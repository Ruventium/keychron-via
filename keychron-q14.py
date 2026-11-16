#!/usr/bin/env python3
"""
Keychron Q14 Pro — нативный конфигуратор для Linux (GTK4).

Работает напрямую с клавиатурой через /dev/hidraw (raw HID, VIA-протокол).
Без браузера, без Electron, без драйверов.

Запуск:  ./keychron-q14.py
"""
import glob
import json
import math
import os
import sys
import time

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import via as vialib   # noqa: E402
import keycodes as kc  # noqa: E402
import kle             # noqa: E402

LAYOUT_FILE = os.path.join(HERE, 'q14_pro.json')
BACKUP_DIR = os.path.join(HERE, 'backups')
LAYER_COUNT = 4

# --- палитра (OLED-black) ---
BG = (0.043, 0.043, 0.055)
KEY_BORDER = (0.22, 0.22, 0.27)
TEXT = (0.93, 0.93, 0.96)
TEXT_DIM = (0.48, 0.48, 0.55)
SEL_FILL = (0.36, 0.30, 0.85)
SEL_BORDER = (0.62, 0.52, 1.0)
HOVER_LIGHT = 0.09

CAT_COLORS = {
    'letters':  (0.16, 0.18, 0.23),
    'control':  (0.13, 0.15, 0.19),
    'symbols':  (0.15, 0.17, 0.21),
    'fkeys':    (0.14, 0.16, 0.20),
    'mods':     (0.20, 0.17, 0.27),
    'media':    (0.13, 0.21, 0.23),
    'lighting': (0.24, 0.20, 0.11),
    'keychron': (0.22, 0.15, 0.18),
    'special':  (0.09, 0.09, 0.11),
    'other':    (0.14, 0.14, 0.17),
}


# ============================================================
#  Транспорт
# ============================================================
class Keyboard:
    """Обёртка с ретраями: прошивка иногда отвечает 0xFF/молчит."""

    def __init__(self):
        dev, name = vialib.find_device()
        self.dev = dev
        self.name = name
        self.k = vialib.Via(dev)

    def _retry(self, fn, tries=5, delay=0.12):
        last = None
        for _ in range(tries):
            try:
                return fn()
            except RuntimeError as e:
                last = e
                time.sleep(delay)
        raise last

    def info(self):
        return {
            'name': self.name,
            'dev': self.dev,
            'protocol': self._retry(self.k.protocol_version),
            'firmware': self.k.firmware_version(),
            'layers': self._retry(self.k.layer_count),
            'macros': self._retry(self.k.macro_count),
        }

    def read_keymap(self):
        return self._retry(self.k.read_keymap)

    def write_keymap(self, data):
        self._retry(lambda: self.k.write_keymap(data))

    def write_cell(self, layer, row, col, val):
        idx = vialib.cell_index(layer, row, col)
        self._retry(lambda: self.k.set_buffer(
            idx, bytes([(val >> 8) & 0xFF, val & 0xFF])))

    def read_encoder(self, layer, idx=0, clockwise=0):
        return self._retry(lambda: self.k.get_encoder(layer, idx, clockwise))

    def write_encoder(self, layer, idx, val, clockwise=0):
        """Запись поворота энкодера.

        Прошивка принимает только 6-байтовую форму команды (с байтом clockwise).
        Каждое направление — отдельный слот, поэтому писать надо оба.
        """
        self._retry(lambda: self.k.set_encoder(layer, idx, val, clockwise))

    def close(self):
        try:
            self.k.close()
        except Exception:
            pass


