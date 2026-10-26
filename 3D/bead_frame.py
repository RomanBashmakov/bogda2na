#!/usr/bin/env python3
"""Генератор рамки для бисерного полотна (две части: низ и верх).

Полотно 38 x 89 мм. Каждая часть — рамка-периметр, перекрывающая
полотно на 1 мм по всему периметру (окно 36 x 87 мм).
"""
import struct

# ---------------- Параметры (в мм) ----------------
ART_W = 38.0     # ширина полотна
ART_H = 89.0     # высота полотна
OVERLAP = 1.0    # перекрытие полотна рамкой по периметру
WALL = 3.0       # толщина наружной стенки рамки
THICK = 3.0      # толщина каждой части (высота рамки)
FILLET = 0.0     # (запас под будущее)

GAP_H = 0.5                    # припуск по высоте посадки (сверху и снизу)

WIN_W = ART_W - 2 * OVERLAP   # окно полочки = видимая часть
WIN_H = ART_H + 2 * GAP_H - 2 * OVERLAP
SEAT_W = ART_W                # посадочное окно (полотно входит вплотную)
SEAT_H = ART_H + 2 * GAP_H    # посадка по высоте с припуском 0.5 мм сверху и снизу
OUT_W = ART_W + 2 * WALL      # наружный размер
OUT_H = ART_H + 2 * WALL
ART_T = 1.2                   # толщина полотна (зазор между полками)
LEDGE_T = 1.0                 # толщина полочки (выступ)


def box(x0, y0, z0, x1, y1, z1):
    """Возвращает список треугольников (кортежи из 3 вершин) для бруска."""
    v = {
        'a': (x0, y0, z0), 'b': (x1, y0, z0), 'c': (x1, y1, z0), 'd': (x0, y1, z0),
        'e': (x0, y0, z1), 'f': (x1, y0, z1), 'g': (x1, y1, z1), 'h': (x0, y1, z1),
    }
    quads = [
        ('a', 'b', 'c', 'd'),  # низ
        ('e', 'f', 'g', 'h'),  # верх
        ('a', 'b', 'f', 'e'),  # перед
        ('c', 'd', 'h', 'g'),  # зад
        ('b', 'c', 'g', 'f'),  # право
        ('d', 'a', 'e', 'h'),  # лево
    ]
    tris = []
    for q in quads:
        p = [v[k] for k in q]
        tris.append((p[0], p[1], p[2]))
        tris.append((p[0], p[2], p[3]))
    return tris


CLEAR = 0.1                  # зазор шипа в посадочном окне


def top_frame_tris(thick):
    """Верхняя рамка: снизу шип-кольцо (вставляется в нижнюю, прижимает полотно),
    сверху плита с окном. Моделируется сразу в печатном положении."""
    tongue_t = ART_T - 0.1    # шип = толщина полотна минус 0.1 мм на клей
    t = []
    plate_t = thick - tongue_t

    def ring(z0, z1, out_w, out_h, win_w, win_h):
        ox0, oy0 = -out_w / 2, -out_h / 2
        ox1, oy1 = out_w / 2, out_h / 2
        ix0, iy0 = -win_w / 2, -win_h / 2
        ix1, iy1 = win_w / 2, win_h / 2
        r = []
        r += box(ox0, oy0, z0, ox1, iy0, z1)
        r += box(ox0, iy1, z0, ox1, oy1, z1)
        r += box(ox0, iy0, z0, ix0, iy1, z1)
        r += box(ix1, iy0, z0, ox1, iy1, z1)
        return r

    # шип: наружный размер чуть меньше посадочного окна нижней рамки
    t += ring(0, tongue_t, SEAT_W - 2 * CLEAR, SEAT_H - 2 * CLEAR, WIN_W, WIN_H)
    # плита
    t += ring(tongue_t, thick, OUT_W, OUT_H, WIN_W, WIN_H)
    return t


def frame_tris(thick):
    """Рамка = 4 бруска по периметру с окном WIN_W x WIN_H."""
    t = []

    def ring(z0, z1, win_w, win_h):
        ox0, oy0 = -OUT_W / 2, -OUT_H / 2
        ox1, oy1 = OUT_W / 2, OUT_H / 2
        ix0, iy0 = -win_w / 2, -win_h / 2
        ix1, iy1 = win_w / 2, win_h / 2
        t = []
        t += box(ox0, oy0, z0, ox1, iy0, z1)   # нижняя перекладина
        t += box(ox0, iy1, z0, ox1, oy1, z1)   # верхняя перекладина
        t += box(ox0, iy0, z0, ix0, iy1, z1)   # левая
        t += box(ix1, iy0, z0, ox1, iy1, z1)   # правая
        return t

    # Нижняя часть: снизу сквозное окно = размер полотна, сверху полочка 1 мм
    t += ring(0, thick - LEDGE_T, SEAT_W, SEAT_H)   # посадочное окно 38x89
    t += ring(thick - LEDGE_T, thick, WIN_W, WIN_H)  # полочка (окно 36x87)
    return t


def write_stl(path, tris, name=b'bead_frame'):
    with open(path, 'wb') as f:
        f.write(name.ljust(80, b'\0'))
        f.write(struct.pack('<I', len(tris)))
        for a, b, c in tris:
            u = tuple(b[i] - a[i] for i in range(3))
            w = tuple(c[i] - a[i] for i in range(3))
            n = (u[1]*w[2]-u[2]*w[1], u[2]*w[0]-u[0]*w[2], u[0]*w[1]-u[1]*w[0])
            ln = (n[0]**2 + n[1]**2 + n[2]**2) ** 0.5 or 1.0
            n = tuple(x/ln for x in n)
            f.write(struct.pack('<3f', *n))
            for p in (a, b, c):
                f.write(struct.pack('<3f', *p))
            f.write(struct.pack('<H', 0))
    print(f'{path}: {len(tris)} треугольников')


if __name__ == '__main__':
    print(f'Полотно: {ART_W}x{ART_H}x{ART_T}, окно полочки: {WIN_W}x{WIN_H}, наружный: {OUT_W}x{OUT_H}')

    write_stl('bead_frame_bottom.stl', frame_tris(THICK))
    write_stl('bead_frame_top.stl', top_frame_tris(THICK))
