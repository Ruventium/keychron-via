#!/usr/bin/env python3
"""
Клиент VIA-протокола (raw HID) для Keychron Q14 Pro на Linux.
Работает напрямую через /dev/hidrawX — без браузера, Electron и драйверов.

Геометрия Q14 Pro (из официального definition):
    6 строк x 19 столбцов = 114 клавиш, 228 байт на слой, 4 слоя = 912 байт.
    Порядок байт в EEPROM: BIG-endian (старший байт первым) — проверено эмпирически.

Использование:
    ./via.py info                     # версия протокола, слои, размеры
    ./via.py dump   out.json          # полный бэкап (keymap + encoders + macros)
    ./via.py restore in.json          # восстановить из бэкапа
    ./via.py get     <layer> <row> <col>
    ./via.py set     <layer> <row> <col> <keycode-hex>
    ./via.py enc     <layer> <idx> [keycode-hex]
    ./via.py diff    out.json         # отличия от дефолта прошивки
"""
import json
import os
import select
import sys
import glob

REPORT = 32

CMD_GET_PROTOCOL_VERSION = 0x01
CMD_GET_KEYBOARD_VALUE = 0x02
CMD_SET_KEYBOARD_VALUE = 0x03
CMD_DYNAMIC_KEYMAP_GET_KEYCODE = 0x04
CMD_DYNAMIC_KEYMAP_SET_KEYCODE = 0x05
CMD_DYNAMIC_KEYMAP_GET_BUFFER = 0x12
CMD_DYNAMIC_KEYMAP_SET_BUFFER = 0x13
CMD_KEYMAP_GET_ENCODER = 0x14
CMD_KEYMAP_SET_ENCODER = 0x15
CMD_MACRO_GET_COUNT = 0x0C
CMD_MACRO_GET_BUFFER_SIZE = 0x0D
CMD_MACRO_GET_BUFFER = 0x0E
CMD_MACRO_SET_BUFFER = 0x0F
CMD_LAYER_COUNT = 0x11

ROWS = 6
COLS = 19
CELLS = ROWS * COLS              # 114
LAYER_BYTES = CELLS * 2          # 228
LAYERS = 4
KEYMAP_BYTES = LAYER_BYTES * LAYERS   # 912


def find_device():
    """hidraw-узел с usage page 0xFF60 / usage 0x61 (VIA raw HID)."""
    for h in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
        try:
            rd = open(os.path.join(h, 'device/report_descriptor'), 'rb').read()
        except OSError:
            continue
        if b'\x06\x60\xff' in rd and b'\x09\x61' in rd:
            ue = open(os.path.join(h, 'device/uevent')).read()
            name = next((l.split('=', 1)[1] for l in ue.splitlines()
                         if l.startswith('HID_NAME=')), '?')
            return '/dev/' + os.path.basename(h), name
    raise SystemExit('VIA raw HID interface not found (keyboard unplugged?)')