# ============================================================
#  Клавиатура на экране
# ============================================================
class KeyboardView(Gtk.DrawingArea):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.keys = kle.load(LAYOUT_FILE)
        for k in self.keys:
            k['is_encoder'] = self._detect_encoder(k)

        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_size_request(560, 340)
        self.set_draw_func(self.on_draw)
        self.hover = None

        self.minx, self.miny, self.maxx, self.maxy = kle.bounds(self.keys)

        motion = Gtk.EventControllerMotion()
        motion.connect('motion', self.on_motion)
        self.add_controller(motion)

        click = Gtk.GestureClick()
        click.connect('pressed', self.on_click)
        self.add_controller(click)

    @staticmethod
    def _detect_encoder(k):
        parts = k['label'].split('\n')
        return len(parts) > 1 and parts[-1].strip().startswith('e')

    def _geometry(self, w, h):
        pad = 14.0
        spanx = self.maxx - self.minx
        spany = self.maxy - self.miny
        unit = min((w - 2 * pad) / spanx, (h - 2 * pad) / spany)
        ox = (w - spanx * unit) / 2 - self.minx * unit
        oy = (h - spany * unit) / 2 - self.miny * unit
        return unit, ox, oy

    def _hit(self, mx, my, w, h):
        unit, ox, oy = self._geometry(w, h)
        best = None
        for k in self.keys:
            # переводим точку в систему координат клавиши (обратный поворот)
            px, py = kle.unrotate_point(mx, my, k['r'],
                                        ox + k['rx'] * unit,
                                        oy + k['ry'] * unit)
            x = ox + k['kx'] * unit
            y = oy + k['ky'] * unit
            kw = k['w'] * unit
            kh = k['h'] * unit
            if x <= px <= x + kw and y <= py <= y + kh:
                best = k
                break
        return best, unit, ox, oy

    def on_motion(self, ctrl, x, y):
        k, _, _, _ = self._hit(x, y, self.get_width(), self.get_height())
        if k is not self.hover:
            self.hover = k
            self.queue_draw()

    def on_click(self, gesture, n, x, y):
        k, _, _, _ = self._hit(x, y, self.get_width(), self.get_height())
        if k:
            self.app.select_key(k)

    def on_draw(self, area, cr, w, h):
        cr.set_source_rgb(*BG)
        cr.paint()
        if not self.keys:
            return

        unit, ox, oy = self._geometry(w, h)

        for k in self.keys:
            val = self.app.get_value(k)
            cat = kc.category_of(val)
            base = CAT_COLORS.get(cat, CAT_COLORS['other'])

            ins = 1.6
            x = ox + k['kx'] * unit + ins
            y = oy + k['ky'] * unit + ins
            kw = k['w'] * unit - 2 * ins
            kh = k['h'] * unit - 2 * ins
            rad = max(3.0, min(6.0, unit * 0.09))

            # энкодер рисуем как ручку: круг + подписи направлений
            if k['is_encoder']:
                self._draw_encoder(cr, k, x, y, kw, kh, unit)
                continue

            sel = k is self.app.selected
            hov = k is self.hover

            cr.save()
            if k['r']:
                cr.translate(ox + k['rx'] * unit, oy + k['ry'] * unit)
                cr.rotate(math.radians(k['r']))
                cr.translate(-(ox + k['rx'] * unit), -(oy + k['ry'] * unit))

            if sel:
                cr.set_source_rgb(*SEL_FILL)
            elif hov:
                cr.set_source_rgb(*(min(1.0, c + HOVER_LIGHT) for c in base))
            else:
                cr.set_source_rgb(*base)
            self._round_rect(cr, x, y, kw, kh, rad)
            cr.fill_preserve()

            if sel:
                cr.set_source_rgb(*SEL_BORDER)
                cr.set_line_width(2.0)
            else:
                cr.set_source_rgb(*KEY_BORDER)
                cr.set_line_width(1.0)
            cr.stroke()

            label = kc.describe(val)
            if val in (0x0000, 0x0001):
                cr.set_source_rgb(*TEXT_DIM)
            else:
                cr.set_source_rgb(*TEXT)
            fs = max(6.5, min(12.0, unit * 0.21))
            self._text(cr, label, x + kw / 2, y + kh / 2, fs, maxw=kw - 3)

            cr.restore()

    def _draw_encoder(self, cr, k, x, y, kw, kh, unit):
        """Ручка энкодера: круг с двумя подписями (CW сверху, CCW снизу)."""
        cx, cy = x + kw / 2, y + kh / 2
        r = min(kw, kh) * 0.30
        sel = k is self.app.selected
        hov = k is self.hover

        # корпус
        cr.set_source_rgb(*(0.30, 0.26, 0.62) if sel else
                          (0.20, 0.20, 0.26) if not hov else
                          (0.27, 0.27, 0.34))
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.fill_preserve()
        cr.set_source_rgb(*(SEL_BORDER if sel else KEY_BORDER))
        cr.set_line_width(2.0 if sel else 1.2)
        cr.stroke()

        # насечка
        cr.set_source_rgb(0.55, 0.52, 0.75)
        cr.set_line_width(max(1.2, unit * 0.02))
        cr.move_to(cx, cy - r * 0.75)
        cr.line_to(cx, cy - r * 0.25)
        cr.stroke()

        cw = self.app.encoder.get((self.app.layer, 1), 0)
        ccw = self.app.encoder.get((self.app.layer, 0), 0)
        fs = max(6.0, min(9.5, unit * 0.17))
        cr.set_source_rgb(*TEXT)
        self._text(cr, kc.describe(cw), cx, y + kh * 0.12, fs, maxw=kw - 2)
        self._text(cr, kc.describe(ccw), cx, y + kh * 0.88, fs, maxw=kw - 2)

    @staticmethod
    def _round_rect(cr, x, y, w, h, r):
        r = min(r, w / 2, h / 2)
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

    @staticmethod
    def _text(cr, s, cx, cy, size, maxw=None):
        layout = PangoCairo.create_layout(cr)
        fd = Pango.FontDescription()
        fd.set_family('Sans')
        fd.set_size(int(size * Pango.SCALE))
        fd.set_weight(Pango.Weight.SEMIBOLD)
        layout.set_font_description(fd)
        layout.set_text(s, -1)
        tw, th = layout.get_pixel_size()
        # сжимаем слишком длинные подписи
        if maxw and tw > maxw and tw > 0:
            fd2 = fd.copy()
            factor = maxw / tw
            fd2.set_size(max(1, int(size * Pango.SCALE * factor)))
            layout.set_font_description(fd2)
            tw, th = layout.get_pixel_size()
        cr.move_to(cx - tw / 2, cy - th / 2)
        PangoCairo.show_layout(cr, layout)


