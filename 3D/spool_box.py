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
HOLE_D = 10.0     # диаметр перфорации
HOLE_PITCH = 14.0  # шаг решётки отверстий
HOLE_EDGE = 3.5   # минимальная перемычка от отверстия до кромки
SEG = 24          # сегментов аппроксимации окружности перфорации


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
    if not mesh.is_volume:        # нечётная перестановка осей — нормали внутрь
        mesh.invert()
    assert mesh.is_watertight and mesh.is_volume, "призма не замкнута"
    return mesh


def box(x0, x1, y0, y1, z0, z1):
    """Замкнутый параллелепипед."""
    return prism([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], z0, z1, (0, 1, 2))


def _subtract(ivals, lo, hi):
    out = []
    for a, b in ivals:
        if hi <= a or lo >= b:
            out.append((a, b))
            continue
        if a < lo:
            out.append((a, min(b, lo)))
        if b > hi:
            out.append((max(a, hi), b))
    return out


def perforation(u0, u1, v0, v1):
    """Решётка круглых отверстий (uc, vc, r) в прямоугольнике [u0,u1]x[v0,v1]:
    ряды по v со сдвигом через ряд, отступ HOLE_EDGE от кромок."""
    r = HOLE_D / 2.0
    holes = []
    row = 0
    v = v0 + HOLE_EDGE + r
    while v + r + HOLE_EDGE <= v1 + 1e-9:
        shift = (HOLE_PITCH / 2.0) * (row % 2)
        u = u0 + HOLE_EDGE + r + shift
        while u + r + HOLE_EDGE <= u1 + 1e-9:
            holes.append((u, v, r))
            u += HOLE_PITCH
        v += HOLE_PITCH
        row += 1
    return holes


def holed_plate(u0, u1, v0, v1, holes=(), a0=0.0, a1=WALL, perm=(0, 1, 2)):
    """Плита-призма с круглыми отверстиями: полосами по v, в каждой полосе
    материал = интервалы по u минус хорды отверстий (консервативно)."""
    if not holes:
        return [prism([(u0, v0), (u1, v0), (u1, v1), (u0, v1)], a0, a1, perm)]
    r = HOLE_D / 2.0
    cuts = [v0, v1]
    for _, vc, _ in holes:
        cuts += list(np.linspace(vc - r, vc + r, SEG + 1))
    cuts = sorted(c for c in cuts if v0 - 1e-9 < c < v1 + 1e-9)
    meshes = []
    for va, vb in zip(cuts[:-1], cuts[1:]):
        if vb - va < 1e-6:
            continue
        ivals = [(u0, u1)]
        for uc, vc, _ in holes:
            wa = np.sqrt(max(r * r - (va - vc) ** 2, 0.0)) if abs(va - vc) <= r else 0.0
            wb = np.sqrt(max(r * r - (vb - vc) ** 2, 0.0)) if abs(vb - vc) <= r else 0.0
            w = max(wa, wb)
            if w > 1e-6:
                ivals = _subtract(ivals, uc - w, uc + w)
        for ia, ib in ivals:
            if ib - ia < 1e-6:
                continue
            meshes.append(prism([(ia, va), (ib, va), (ib, vb), (ia, vb)], a0, a1, perm))
    return meshes


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

    parts = []
    # дно
    parts += holed_plate(0.0, length, 0.0, depth, perforation(0.0, length, 0.0, depth),
                         0.0, BASE, (0, 1, 2))
    # торцы и перегородки (u=y, v=z)
    wx = [(0.0, WALL, wall_h[0]), (length - WALL, length, wall_h[-1])]
    wx += [(x, x + WALL, BASE + max(a, b))
           for x, a, b in zip(xs[1:-1], half, half[1:])]
    for x0, x1, h in wx:
        parts += holed_plate(0.0, depth, BASE, h, perforation(0.0, depth, BASE, h),
                             x0, x1, (1, 2, 0))
    # передняя и задняя стенки (u=x, v=z)
    for y0, y1 in ((0.0, WALL), (depth - WALL, depth)):
        parts += holed_plate(0.0, length, BASE, hmax, perforation(0.0, length, BASE, hmax),
                             y0, y1, (0, 2, 1))
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