class Via:
    def __init__(self, dev=None, timeout=1.0):
        self.dev = dev or find_device()[0]
        self.fd = os.open(self.dev, os.O_RDWR)
        self.timeout = timeout

    def _flush(self):
        """Выбрасывает висящие пакеты из буфера hidraw.

        Критично: прошивка Keychron присылает ответ на каждую команду,
        включая set-команды. Если их не вычитывать, следующий запрос
        получит ЧУЖОЙ ответ и результат будет случайным.
        """
        n = 0
        while True:
            r, _, _ = select.select([self.fd], [], [], 0)
            if not r:
                return n
            os.read(self.fd, REPORT)
            n += 1

    def xfer(self, payload, timeout=None):
        self._flush()
        buf = bytes(payload) + b'\x00' * (REPORT - len(payload))
        os.write(self.fd, buf)
        t = self.timeout if timeout is None else timeout
        r, _, _ = select.select([self.fd], [], [], t)
        if not r:
            return None
        return os.read(self.fd, REPORT)

    def call(self, payload, timeout=None, tries=4):
        """Команда с проверкой: ответ должен начинаться с того же кода.

        Без этой проверки устаревший ответ от предыдущей команды
        интерпретируется как ответ на текущую — отсюда «настройки
        не применяются» и случайные значения.
        """
        want = payload[0]
        last = None
        for _ in range(tries):
            r = self.xfer(payload, timeout)
            if r is None:
                last = 'timeout for cmd 0x%02X' % want
                continue
            if r[0] == 0xFF:
                last = 'cmd 0x%02X unhandled by firmware' % want
                continue
            if r[0] != want:
                last = 'desync: expected 0x%02X, got 0x%02X' % (want, r[0])
                continue
            return r
        raise RuntimeError(last or 'no valid response for cmd 0x%02X' % want)

    # --- низкий уровень ---
    def protocol_version(self):
        """Версия протокола VIA — BIG-endian (0x00,0x0C -> 12).

        Прошивка Q14 Pro отвечает здесь big-endian, а macro_buffer_size —
        little-endian. Смешанный порядок байт в одном протоколе — её дефект,
        учитываем явно.
        """
        r = self.call([CMD_GET_PROTOCOL_VERSION])
        return (r[1] << 8) | r[2]

    def firmware_version(self):
        """Версия прошивки из USB-дескриптора (bcdDevice), напр. '1.01'."""
        for d in glob.glob('/sys/bus/usb/devices/*/'):
            try:
                vid = open(d + 'idVendor').read().strip()
                if vid != '3434':
                    continue
                bcd = int(open(d + 'bcdDevice').read().strip(), 16)
                return '%d.%02d' % (bcd >> 8, bcd & 0xFF)
            except (OSError, ValueError):
                continue
        return '?'

    def layer_count(self):
        return self.call([CMD_LAYER_COUNT])[1]

    def macro_count(self):
        return self.call([CMD_MACRO_GET_COUNT])[1]

    def macro_buffer_size(self):
        r = self.call([CMD_MACRO_GET_BUFFER_SIZE])
        return r[1] | (r[2] << 8)

    def get_buffer(self, offset, size):
        """Чтение EEPROM. ВАЖНО: size > 32 ВЕШАЕТ прошивку намертво.

        Проверено на железе: запрос size=120 уводит устройство в HardFault
        (бесконечный цикл), после чего помогает только переподключение USB.
        Поэтому размер жёстко ограничен.
        """
        if not 1 <= size <= 32:
            raise ValueError('size must be 1..32 (firmware hangs beyond that)')
        r = self.call([CMD_DYNAMIC_KEYMAP_GET_BUFFER, (offset >> 8) & 0xFF, offset & 0xFF, size])
        # прошивка иногда отдаёт меньше запрошенного — добираем по одному
        data = bytes(r[4:4 + size])
        while len(data) < size:
            more = self.call([CMD_DYNAMIC_KEYMAP_GET_BUFFER,
                              ((offset + len(data)) >> 8) & 0xFF,
                              (offset + len(data)) & 0xFF, 1])
            data += bytes(more[4:5])
        return data[:size]

    def set_buffer(self, offset, data):
        self.call([CMD_DYNAMIC_KEYMAP_SET_BUFFER, (offset >> 8) & 0xFF,
                   offset & 0xFF, len(data)] + list(data))

    def read_keymap(self, size=KEYMAP_BYTES):
        out = b''
        off = 0
        while off < size:
            n = min(16, size - off)
            out += self.get_buffer(off, n)
            off += n
        return out

    def write_keymap(self, data):
        off = 0
        while off < len(data):
            n = min(16, len(data) - off)
            self.set_buffer(off, data[off:off + n])
            off += n

    def get_encoder(self, layer, idx, clockwise=0):
        """Читает код поворота энкодера.

        Протокол VIA: [0x14, layer, idx, clockwise]. Байт clockwise обязателен —
        без него прошивка возвращает содержимое не того слота (CCW), из-за чего
        значение выглядит «съехавшим» на байт (0x00AA читается как 0xAA00).

        ВАЖНО: idx >= 1 ВЕШАЕТ прошивку (HardFault). У Q14 Pro один энкодер.
        """
        if idx != 0:
            raise ValueError('Q14 Pro has exactly one encoder (idx must be 0)')
        r = self.call([CMD_KEYMAP_GET_ENCODER, layer, idx, 1 if clockwise else 0])
        return (r[4] << 8) | r[5]

    def set_encoder(self, layer, idx, kc, clockwise=0):
        """Записывает код поворота энкодера.

        Протокол VIA: [0x15, layer, idx, clockwise, kc_hi, kc_lo] — ровно 6 байт.
        Пропуск байта clockwise сдвигает поля: младший байт ключа уходит в
        поле направления, а сам ключ получает нулевой младший байт (0x00AA -> 0xAA00).
        Именно это ломало энкодер громкости.
        """
        if idx != 0:
            raise ValueError('Q14 Pro has exactly one encoder (idx must be 0)')
        self.call([CMD_KEYMAP_SET_ENCODER, layer, idx, 1 if clockwise else 0,
                   (kc >> 8) & 0xFF, kc & 0xFF])



    def get_macro(self, offset, size):
        r = self.call([CMD_MACRO_GET_BUFFER, (offset >> 8) & 0xFF, offset & 0xFF, size])
        return bytes(r[4:4 + size])

    def set_macro(self, offset, data):
        self.call([CMD_MACRO_SET_BUFFER, (offset >> 8) & 0xFF, offset & 0xFF,
                   len(data)] + list(data))

    def close(self):
        os.close(self.fd)