# ============================================================
#  Приложение
# ============================================================
class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.ruventium.keychronq14')
        self.kb = None
        self.keymap = None
        self.encoder = {}
        self.layer = 0
        self.selected = None
        self.dirty = False
        self.win_mode = True          # переключатель ОС на задней панели
        self.enc_target = 'press'     # press | cw | ccw

    # --- данные ---
    def get_value(self, k):
        if k['is_encoder']:
            return self.encoder.get((self.layer, 0), 0)
        if self.keymap is None:
            return 0
        return vialib.decode(self.keymap, self.layer, k['row'], k['col'])

    def reload(self, quiet=False):
        self.keymap = self.kb.read_keymap()
        self.encoder = {}
        for l in range(LAYER_COUNT):
            for cw in (0, 1):
                try:
                    self.encoder[(l, cw)] = self.kb.read_encoder(l, 0, cw)
                except Exception:
                    self.encoder[(l, cw)] = 0
        self.dirty = False
        if self.view:
            self.view.queue_draw()
        if hasattr(self, 'enc_label'):
            self.update_enc_label()
        if not quiet:
            self.status('Карта клавиш прочитана из клавиатуры')

    def active_layer(self):
        """Слой, на котором реально работает клавиатура.

        Слои у Q Pro идут парами: 0/2 — Mac, 1/3 — Win/Android.
        Переключатель ОС на задней панели выбирает пару, а базовый слой
        внутри пары — это 0 или 2. Определить точное значение по протоколу
        нельзя (прошивка не отдаёт текущий слой), но для пользователя
        практически важно то, что править надо ПОСЛЕДНИЙ слой пары.
        """
        return 2 if self.win_mode else 0

    def is_editing_active(self):
        return self.layer in (self.active_layer(), self.active_layer() + 1)

    def select_key(self, k):
        self.selected = k
        self.view.queue_draw()
        if k['is_encoder']:
            press = self.get_value(k)
            cw = self.encoder.get((self.layer, 1), 0)
            ccw = self.encoder.get((self.layer, 0), 0)
            self.sel_label.set_markup(
                '<b>энкодер (ручка)</b> — три действия:\n'
                'нажатие:     <b>%s</b> (0x%04X)\n'
                'по часовой: <b>%s</b> (0x%04X)\n'
                'против:      <b>%s</b> (0x%04X)\n'
                '<span size="small" foreground="#8a8a9a">'
                'Код из палитры запишется в выбранную выше цель.</span>'
                % (kc.describe(press), press,
                   kc.describe(cw), cw, kc.describe(ccw), ccw))
            return
        val = self.get_value(k)
        warn = ''
        if not self.is_editing_active():
            warn = ('\n<span foreground="#d0a040">⚠ это не активный слой — '
                    'устройство работает на L%d, изменения здесь '
                    'не проявятся</span>' % self.active_layer())
        self.sel_label.set_markup(
            '<b>row %d, col %d</b>\nсейчас: %s  (0x%04X)%s'
            % (k['row'], k['col'], kc.describe(val), val, warn))

    def assign(self, val):
        if self.selected is None:
            self.status('Сначала выбери клавишу на клавиатуре')
            return
        k = self.selected
        try:
            if k['is_encoder']:
                target = self.enc_target
                idx = vialib.cell_index(self.layer, k['row'], k['col'])
                if target == 'press':
                    self.kb.write_cell(self.layer, k['row'], k['col'], val)
                    self.keymap = (self.keymap[:idx]
                                   + bytes([(val >> 8) & 0xFF, val & 0xFF])
                                   + self.keymap[idx + 2:])
                    where = 'нажатие'
                elif target == 'cw':
                    self.kb.write_encoder(self.layer, 0, val, 1)
                    self.encoder[(self.layer, 1)] = val
                    where = 'по часовой'
                else:
                    self.kb.write_encoder(self.layer, 0, val, 0)
                    self.encoder[(self.layer, 0)] = val
                    where = 'против часовой'
                self.dirty = True
                self.view.queue_draw()
                self.select_key(k)
                self.update_enc_label()
                self.status('Энкодер L%d, %s -> %s (0x%04X) в EEPROM'
                            % (self.layer, where, kc.describe(val), val))
                return
            self.kb.write_cell(self.layer, k['row'], k['col'], val)
            idx = vialib.cell_index(self.layer, k['row'], k['col'])
            self.keymap = (self.keymap[:idx]
                           + bytes([(val >> 8) & 0xFF, val & 0xFF])
                           + self.keymap[idx + 2:])
            self.dirty = True
            self.view.queue_draw()
            self.select_key(k)
            self.status('Записано: r%d c%d  →  %s (0x%04X) в EEPROM'
                        % (k['row'], k['col'], kc.describe(val), val))
        except Exception as e:
            self.status('Ошибка записи: %s' % e)

    def switch_layer(self, l):
        self.layer = l
        self.view.queue_draw()
        self.update_enc_label()
        if self.selected:
            self.select_key(self.selected)
        msg = 'Слой %d' % l
        if not self.is_editing_active():
            msg += ('  ⚠ неактивный — устройство работает на L%d'
                    % self.active_layer())
        self.status(msg)

    def on_os_toggle(self, w):
        self.win_mode = w.get_active()
        w.set_label('Win' if self.win_mode else 'Mac')
        act = self.active_layer()
        # чтобы не запутаться, автоматически переключаемся на активный слой
        if self.layer_btns and self.layer_btns[act].get_active() is False:
            self.layer_btns[act].set_active(True)
        else:
            self.switch_layer(act)
        self.status('Режим %s: активны слои %d/%d'
                    % ('Win' if self.win_mode else 'Mac', act, act + 1))

    def on_enc_target(self, target, w):
        if w.get_active():
            self.enc_target = target
            self.status('Цель энкодера: %s' %
                        {'press': 'нажатие', 'cw': 'по часовой',
                         'ccw': 'против часовой'}[target])

    def update_enc_label(self):
        press = 0
        if self.keymap is not None:
            press = vialib.decode(self.keymap, self.layer, 0, 0)
        cw = self.encoder.get((self.layer, 1), 0)
        ccw = self.encoder.get((self.layer, 0), 0)
        self.enc_label.set_markup(
            'L%d  нажатие: <b>%s</b>\n'
            'L%d  по часовой: <b>%s</b>\n'
            'L%d  против: <b>%s</b>'
            % (self.layer, kc.describe(press),
               self.layer, kc.describe(cw),
               self.layer, kc.describe(ccw)))

    def do_reconnect(self):
        """Переподключение USB — выход из зависания прошивки."""
        path = vialib.usb_path()
        self.status('Переподключаю USB (%s)...' % (path or '?'))
        ok, msg = vialib.usb_reconnect(path)
        if not ok:
            self.status('USB: %s' % msg)
            return
        # пересоздаём соединение
        try:
            if self.kb:
                self.kb.close()
        except Exception:
            pass
        try:
            self.kb = Keyboard()
            i = self.kb.info()
            self.conn_label.set_text(
                '%s  ·  %s  ·  прошивка %s  ·  VIA v%d  ·  слоёв %d'
                % (i['name'], i['dev'], i['firmware'], i['protocol'], i['layers']))
            self.reload(quiet=True)
            self.update_enc_label()
            self.status('USB переподключён, %s' % msg)
        except Exception as e:
            self.status('USB поднят, но связь не восстановилась: %s' % e)

    def status(self, text):
        if hasattr(self, 'status_label'):
            self.status_label.set_text(text)

    # --- UI ---
    def do_activate(self):
        self.view = None
        self.selected = None

        win = Gtk.ApplicationWindow(application=self)
        win.set_title('Keychron Q14 Pro — конфигуратор')
        win.set_default_size(1480, 940)

        css = Gtk.CssProvider()
        css.load_from_data(b"""
            window { background: #0b0b0e; }
            label { color: #ededf2; }
            button { background: #1b1b21; color: #ededf2;
                     border: 1px solid #34343e; border-radius: 6px;
                     padding: 5px 9px; font-size: 12px; }
            button:hover { background: #272730; border-color: #4a4a58; }
            button:active { background: #4a3fc4; }
            .layerbtn:checked { background: #4a3fc4; border-color: #6a5ce0; }
            .cat-label { color: #7a7a8a; font-size: 10px;
                         font-weight: bold; }
            .dim { color: #7a7a8a; font-size: 11px; }
            .sel-info { background: #14141a; border: 1px solid #34343e;
                        border-radius: 8px; padding: 8px; }
        """)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # подключение
        connected = True
        try:
            self.kb = Keyboard()
            i = self.kb.info()
            conn_text = '%s  ·  %s  ·  прошивка %s  ·  VIA v%d  ·  слоёв %d' % (
                i['name'], i['dev'], i['firmware'], i['protocol'], i['layers'])
        except Exception as e:
            connected = False
            conn_text = 'нет связи: %s' % e

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        win.set_child(root)

        # --- шапка ---
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        top.set_margin_top(10)
        top.set_margin_bottom(6)
        top.set_margin_start(14)
        top.set_margin_end(14)
        root.append(top)

        t = Gtk.Label()
        t.set_markup('<b>Keychron Q14 Pro</b>')
        top.append(t)

        self.conn_label = Gtk.Label(label=conn_text)
        self.conn_label.add_css_class('dim')
        top.append(self.conn_label)

        sp = Gtk.Box()
        sp.set_hexpand(True)
        top.append(sp)

        # активная пара слоёв (переключатель ОС на задней панели)
        self.os_btn = Gtk.ToggleButton(label='Win')
        self.os_btn.set_active(True)
        self.os_btn.set_tooltip_text(
            'Положение переключателя ОС на задней панели.\n'
            'Win/Android -> слои 2/3, Mac/iOS -> слои 0/1.')
        self.os_btn.connect('toggled', self.on_os_toggle)
        top.append(self.os_btn)

        lb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        self.layer_btns = []
        for l in range(LAYER_COUNT):
            b = Gtk.ToggleButton(label='L%d' % l)
            b.add_css_class('layerbtn')
            b.set_size_request(46, -1)
            if self.layer_btns:
                b.set_group(self.layer_btns[0])
            else:
                b.set_active(True)
            b.connect('toggled', lambda w, lv=l: (
                self.switch_layer(lv) if w.get_active() else None))
            lb.append(b)
            self.layer_btns.append(b)
        top.append(lb)

        btn = Gtk.Button(label='⟳')
        btn.set_tooltip_text('Перечитать из клавиатуры')
        btn.connect('clicked', lambda w: self.safe(self.reload))
        top.append(btn)

        btn = Gtk.Button(label='💾 Бэкап')
        btn.connect('clicked', lambda w: self.safe(self.do_backup))
        top.append(btn)

        btn = Gtk.Button(label='↺ Откат')
        btn.set_tooltip_text('Восстановить из файла бэкапа')
        btn.connect('clicked', lambda w: self.safe(self.do_restore))
        top.append(btn)

        btn = Gtk.Button(label='⚡ USB')
        btn.set_tooltip_text(
            'Переподключить USB. Нужно, если клавиатура зависла\n'
            '(перестала отвечать после некорректного запроса).')
        btn.connect('clicked', lambda w: self.safe(self.do_reconnect))
        top.append(btn)

        # --- тело ---
        paned = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        paned.set_vexpand(True)
        paned.set_hexpand(True)
        root.append(paned)

        self.view = KeyboardView(self)
        self.view.set_size_request(560, 340)
        fr = Gtk.Frame()
        fr.set_child(self.view)
        fr.set_margin_start(14)
        fr.set_margin_end(8)
        fr.set_margin_top(4)
        fr.set_margin_bottom(8)
        fr.set_hexpand(True)
        paned.append(fr)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right.set_margin_end(14)
        right.set_margin_top(4)
        right.set_margin_bottom(8)
        right.set_size_request(420, -1)
        paned.append(right)

        self.sel_label = Gtk.Label()
        self.sel_label.set_markup('<b>клавиша не выбрана</b>')
        self.sel_label.set_xalign(0)
        self.sel_label.set_wrap(True)
        self.sel_label.add_css_class('sel-info')
        right.append(self.sel_label)

        # --- энкодер: нажатие и два направления — три разные цели ---
        enc_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        enc_box.add_css_class('sel-info')
        right.append(enc_box)

        enc_hdr = Gtk.Label()
        enc_hdr.set_markup('<b>энкодер</b> — куда писать код из палитры')
        enc_hdr.set_xalign(0)
        enc_box.append(enc_hdr)

        enc_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=3)
        enc_box.append(enc_row)
        self.enc_btns = []
        for key, lbl, tip in (('press', 'нажатие', 'Нажатие на ручку (ячейка матрицы)'),
                              ('cw', '↻', 'Поворот по часовой'),
                              ('ccw', '↺', 'Поворот против часовой')):
            b = Gtk.ToggleButton(label=lbl)
            b.set_tooltip_text(tip)
            if not self.enc_btns:
                b.set_active(True)
            else:
                b.set_group(self.enc_btns[0])
            b.connect('toggled',
                      lambda w, t=key: self.on_enc_target(t, w))
            enc_row.append(b)
            self.enc_btns.append(b)

        self.enc_label = Gtk.Label()
        self.enc_label.set_xalign(0)
        self.enc_label.set_wrap(True)
        enc_box.append(self.enc_label)

        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        right.append(sw)

        pal = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        pal.set_margin_end(6)
        sw.set_child(pal)

        for cat, items in kc.palette().items():
            lab = Gtk.Label(label=cat)
            lab.set_xalign(0)
            lab.add_css_class('cat-label')
            pal.append(lab)

            flow = Gtk.FlowBox()
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_max_children_per_line(6)
            flow.set_column_spacing(3)
            flow.set_row_spacing(3)
            pal.append(flow)

            for label, code in items:
                b = Gtk.Button(label=label)
                b.set_size_request(62, 28)
                b.connect('clicked', lambda w, c=code: self.assign(c))
                flow.append(b)

        # подвал
        self.status_label = Gtk.Label(
            label='Готово' if connected else 'Клавиатура не найдена')
        self.status_label.add_css_class('dim')
        self.status_label.set_xalign(0)
        self.status_label.set_margin_start(14)
        self.status_label.set_margin_bottom(8)
        root.append(self.status_label)

        win.present()

        if connected:
            self.safe(self.reload)
            # сразу открываем активный слой, чтобы не править не тот
            act = self.active_layer()
            if self.layer_btns:
                self.layer_btns[act].set_active(True)
            else:
                self.switch_layer(act)

    def safe(self, fn, *a):
        try:
            fn(*a)
        except Exception as e:
            self.status('Ошибка: %s' % e)

    # --- бэкап ---
    def do_backup(self):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        path = os.path.join(BACKUP_DIR, time.strftime('%Y%m%d-%H%M%S') + '.json')
        vialib.dump(path, self.kb.dev)
        self.status('Бэкап сохранён: %s' % path)

    def do_restore(self):
        files = sorted(glob.glob(os.path.join(BACKUP_DIR, '*.json')))
        if not files:
            self.status('Бэкапов нет')
            return
        files = list(reversed(files))

        dlg = Gtk.Window(transient_for=self.props.active_window, modal=True)
        dlg.set_title('Выбери бэкап')
        dlg.set_default_size(460, 360)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for m in ('top', 'bottom', 'start', 'end'):
            getattr(box, 'set_margin_' + m)(10)
        dlg.set_child(box)

        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        box.append(sw)

        lst = Gtk.ListBox()
        lst.set_selection_mode(Gtk.SelectionMode.NONE)
        sw.set_child(lst)

        for f in files:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            for m in ('top', 'bottom', 'start', 'end'):
                getattr(row, 'set_margin_' + m)(4)
            lbl = Gtk.Label(label=os.path.basename(f))
            lbl.set_xalign(0)
            lbl.set_hexpand(True)
            row.append(lbl)
            b = Gtk.Button(label='Восстановить')

            def on_click(w, path=f):
                try:
                    vialib.restore(path, self.kb.dev)
                    self.reload(quiet=True)
                    self.status('Восстановлено: %s' % os.path.basename(path))
                except Exception as e:
                    self.status('Ошибка отката: %s' % e)
                dlg.close()

            b.connect('clicked', on_click)
            row.append(b)
            lst.append(row)

        dlg.present()


if __name__ == '__main__':
    App().run(sys.argv)
