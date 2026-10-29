#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_opalubka.py — генератор опалубки: рамки, на которой собирается
бисерное полотно и которая остаётся его оформлением/упаковкой.

Две половинки под FDM-печать (бинарный STL, без зависимостей):

  нижняя  — дно-полочка со сквозным окном (полотно лежит на полочке,
            выступ = --ledge); по краю полотна — гребёнки-«стенки» из
            ровных вертикальных столбиков, идущие от края полотна до
            наружного края низа; столбики стоят В ПРОМЕЖУТКАХ между
            нитками, поэтому окошек ровно по числу ниток (рядов и
            прошивок); сверху столбики объединяет сплошная полка
            (--shelf-t). Иголка с ниткой прошивает окошко НАСКОЗЬ —
            за столбиками на высоте окошек ничего нет;
  верхняя — «негатив»: пластина с пальцем-прижимом и наружной
            юбкой-ключом на всю высоту сборки: юбка накрывает низ
            снаружи до самого стола, стык центрирует половинки.

Как собирать (нижняя половина лежит на столе, стол закрывает окно):
  1) горизонтальный ряд: иголка входит снаружи через окошко ЛЕВОЙ
     гребёнки (окошек = рядов, шаг = высота бисерины), на нитку
     нанизывается бисер ряда, иголка выходит через окошко ПРАВОЙ
     гребёнки — нитка заперта в окошках и никуда не денется;
  2) ряд за рядом с натягом; 3) вертикальная прошивка: нити проходят
     через окошки ВЕРХНЕЙ и НИЖНЕЙ гребёнок (окошек = числу прошивок,
     шаг = ширине бисерины); 4) хвосты ниток выходят наружу через
     окошки — подклеить/подрезать по вкусу; верхняя половинка
     надевается на низ: палец прижимает крайние бисерины (зазор
     прижима = толщине полотна), юбка накрывает низ снаружи + клей.

Окно сквозное в ОБЕИХ половинках — полотно «висит в воздухе» с двух сторон.

Запуск из папки со скриптом (или из веб-панели, вкладка «Опалубка»):
    python3 make_opalubka.py                    # 26×52 → полотно 38×90 мм
    python3 make_opalubka.py --cols 20 --rows 40 --border 5 --name ramka