def usb_path():
    """USB-путь клавиатуры (напр. '1-11.1') — нужен для переподключения.

    Берём реальный sysfs-путь вида
      .../usb1/1-11/1-11.1/1-11.1:1.1/0003:3434:06E0.000D
    и отрезаем последние два компонента (HID-интерфейс и дескриптор).
    """
    for h in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
        try:
            rd = open(os.path.join(h, 'device/report_descriptor'), 'rb').read()
        except OSError:
            continue
        if b'\x06\x60\xff' not in rd or b'\x09\x61' not in rd:
            continue
        real = os.path.realpath(os.path.join(h, 'device'))
        parts = real.split('/')
        # .../usb1/<USB-устройство>/<интерфейс>/<hid-дескриптор>
        if len(parts) >= 3:
            return parts[-3]
    return None


def usb_reconnect(path=None, tries=8):
    """Переподключает устройство через sysfs (аналог выдёргивания кабеля).

    Единственный способ поднять клавиатуру после зависания прошивки
    (get_buffer size>32 или get_encoder idx>0). Требует прав root.
    """
    path = path or usb_path()
    if not path:
        return False, 'USB-путь не определён'
    base = '/sys/bus/usb/drivers/usb'
    unbind, bind = base + '/unbind', base + '/bind'
    try:
        with open(unbind, 'w') as f:
            f.write(path)
    except OSError as e:
        return False, 'unbind: %s (нужен root)' % e
    import time as _t
    _t.sleep(2.0)
    for i in range(tries):
        try:
            with open(bind, 'w') as f:
                f.write(path)
        except OSError as e:
            return False, 'bind: %s' % e
        _t.sleep(2.5)
        # устройство считается поднятым, когда появился интерфейс 0xFF60/0x61
        if _via_node():
            return True, 'подключено с попытки %d' % (i + 1)
    return False, 'не поднялось за %d попыток' % tries


def _via_node(usbpath=None):
    """Ищет hidraw-узел VIA-интерфейса (usage page 0xFF60 / usage 0x61)."""
    for h in glob.glob('/sys/class/hidraw/hidraw*'):
        try:
            rd = open(os.path.join(h, 'device/report_descriptor'), 'rb').read()
        except OSError:
            continue
        if b'\x06\x60\xff' in rd and b'\x09\x61' in rd:
            return '/dev/' + os.path.basename(h)
    return None


def cell_index(layer, row, col):
    return layer * LAYER_BYTES + (row * COLS + col) * 2


def decode(buf, layer, row, col):
    i = cell_index(layer, row, col)
    return (buf[i] << 8) | buf[i + 1]


def encode(buf, layer, row, col, kc):
    i = cell_index(layer, row, col)
    buf[i] = (kc >> 8) & 0xFF
    buf[i + 1] = kc & 0xFF


