"""Корректный парсер KLE (keyboard-layout-editor) для VIA-definition.

Важно: возвращаются координаты ДО поворота (kx, ky) плюс параметры поворота
(r, rx, ry). Поворот применяет отрисовщик (или hit-test) вокруг (rx, ry) —
ровно как в спецификации KLE. Так исключается двойной поворот.

Формат: внешний массив = визуальные строки KLE. Внутри строки:
    dict  — свойства (x, y, w, h, r, rx, ry, c) — накапливаются
    str   — метка клавиши "row,col" (+ произвольные подписи через \\n)

Правила (kle-serial):
    * в начале строки x сбрасывается в 0, w/h в 1;
    * после строки y увеличивается на 1;
    * x/y из dict прибавляются к текущим;
    * r/rx/ry задают поворот кластера и сохраняются до следующего изменения.
"""
import json
import math


def deserialize(kle):
    keys = []
    y = 0.0
    r = 0.0
    rx = 0.0
    ry = 0.0

    for row in kle:
        x = 0.0
        w = 1.0
        h = 1.0
        for item in row:
            if isinstance(item, dict):
                if 'r' in item:
                    r = float(item['r'])
                if 'rx' in item:
                    rx = float(item['rx'])
                if 'ry' in item:
                    ry = float(item['ry'])
                if 'x' in item:
                    x += float(item['x'])
                if 'y' in item:
                    y += float(item['y'])
                if 'w' in item:
                    w = float(item['w'])
                if 'h' in item:
                    h = float(item['h'])
            elif isinstance(item, str):
                label = item
                cell = label.split('\n')[0].strip()
                try:
                    row_i, col_i = (int(v) for v in cell.split(','))
                except ValueError:
                    x += w
                    w, h = 1.0, 1.0
                    continue

                keys.append({
                    'cell': cell,
                    'row': row_i,
                    'col': col_i,
                    'kx': x,          # координаты ДО поворота
                    'ky': y,
                    'w': w,
                    'h': h,
                    'r': r,           # угол, градусы
                    'rx': rx,
                    'ry': ry,
                    'label': label,
                })
                x += w
                w, h = 1.0, 1.0
        y += 1.0

    return keys


def rotate_point(px, py, r, rx, ry):
    """Поворот точки вокруг (rx, ry) на r градусов (система экрана: y вниз)."""
    if not r:
        return px, py
    a = math.radians(r)
    cos_a, sin_a = math.cos(a), math.sin(a)
    dx, dy = px - rx, py - ry
    return rx + dx * cos_a - dy * sin_a, ry + dx * sin_a + dy * cos_a


def unrotate_point(px, py, r, rx, ry):
    """Обратный поворот — для hit-test."""
    return rotate_point(px, py, -r, rx, ry)


def bounds(keys):
    """Габариты с учётом поворотов (по четырём углам каждой клавиши)."""
    xs, ys = [], []
    for k in keys:
        for cx, cy in ((k['kx'], k['ky']),
                       (k['kx'] + k['w'], k['ky']),
                       (k['kx'], k['ky'] + k['h']),
                       (k['kx'] + k['w'], k['ky'] + k['h'])):
            px, py = rotate_point(cx, cy, k['r'], k['rx'], k['ry'])
            xs.append(px)
            ys.append(py)
    return min(xs), min(ys), max(xs), max(ys)


def load(path):
    """Загружает KLE из файла VIA-definition или голого KLE-массива."""
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        if 'layouts' in data and 'keymap' in data['layouts']:
            data = data['layouts']['keymap']
        elif 'keymap' in data:
            data = data['keymap']
    return deserialize(data)


if __name__ == '__main__':
    import sys
    keys = load(sys.argv[1] if len(sys.argv) > 1 else
                '/home/ruventium/projects/keychron-via/q14_pro.json')
    x0, y0, x1, y1 = bounds(keys)
    print('клавиш :', len(keys))
    print('габарит: X %.2f..%.2f  Y %.2f..%.2f  (%.1f x %.1f)' %
          (x0, x1, y0, y1, x1 - x0, y1 - y0))
    rot = sorted({k['r'] for k in keys})
    print('углы   :', rot)
    print('энкодер:', [k['cell'] for k in keys
                       if k['label'].split('\n')[-1].strip().startswith('e')])
