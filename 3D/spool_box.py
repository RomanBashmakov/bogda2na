"""Коробка для хранения катушек ниток (печать на FDM).

Простой лоток как в референсе (коробка_для_проводов.stl): открытая сверху
коробка со сплошными вертикальными перегородками. Катушки стоят как книги:
ячейка шириной «толщина катушки + 2 мм», внутренние высота и глубина — под
самую большую катушку + 2 мм. Без посадок, стержней и модульности.

Запуск:
    python spool_box.py --cells 17x70,17x70,20x84 --out my.stl

Меши строятся вручную из призм-коробок (без булевых операций).

Все размеры в мм.
"""

import argparse
from collections import Counter

import numpy as np
import trimesh

ap = argparse.ArgumentParser(description="Коробка для катушек")
ap.add_argument("--cells", default="17x70",
                help="ячейки через запятую: толщинаxдиаметр, например 17x70,20x84")
ap.add_argument("--out", default=None, help="имя выходного STL (по умолчанию по размеру)")

# --- Параметры печати/конструкции (мм) ---
WALL = 1.6        # толщина стенок и перегородок (2 периметра сопла 0.4)
BASE = 1.6        # толщина дна
CLEAR = 2.0       # зазор вокруг катушки (по толщине и глубине)
MARGIN = 6.0      # насколько стенки выше половины катушки («чуть больше половины»)


def prism(poly, a0, a1, perm):
    """Замкнутая призма: полигон [(u,v), ...] CCW, вытянутый вдоль третьей
    оси от a0 до a1; perm = (ось u, ось v, ось w) индексы X/Y/Z."""
    n = len(poly)
    va, vb = [], []
    for u, v in poly:
        p = [0.0, 0.0, 0.0]
        p[perm[0]] = u
        p[perm[1]] = v
        p[perm[2]] = a0
        va.append(list(p))
        p[perm[2]] = a1
        vb.append(list(p))
    vertices = np.array(va + vb, dtype=float)
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces += [[i, j, j + n], [i, j + n, i + n]]
    for i in range(1, n - 1):
        faces += [[0, i + 1, i], [n, n + i, n + i + 1]]
    mesh = trimesh.Trimesh(vertices=vertices, faces=np.array(faces), process=True)
    assert mesh.is_watertight and mesh.is_volume, "призма не замкнута"
    return mesh


def box(x0, x1, y0, y1, z0, z1):
    """Замкнутый параллелепипед."""
    return prism([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0, z1, (0, 1, 2))


def build(cells):
    """cells: список (толщина, диаметр) слева направо. Список мешей.

    Ячейка шириной «толщина + CLEAR», глубиной «диаметр + CLEAR».
    Все стенки закрывают чуть больше половины катушки: высота = половина
    диаметра соседней катушки + MARGIN (катушка не выпадает, верх открыт).
    """
    half = [d / 2.0 + MARGIN for _, d in cells]     # высота ограждения ячейки
    wall_h = [BASE + h for h in half]               # от дна
    depth = max(d for _, d in cells) + CLEAR + 2 * WALL   # габарит по Y
    xs = [0.0]                                     # внутренняя грань левой стенки
    for t, _ in cells:
        xs.append(xs[-1] + t + CLEAR + WALL)        # следующая перегородка
    length = xs[-1] + WALL                         # габарит по X
    hmax = max(wall_h)

    parts = [box(0.0, length, 0.0, depth, 0.0, BASE)]              # дно
    parts.append(box(0.0, WALL, 0.0, depth, 0.0, wall_h[0]))       # левый торец
    parts.append(box(length - WALL, length, 0.0, depth, 0.0, wall_h[-1]))
    for x, h in zip(xs[1:-1], [max(a, b) for a, b in zip(half, half[1:])]):
        parts.append(box(x, x + WALL, 0.0, depth, 0.0, BASE + h))  # перегородки
    # передняя и задняя стенки (катушка не выпадает вперёд/назад)
    parts.append(box(0.0, length, 0.0, WALL, 0.0, hmax))
    parts.append(box(0.0, length, depth - WALL, depth, 0.0, hmax))
    return parts


def main():
    args = ap.parse_args()
    cells = []
    for c in args.cells.split(","):
        t, d = c.lower().split("x")
        cells.append((float(t), float(d)))
    parts = build(cells)
    for p in parts:
        assert p.is_watertight and p.is_volume
    mesh = trimesh.util.concatenate(parts)
    if args.out is None:
        cnt = Counter(cells)
        args.out = "spool_box_" + "_".join(
            f"{t:g}x{d:g}x{n:g}" for (t, d), n in sorted(cnt.items())) + ".stl"
    mesh.export(args.out)
    b = mesh.bounds
    print(f"Ячейки: {['%.0fx%.0f' % c for c in cells]}")
    print(f"Габарит: {b[1][0]:.1f} x {b[1][1]:.1f} x {b[1][2]:.1f} мм "
          f"(длина x глубина x высота)")
    print(f"Объём пластика: ~{mesh.volume / 1000:.0f} см³; "
          f"треугольников: {len(mesh.faces)}")
    print(f"STL сохранён: {args.out}")


if __name__ == "__main__":
    main()