def dump(path, dev=None, enc_count=1):
    k = Via(dev)
    try:
        buf = k.read_keymap()
        data = {
            'device': k.dev,
            'protocol_version': k.protocol_version(),
            'matrix': {'rows': ROWS, 'cols': COLS},
            'layers': k.layer_count(),
            'layer_bytes': LAYER_BYTES,
            'endian': 'big',
            'keymap_hex': buf.hex(),
            'encoders': {},
            'macros_hex': None,
        }
        for l in range(LAYERS):
            data['encoders'][str(l)] = [
                {'cw': '%04x' % k.get_encoder(l, e, 1),
                 'ccw': '%04x' % k.get_encoder(l, e, 0)}
                for e in range(enc_count)]
        msize = k.macro_buffer_size()
        if msize:
            mdata = b''
            off = 0
            while off < msize:
                n = min(16, msize - off)
                mdata += k.get_macro(off, n)
                off += n
            data['macros_hex'] = mdata.hex()
        with open(path, 'w') as f:
            json.dump(data, f, indent=1)
        print('бэкап записан: %s (%d байт keymap + %d байт макросов)'
              % (path, len(buf), len(data['macros_hex'] or '') // 2))
    finally:
        k.close()


def restore(path, dev=None):
    d = json.load(open(path))
    k = Via(dev)
    try:
        buf = bytes.fromhex(d['keymap_hex'])
        k.write_keymap(buf)
        for l, encs in d.get('encoders', {}).items():
            for e, code in enumerate(encs):
                # новый формат — {'cw','ccw'}; старый — одна строка (только CCW)
                if isinstance(code, dict):
                    if 'cw' in code:
                        k.set_encoder(int(l), e, int(code['cw'], 16), 1)
                    if 'ccw' in code:
                        k.set_encoder(int(l), e, int(code['ccw'], 16), 0)
                else:
                    k.set_encoder(int(l), e, int(code, 16), 0)
        if d.get('macros_hex'):
            m = bytes.fromhex(d['macros_hex'])
            off = 0
            while off < len(m):
                n = min(16, len(m) - off)
                k.set_macro(off, m[off:off + n])
                off += n
        print('восстановлено из %s' % path)
    finally:
        k.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    dev = os.environ.get('VIA_DEV')

    if cmd == 'find':
        print(*find_device(), sep='  ')
        return 0

    if cmd == 'info':
        k = Via(dev)
        try:
            print('device          :', k.dev)
            print('protocol version:', k.protocol_version())
            print('layers          :', k.layer_count())
            print('keymap          : %dx%d = %d клавиш, %d байт/слой, %d байт всего'
                  % (ROWS, COLS, CELLS, LAYER_BYTES, KEYMAP_BYTES))
            print('macros          : %d слотов, буфер %d байт'
                  % (k.macro_count(), k.macro_buffer_size()))
            print('encoders        :', ['0x%04x cw / 0x%04x ccw'
                                        % (k.get_encoder(0, i, 1), k.get_encoder(0, i, 0))
                                        for i in range(1)])
        finally:
            k.close()
        return 0

    if cmd == 'dump':
        dump(sys.argv[2], dev)
        return 0

    if cmd == 'restore':
        restore(sys.argv[2], dev)
        return 0

    if cmd == 'get':
        l, r, c = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
        k = Via(dev)
        try:
            print('%04x' % decode(k.read_keymap(), l, r, c))
        finally:
            k.close()
        return 0

    if cmd == 'set':
        l, r, c = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
        kc = int(sys.argv[5], 16)
        k = Via(dev)
        try:
            k.set_buffer(cell_index(l, r, c), bytes([(kc >> 8) & 0xFF, kc & 0xFF]))
            print('%04x' % decode(k.read_keymap(), l, r, c))
        finally:
            k.close()
        return 0

    if cmd == 'enc':
        l, i = int(sys.argv[2]), int(sys.argv[3])
        cw = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0
        k = Via(dev)
        try:
            if len(sys.argv) > 5:
                k.set_encoder(l, i, int(sys.argv[5], 16), cw)
            print('%04x' % k.get_encoder(l, i, cw))
        finally:
            k.close()
        return 0

    print('unknown command:', cmd)
    return 1


if __name__ == '__main__':
    sys.exit(main())