Выход: out/<имя>_bottom.stl, out/<имя>_top.stl. Печать плашмя в ориентации
как в файле (низ — дном на стол, верх — лицом на стол), без поддержек
(полка над окошками — мостики шириной --slot ≈ 0.6 мм).
"""

import argparse
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BAD_NAME = re.compile(r"[^0-9A-Za-zА-Яа-яЁё._-]")

EPS = 1e-9


def build_parser():
    ap = argparse.ArgumentParser(
        description="Опалубка-рамка для сборки бисерного полотна (STL)")
    ap.add_argument("--cols", type=int, default=26,
                    help="бисерин в ряду (ширина полотна), по умолчанию 26")
    ap.add_argument("--rows", type=int, default=52,
                    help="рядов (высота полотна), по умолчанию 52")
    ap.add_argument("--bead-w", type=float, default=1.4615,
                    help="ширина бисерины, мм = шаг верхней/нижней гребёнки")
    ap.add_argument("--bead-h", type=float, default=1.7308,
                    help="высота бисерины, мм = шаг левой/правой гребёнки")
    ap.add_argument("--fabric-t", type=float, default=1.73,
                    help="толщина полотна = зазор прижима, мм")
    ap.add_argument("--tooth-h", type=float, default=1.3,
                    help="высота столбиков гребёнки вместе с полкой, мм")
    ap.add_argument("--shelf-t", type=float, default=0.5,
                    help="толщина объединяющей полки над столбиками, мм "
                         "(окошко = tooth_h − shelf_t в высоту)")
    ap.add_argument("--ledge", type=float, default=1.0,
                    help="выступ полочки ПОД полотно, мм")
    ap.add_argument("--border", type=float, default=4.2,
                    help="толщина видимой рамки от края окна, мм "
                         "(включает юбку-ключ верхней половинки)")
    ap.add_argument("--slot", type=float, default=0.8,
                    help="ширина окошка между столбиками, мм "
                         "(столбик = шаг − окошко)")
    ap.add_argument("--clearance", type=float, default=0.15,
                    help="посадочный зазор пальца и юбки, мм")
    ap.add_argument("--base-t", type=float, default=2.0,
                    help="толщина дна-полочки нижней половинки, мм")
    ap.add_argument("--top-t", type=float, default=1.0,
                    help="толщина пластины верхней половинки, мм")
    ap.add_argument("--finger", type=float, default=0.7,
                    help="высота пальца-прижима, мм")
    ap.add_argument("--wall", type=float, default=1.2,
                    help="толщина юбки-ключа верхней половинки, мм")
    ap.add_argument("--name", default="opalubka",
                    help="имя файлов (без расширения)")
    ap.add_argument("--out-dir", default=None,
                    help="куда класть STL (по умолчанию out/ рядом со скриптом)")
    return ap


class Params:

    def __init__(self, a):
        for key in ("cols", "rows", "bead_w", "bead_h", "fabric_t", "tooth_h",
                    "shelf_t", "ledge", "border", "slot", "clearance",
                    "base_t", "top_t", "finger", "wall"):
            setattr(self, key, getattr(a, key))
        # производные размеры (всё от центра полотна)
        self.fw2 = self.cols * self.bead_w / 2.0    # край полотна по X
        self.fh2 = self.rows * self.bead_h / 2.0    # край полотна по Y
        self.wx2 = self.fw2 - self.ledge            # край окна (меньше полотна)
        self.wy2 = self.fh2 - self.ledge
        self.ox2 = self.wx2 + self.border           # наружный габарит сборки
        self.oy2 = self.wy2 + self.border
        # наружный край НИЗА: дальше — зазор посадки и юбка верха (ключ-стык)
        self.bxo = self.ox2 - self.wall - self.clearance
        self.byo = self.oy2 - self.wall - self.clearance
        # глубина гребёнки: от края полотна до наружного края низа
        self.td = self.bxo - self.fw2
        self.zb = self.base_t                       # уровень полочки
        self.Hb = self.base_t + self.fabric_t + self.finger  # высота низа
        # палец-прижим верха: его наружная грань (внутри гребёнок)
        self.s2 = self.ox2 - 2 * self.wall - 2 * self.clearance
        self.t2 = self.oy2 - 2 * self.wall - 2 * self.clearance

    def validate(self):
        err = []
        if self.cols < 1 or self.rows < 1:
            err.append("cols и rows — целые >= 1")
        if min(self.bead_w, self.bead_h) <= self.slot:
            err.append("окошко %.2f мм не меньше шага бисерины — "
                       "столбиков не останется" % self.slot)
        if self.bead_w - self.slot < 0.4 or self.bead_h - self.slot < 0.4:
            err.append("столбик уже 0.4 мм (шаг минус окошко) — "
                       "не напечатается")
        if self.tooth_h >= self.fabric_t - 0.2:
            err.append("высота столбиков %.2f мм: нужно минимум на 0.2 мм "
                       "меньше толщины полотна %.2f мм, иначе прижим не "
                       "закроется" % (self.tooth_h, self.fabric_t))
        if self.slot < 0.45 or self.tooth_h - self.shelf_t < 0.45:
            err.append("окошко %.2f x %.2f мм — иголка не пройдёт, нужно "
                       "хотя бы 0.45 x 0.45"
                       % (self.slot, self.tooth_h - self.shelf_t))
        if not 0.25 <= self.shelf_t <= self.tooth_h - 0.45:
            err.append("толщина полки %.2f мм: нужно 0.25..%.2f (тоньше не "
                       "напечатается, толще — окошко мало)"
                       % (self.shelf_t, self.tooth_h - 0.45))
        if self.td < 0.8:
            err.append("рамка слишком узкая: на гребёнку остаётся %.2f мм "
                       "(минимум 0.8) — увеличьте --border" % self.td)
        if self.wx2 <= 0 or self.wy2 <= 0:
            err.append("выступ полочки больше половины полотна — окно "
                       "выродилось")
        if self.ledge < 0.2:
            err.append("выступ полочки меньше 0.2 мм — полотно не на чём "
                       "держать")
        if min(self.base_t, self.top_t) < 0.4:
            err.append("толщины пластин меньше 0.4 мм — не напечатается")
        if self.finger < 0.3:
            err.append("высота пальца меньше 0.3 мм — прижим не держит")
        if self.wall < 0.5:
            err.append("юбка-ключ тоньше 0.5 мм — не напечатается")
        if not 0 <= self.clearance <= 0.5:
            err.append("зазор посадки — от 0 до 0.5 мм")
        if self.s2 - self.fw2 < 0.1 or self.t2 - self.fh2 < 0.1:
            err.append("рамка слишком узкая: палец-прижим верха наезжает "
                       "на окно — увеличьте --border")
        if err:
            raise ValueError("; ".join(err))

# --- геометрия: всё брусками (x0, x1, y0, y1, z0, z1) ---

def ring(add, ix2, iy2, ox2, oy2, z0, z1):
    """Кольцо вокруг прямоугольного окна: 4 полосы без пересечений."""
    add(-ox2, ox2, -oy2, -iy2, z0, z1)
    add(-ox2, ox2, iy2, oy2, z0, z1)
    add(-ox2, -ix2, -iy2, iy2, z0, z1)
    add(ix2, ox2, -iy2, iy2, z0, z1)


def pegs(centers, width, lo, hi):
    """Столбики (a, b) с центрами centers и толщиной width, обрезанные
    до [lo, hi] — окошки между ними попадают точно на нитки."""
    out = []
    for c in centers:
        a, b = max(c - width / 2.0, lo), min(c + width / 2.0, hi)
        if b - a > EPS:
            out.append((a, b))
    return out


def boxes_bottom(p):
    """Нижняя половина: дно-полочка вокруг окна + гребёнки-«стенки».

    Гребёнка — ровные вертикальные столбики от края полотна до наружного
    края низа; столбики стоят между нитками (их на 1 больше, чем ниток),
    поэтому окошек ровно по числу ниток и они точно на центрах ниток.
    Сверху столбики объединяет полка shelf_t — окошко замкнуто с четырёх
    сторон (столбики + дно + полка): нитка запирается в окошке, а
    иголка проходит насквозь — за столбиками ничего нет."""
    boxes = []

    def add(x0, x1, y0, y1, z0, z1):
        boxes.append((x0, x1, y0, y1, z0, z1, 0.0, 0.0))

    # дно вокруг окна: его верх = полочка, на которой лежит полотно.
    # Дно идёт до полного наружного края низа (bxo, byo): дальше при
    # сборке юбка верхней половинки (ключ-стык) с зазором clearance.
    ring(add, p.wx2, p.wy2, p.bxo, p.byo, 0.0, p.zb)

    # центры столбиков: В ПРОМЕЖУТКАХ между нитками.
    # боковые гребёнки (лево/право): rows+1 столбиков -> rows окошек
    # ровно на центрах рядов; верх/низ: cols+1 -> cols окошек прошивки.
    rowc = [-p.fh2 + k * p.bead_h for k in range(p.rows + 1)]
    colc = [-p.fw2 + k * p.bead_w for k in range(p.cols + 1)]

    zt0 = p.zb                           # столбики стоят на полочке...
    zt1 = p.zb + p.tooth_h - p.shelf_t   # ...и до низа полки
    zs0, zs1 = zt1, p.zb + p.tooth_h     # полка сверху, высотой shelf_t

    # боковые гребёнки: полоса от края полотна до края низа, полка по Y
    # на всю ширину (накрывает и углы); столбики — в пределах полотна,
    # углы — сплошные блоки (там ниток нет).
    for x0, x1 in ((-p.bxo, -p.fw2), (p.fw2, p.bxo)):
        for a, b in pegs(rowc, p.bead_h - p.slot, -p.fh2, p.fh2):
            add(x0, x1, a, b, zt0, zt1)
        add(x0, x1, -p.byo, -p.fh2, zt0, zt1)   # нижний угол
        add(x0, x1, p.fh2, p.byo, zt0, zt1)     # верхний угол
        add(x0, x1, -p.byo, p.byo, zs0, zs1)    # объединяющая полка

    # верхняя/нижняя гребёнки: столбики между краями полотна по X
    # (углы заняты боковыми гребёнками), своя полка над ними.
    for y0, y1 in ((-p.byo, -p.fh2), (p.fh2, p.byo)):
        for a, b in pegs(colc, p.bead_w - p.slot, -p.fw2, p.fw2):
            add(a, b, y0, y1, zt0, zt1)
        add(-p.fw2, p.fw2, y0, y1, zs0, zs1)    # объединяющая полка
    return boxes


def boxes_top(p):
    """Верхняя половина (печать: пластиной на стол): пластина с окном,
    палец-прижим и наружная юбка-ключ на всю высоту сборки — при сборке
    юбка накрывает низ снаружи до стола, верх «поглощает» нижнюю
    половинку (см. эскиз «стык» в корне проекта)."""
    boxes = []
    twx2, twy2 = p.wx2 + p.clearance, p.wy2 + p.clearance  # окно верха
    fs2, ft2 = p.s2 - p.clearance, p.t2 - p.clearance      # палец снаружи
    kx2, ky2 = p.ox2 - p.wall, p.oy2 - p.wall              # юбка изнутри

    def add(x0, x1, y0, y1, z0, z1, dx=0.0, dy=0.0):
        boxes.append((x0, x1, y0, y1, z0, z1, dx, dy))

    ring(add, twx2, twy2, p.ox2, p.oy2, 0.0, p.top_t)             # пластина
    ring(add, twx2, twy2, fs2, ft2, p.top_t, p.top_t + p.finger)  # палец
    # юбка-ключ: встаёт поверх пластины, при сборке уходит вниз до стола
    ring(add, kx2, ky2, p.ox2, p.oy2, p.top_t, p.top_t + p.Hb)
    return boxes
# --- бинарный STL из брусков (в т.ч. наклонных) ---

def solid_triangles(x0, x1, y0, y1, z0, z1, dx=0.0, dy=0.0):
    """Параллелепипед: нижняя грань (x0..x1, y0..y1) на z0, верхняя —
    такая же, сдвинутая на (dx, dy), на z1. 6 плоских граней -> 12 тр-ков."""
    b = ((x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0))
    t = ((x0 + dx, y0 + dy, z1), (x1 + dx, y0 + dy, z1),
         (x1 + dx, y1 + dy, z1), (x0 + dx, y1 + dy, z1))
    quads = (
        (b[0], b[3], b[2], b[1]),   # низ
        (t[0], t[1], t[2], t[3]),   # верх
        (b[0], b[1], t[1], t[0]),   # y0
        (b[3], t[3], t[2], b[2]),   # y1
        (b[0], t[0], t[3], b[3]),   # x0
        (b[1], b[2], t[2], t[1]),   # x1
    )
    tris = []
    for q in quads:
        tris.append((q[0], q[1], q[2]))
        tris.append((q[0], q[2], q[3]))
    return tris


def mesh_check(tris):
    """Замкнутость набора тел: рёбер без пары (нечётное число граней)
    быть не должно. Совпадающие грани соседних брусков (union тел) дают
    чётное число и для печати нормальны."""
    edges = {}

    def key(v):
        return (round(v[0], 5), round(v[1], 5), round(v[2], 5))

    for t in tris:
        ks = [key(v) for v in t]
        for a, b in ((0, 1), (1, 2), (2, 0)):
            e = tuple(sorted((ks[a], ks[b])))
            edges[e] = edges.get(e, 0) + 1
    return sum(1 for n in edges.values() if n % 2)


def write_stl(path, boxes, title):
    for x0, x1, y0, y1, z0, z1, dx, dy in boxes:
        if not (x1 - x0 > 1e-4 and y1 - y0 > 1e-4 and z1 - z0 > 1e-4):
            raise ValueError("вырожденный брусок: %r"
                             % ((x0, x1, y0, y1, z0, z1, dx, dy),))
    tris = []
    for b in boxes:
        tris += solid_triangles(*b)
    bad = mesh_check(tris)
    if bad:
        raise ValueError("рёбер без пары: %d" % bad)
    with open(path, "wb") as f:
        f.write(title.encode("ascii", "replace")[:80].ljust(80, b"\0"))
        f.write(struct.pack("<I", len(tris)))
        pack = struct.Struct("<12fH").pack
        for a, b, c in tris:
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            length = (nx * nx + ny * ny + nz * nz) ** 0.5 or 1.0
            f.write(pack(nx / length, ny / length, nz / length,
                         a[0], a[1], a[2], b[0], b[1], b[2],
                         c[0], c[1], c[2], 0))
    return len(tris)


def bbox(boxes):
    xs = [v for b in boxes for v in (b[0], b[1], b[0] + b[6], b[1] + b[6])]
    ys = [v for b in boxes for v in (b[2], b[3], b[2] + b[7], b[3] + b[7])]
    zs = [v for b in boxes for v in (b[4], b[5])]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def main():
    a = build_parser().parse_args()
    a.name = BAD_NAME.sub("_", a.name.strip()) or "opalubka"
    p = Params(a)
    try:
        p.validate()
    except ValueError as e:
        print("ОШИБКА: " + str(e), file=sys.stderr)
        return 2
    out_dir = a.out_dir or os.path.join(HERE, "out")
    os.makedirs(out_dir, exist_ok=True)

    print("ПОЛОТНО: %d x %d бисерин, шаг %.4f x %.4f мм -> %.1f x %.1f мм"
          % (p.cols, p.rows, p.bead_w, p.bead_h, 2 * p.fw2, 2 * p.fh2))
    print("ОКНО: %.1f x %.1f мм (выступ полочки %.2f мм с каждой стороны)"
          % (2 * p.wx2, 2 * p.wy2, p.ledge))
    print("ГАБАРИТ: %.1f x %.1f мм, глубина сборки %.2f мм"
          % (2 * p.ox2, 2 * p.oy2, p.Hb + p.top_t))
    print("СТЫК: юбка верха накрывает низ снаружи до стола (зазор %.2f); "
          "низ %.1f x %.1f, верх и сборка %.1f x %.1f мм"
          % (p.clearance, 2 * p.bxo, 2 * p.byo, 2 * p.ox2, 2 * p.oy2))
    print("ГРЕБЁНКИ: боковые %d столбиков -> %d окошек (= рядам, шаг "
          "%.4f), верх/низ %d столбиков -> %d окошек (= прошивкам, шаг "
          "%.4f) — окошки точно на центрах ниток"
          % (p.rows + 1, p.rows, p.bead_h,
             p.cols + 1, p.cols, p.bead_w))
    print("ОКОШКИ: %.2f x %.2f мм (ширина x высота), глубина столбиков "
          "%.2f, полка сверху %.2f мм — иголка проходит НАСКОЗЬ, нитка "
          "запирается в окошке"
          % (p.slot, p.tooth_h - p.shelf_t, p.td, p.shelf_t))
    print("ХВОСТЫ: выходят наружу через те же окошки — подклеить/"
          "подрезать по вкусу")

    for half, build in (("bottom", boxes_bottom), ("top", boxes_top)):
        boxes = build(p)
        path = os.path.join(out_dir, "%s_%s.stl" % (a.name, half))
        tris = write_stl(path, boxes, "opalubka %s %s" % (a.name, half))
        (x0, y0, z0), (x1, y1, z1) = bbox(boxes)
        print("ФАЙЛ: %s — %d брусков, %d треугольников, замкнуто, "
              "%.1f x %.1f x %.1f мм, %.1f КБ"
              % (os.path.relpath(path, HERE), len(boxes), tris,
                 x1 - x0, y1 - y0, z1 - z0, os.path.getsize(path) / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())

