"""Сита-трафареты для массовой засыпки бисера в матрицу STL_3d_matrix.

Схема painter (JSON: cols/rows/colors/cells) → по одному STL на номер
цвета: тонкая пластина (0.4 мм) с квадратными отверстиями 3.2×3.2 мм
в клетках этого цвета. Шаг сетки 3.75 мм — как у матрицы.

Совмещение: сито прижимается к окантовке-ключу матрицы (лента 2 мм
толщиной у левого и верхнего края). Первая линия сетки сита — в 1 мм
от его края, поэтому ячейки совпадают клетка-в-клетку.

CLI:  python3 make_sieve.py painter/schemes/koi.json [выходная_папка]
API: make_sieves(data, out_dir, name) -> список имён файлов.
"""
import json
import sys
from pathlib import Path

import numpy as np
import trimesh

# --- Параметры (мм), согласованы с matrix_square.py ---
SPACING = 3.75          # шаг центров ячеек матрицы
HOLE = 3.2              # сторона квадратного отверстия (ячейка 3.0 + люфт)
THICK = 0.4             # толщина сита: 4 слоя по 0.1 мм
MARGIN = 1.0            # боковая стенка сита вокруг крайних ячеек

HOLE_TOL = 0.6          # запас высоты призмы, чтобы проткнуть пластину


def _sieve_mesh(cells, cols, rows, color):
    """Меш сита для одного номера цвета; None, если бисерин нет."""
    idx = [k for k, v in enumerate(cells) if v == color]
    if not idx:
        return None
    # габарит сита: рамка MARGIN + клетки шагом SPACING
    w = 2 * MARGIN + cols * SPACING
    h = 2 * MARGIN + rows * SPACING
    plate = trimesh.creation.box(extents=[w, h, THICK])
    prism = trimesh.creation.box(
        extents=[HOLE, HOLE, THICK + HOLE_TOL])
    x0 = -w / 2.0 + MARGIN + SPACING / 2.0   # центр первой ячейки
    y0 = -h / 2.0 + MARGIN + SPACING / 2.0
    parts = []
    for k in idx:
        c, r = k % cols, k // cols            # ряд 0 — верх
        T = np.eye(4)
        T[:3, 3] = [x0 + c * SPACING, y0 + (rows - 1 - r) * SPACING, 0.0]
        parts.append(prism.copy().apply_transform(T))
    holes = trimesh.util.concatenate(parts)
    return trimesh.boolean.difference([plate, holes], engine='manifold',
                                      process=True)


def make_sieves(data, out_dir, name):
    """data — схема painter (словарь); пишет <name>_sieve_<№>.stl в out_dir."""
    cols, rows = int(data["cols"]), int(data["rows"])
    cells = data["cells"]
    used = sorted({v for v in cells if isinstance(v, int) and v >= 0})
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for color in used:
        mesh = _sieve_mesh(cells, cols, rows, color)
        if mesh is None:
            continue
        fname = f"{name}_sieve_{color}.stl"
        mesh.export(out / fname)
        files.append(fname)
        print(f"{fname}: {sum(1 for v in cells if v == color)} бисерин, "
              f"габарит {mesh.extents[0]:.1f} x {mesh.extents[1]:.1f} мм")
    return files


def main():
    if len(sys.argv) < 2:
        sys.exit("Использование: make_sieve.py схема.json [выходная_папка]")
    scheme = Path(sys.argv[1])
    data = json.loads(scheme.read_text(encoding="utf-8"))
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else scheme.parent / "out"
    make_sieves(data, out_dir, scheme.stem)


if __name__ == "__main__":
    main()
