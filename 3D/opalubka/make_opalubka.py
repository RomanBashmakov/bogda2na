#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_opalubka.py — генератор опалубки: рамки, на которой собирается
бисерное полотно и которая остаётся его оформлением/упаковкой.

Две половинки под FDM-печать (бинарный STL, без зависимостей):

  нижняя  — пластина со сквозным окном; по периметру окна карман-«ступенька»
            с полочкой; по краю полочки — зубья-колышки точно на центрах
            ниток, наклонённые ОТ полотна; за колышками до стенки кармана —
            канавка, в которую надевается нить (наклонённая вершина
            нависает над канавкой и держит нитку); внешняя стенка — с
            углублением под хвосты по всему периметру и сквозными
            ПРОРЕЗЯМИ (по 2 на сторону, ровно на первой и последней нити):
            через них нить заходит в плетение и выходит;
  верхняя — «негатив»: пластина с пальцем-прижимом (палец входит в карман)
            и наружной юбкой-ключом на всю высоту сборки: юбка накрывает
            низ снаружи до самого стола, верх «поглощает» нижнюю половину;
            стык центрирует половинки и прячет шов.

Как собирать (нижняя половина лежит на столе, стол закрывает окно):
  1) нить заводится СНАРУЖИ через прорезь в стенке; на неё нанизывается
     бисер ряда; нить надевается на колышки ЛЕВОЙ и ПРАВОЙ гребёнок,
     хвост остаётся в углублении вдоль внешней стенки (шаг = высота
     бисерины, колышков = рядов);
  2) ряд за рядом, натягивая от закреплённого хвоста (капля суперклея
     на хвост в углублении — якорь); 3) вертикальная прошивка между
     бисеринами: её нити надеваются на колышки ВЕРХНЕЙ и НИЖНЕЙ гребёнок
     (шаг = ширина бисерины, колышков = бисерин в ряду + 1, включая
     2 краевые), концы — так же через прорези в углубление;
  4) хвосты в углублении подклеиваются, верхняя половинка надевается
     на низ: палец входит в карман, юбка накрывает стенку снаружи
     (ключ-стык), прижимаются крайние бисерины (они лежат на полочке,
     зазор прижима = толщине полотна); посадка плотная + клей.

Окно сквозное в ОБЕИХ половинках — полотно «висит в воздухе» с двух сторон.

Запуск из папки со скриптом (или из веб-панели, вкладка «Опалубка»):
    python3 make_opalubka.py                    # 26×52 → полотно 38×90 мм
    python3 make_opalubka.py --cols 20 --rows 40 --border 4 --name ramka

Выход: out/<имя>_bottom.stl, out/<имя>_top.stl. Печать плашмя в ориентации
как в файле (низ — дном на стол, верх — лицом на стол), без поддержек.
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
    ap.add_argument("--tooth-h", type=float, default=1.0,
                    help="высота зубчиков гребёнки, мм")
    ap.add_argument("--tooth-lean", type=float, default=0.25,
                    help="наклон зубьев ОТ полотна: сдвиг вершины от "
                         "основания, мм (0 — прямые зубья); вершина "
                         "нависает над канавкой и держит нитку")
    ap.add_argument("--ledge", type=float, default=1.0,
                    help="выступ полочки ПОД полотно, мм")
    ap.add_argument("--border", type=float, default=3.8,
                    help="толщина видимой рамки от края окна, мм "
                         "(включает юбку-ключ верхней половинки)")
    ap.add_argument("--slot", type=float, default=0.6,
                    help="зазор между зубьями, мм (зуб = шаг − зазор)")
    ap.add_argument("--channel", type=float, default=0.6,
                    help="канавка между зубьями и стенкой кармана, куда "
                         "надевается нить, мм")
    ap.add_argument("--clearance", type=float, default=0.15,
                    help="посадочный зазор пальца и окна, мм")
    ap.add_argument("--base-t", type=float, default=0.7,
                    help="толщина дна под полочкой, мм")
    ap.add_argument("--top-t", type=float, default=1.0,
                    help="толщина пластины верхней половинки, мм")
    ap.add_argument("--finger", type=float, default=0.7,
                    help="высота пальца-прижима, мм")
    ap.add_argument("--wall", type=float, default=0.6,
                    help="толщина наружной стенки низа и юбки-ключа "
                         "верха, мм")
    ap.add_argument("--tail-groove", type=float, default=0.2,
                    help="углубление вдоль внешней стенки, куда ложатся "
                         "и подклеиваются хвосты ниток, мм")
    ap.add_argument("--name", default="opalubka",
                    help="имя файлов (без расширения)")
    ap.add_argument("--out-dir", default=None,
                    help="куда класть STL (по умолчанию out/ рядом со скриптом)")
    return ap


class Params:

    def __init__(self, a):
        for key in ("cols", "rows", "bead_w", "bead_h", "fabric_t", "tooth_h",
                    "tooth_lean", "ledge", "border", "slot", "channel",
                    "clearance", "base_t", "top_t", "finger", "wall",
                    "tail_groove"):
            setattr(self, key, getattr(a, key))
        # производные размеры (всё от центра полотна)
        self.fw2 = self.cols * self.bead_w / 2.0    # край полотна по X
        self.fh2 = self.rows * self.bead_h / 2.0    # край полотна по Y
        self.wx2 = self.fw2 - self.ledge            # край окна (меньше полотна)
        self.wy2 = self.fh2 - self.ledge
        self.ox2 = self.wx2 + self.border           # наружный габарит
        self.oy2 = self.wy2 + self.border
        # стенка низа изнутри: за ней ещё стенка, зазор и юбка верха
        # (ключ-стык — юбка накрывает низ снаружи)
        self.s2 = self.ox2 - 2 * self.wall - self.clearance
        self.t2 = self.oy2 - 2 * self.wall - self.clearance
        # глубина зуба: карман (от края полотна до стенки) минус канавка
        self.td = (self.border - 2 * self.wall - self.clearance
                   - self.ledge - self.channel)
        self.zb = self.base_t                       # уровень полочки
        self.Hb = self.base_t + self.fabric_t + self.finger  # высота низа
        # хвосты ниток: стенка над углублением тоньше — наружная грань
        # утоплена на tail_groove, хвосты лежат на кромке дна и клеятся
        self.gw = self.wall - self.tail_groove      # стенка над углублением
        self.sw2 = self.s2 + self.gw                # наружная грань стенки
        self.st2 = self.t2 + self.gw

    def validate(self):
        err = []
        if self.cols < 1 or self.rows < 1:
            err.append("cols и rows — целые >= 1")
        if min(self.bead_w, self.bead_h) <= self.slot:
            err.append("зазор между зубьями %.2f мм не меньше шага "
                       "бисерины — зубьев не останется" % self.slot)
        if self.bead_w - self.slot < 0.4 or self.bead_h - self.slot < 0.4:
            err.append("зуб уже 0.4 мм (шаг минус зазор) — не напечатается")
        if self.tooth_h >= self.fabric_t - 0.2:
            err.append("высота зубчиков %.2f мм: нужно минимум на 0.2 мм "
                       "меньше толщины полотна %.2f мм, иначе прижим не "
                       "закроется" % (self.tooth_h, self.fabric_t))
        if self.channel < 0.45:
            err.append("канавка за зубьями %.2f мм — нитка не пройдёт, "
                       "нужно хотя бы 0.45 мм" % self.channel)
        if self.td < 0.5:
            err.append("рамка слишком узкая: на карман не хватает места "
                       "под зуб (минимум 0.5 мм) и канавку %.2f мм — "
                       "увеличьте --border" % self.channel)
        lean_max = min(self.tooth_h, max(self.channel - 0.1, 0.0))
        if not 0 <= self.tooth_lean <= lean_max:
            err.append("наклон зубьев %.2f мм: нужно 0..%.2f мм (не круче "
                       "45° и с запасом до стенки — иначе нитка не пролезет "
                       "в канавку)" % (self.tooth_lean, lean_max))
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
            err.append("стенка кармана меньше 0.5 мм — не напечатается")
        if not 0 <= self.clearance <= 0.5:
            err.append("зазор посадки — от 0 до 0.5 мм")
        if not 0 <= self.tail_groove <= self.wall - 0.35:
            err.append("углубление под хвосты %.2f мм: нужно 0..%.2f "
                       "(стенка над углублением тоньше 0.35 мм не "
                       "напечатается)" % (self.tail_groove,
                                           self.wall - 0.35))
        cutx = self.sw2 - self.fw2 - self.slot / 2.0              # короткие
        cuty = self.t2 - (self.fh2 - self.bead_h / 2.0) - self.slot / 2.0
        if min(cutx, cuty) < 0.3:
            err.append("для прорезей под хвосты не хватает %.2f мм "
                       "стенки — увеличьте --border"
                       % (0.3 - min(cutx, cuty)))
        if err:
            raise ValueError("; ".join(err))

# --- геометрия: всё брусками (x0, x1, y0, y1, z0, z1, dx, dy) ---

def ring(add, ix2, iy2, ox2, oy2, z0, z1):
    """Кольцо вокруг прямоугольного окна: 4 полосы без пересечений.
    dx/dy в бруске — сдвиг верхней грани (наклон зубьев)."""
    add(-ox2, ox2, -oy2, -iy2, z0, z1, 0.0, 0.0)
    add(-ox2, ox2, iy2, oy2, z0, z1, 0.0, 0.0)
    add(-ox2, -ix2, -iy2, iy2, z0, z1, 0.0, 0.0)
    add(ix2, ox2, -iy2, iy2, z0, z1, 0.0, 0.0)


def pegs(centers, width, lo, hi):
    """Колышки (a, b) с центрами centers и толщиной width, обрезанные
    до [lo, hi] — по одному на каждую нить."""
    out = []
    for c in centers:
        a, b = max(c - width / 2.0, lo), min(c + width / 2.0, hi)
        if b - a > EPS:
            out.append((a, b))
    return out


def boxes_bottom(p):
    """Нижняя половина: дно вокруг окна + стенка кармана + зубья-колышки.
    Колышки стоят точно на центрах ниток у края полотна и наклонены ОТ
    полотна (--tooth-lean); за ними до стенки кармана остаётся канавка,
    в которую надевается нить: наклонённая вершина нависает над канавкой
    крючком и не даёт нитке соскочить."""
    boxes = []

    def add(x0, x1, y0, y1, z0, z1, dx=0.0, dy=0.0):
        boxes.append((x0, x1, y0, y1, z0, z1, dx, dy))

    # дно вокруг окна: его верх и есть полочка. Наружная кромка дна
    # выступает за стенку на tail_groove — этот уступ по всему периметру
    # и есть «посадка» для хвостов: на него ложатся выведенные через
    # прорези концы ниток (сверху капается супер-клей, до закрытия).
    # Наружную сторону стенки при сборке накрывает юбка верхней
    # половинки (ключ-стык), поэтому низ заканчивается на s2+wall.
    bw2, bt2 = p.s2 + p.wall, p.t2 + p.wall
    ring(add, p.wx2, p.wy2, bw2, bt2, 0.0, p.zb)

    # центры ниток: ряды (горизонтальные нити) и прошивка
    # (вертикальные, включая 2 краевые по краям полотна)
    rowc = [-p.fh2 + p.bead_h / 2.0 + k * p.bead_h for k in range(p.rows)]
    colc = [-p.fw2 + k * p.bead_w for k in range(p.cols + 1)]

    # стенка над дном: наружная грань утоплена на tail_groove —
    # углубление под хвосты по всему периметру; в каждой стенке по 2
    # сквозные прорези шириной slot, РОВНО на первой и последней нити
    # этой стороны, от полочки до верха (см. эскиз «прорези» в корне):
    # через них нить заходит в плетение с натягом и выходит в конце
    def wall(x0, x1, y0, y1, cuts, vertical):
        """Полоса стенки, разрезанная прорезями шириной slot с центрами
        cuts вдоль длинной стороны (vertical — режем по Y): интервал
        прорези пропускается, стенка — это сегменты МЕЖДУ прорезями."""
        a0, a1 = (y0, y1) if vertical else (x0, x1)
        segs, cur = [], a0
        for c in sorted(cuts):
            lo, hi = c - p.slot / 2.0, c + p.slot / 2.0
            if cur < lo and hi < a1:
                segs.append((cur, lo))
                cur = hi
        segs.append((cur, a1))
        for u, v in segs:
            if v - u > EPS:
                if vertical:
                    add(x0, x1, u, v, p.zb, p.Hb)
                else:
                    add(u, v, y0, y1, p.zb, p.Hb)

    rows_cut, cols_cut = (rowc[0], rowc[-1]), (colc[0], colc[-1])
    wall(-p.sw2, -p.s2, -p.t2, p.t2, rows_cut, True)      # левая
    wall(p.s2, p.sw2, -p.t2, p.t2, rows_cut, True)        # правая
    wall(-p.sw2, p.sw2, -p.st2, -p.t2, cols_cut, False)   # нижняя
    wall(-p.sw2, p.sw2, p.t2, p.st2, cols_cut, False)     # верхняя

    zt0, zt1 = p.zb, p.zb + p.tooth_h
    # левая/правая гребёнки: колышки на центрах рядов, наклон наружу по X
    for x0, dx in ((-p.fw2 - p.td, -p.tooth_lean), (p.fw2, p.tooth_lean)):
        for a, b in pegs(rowc, p.bead_h - p.slot, -p.fh2, p.fh2):
            add(x0, x0 + p.td, a, b, zt0, zt1, dx, 0.0)
    # верхняя/нижняя гребёнки: колышки на центрах ниток прошивки
    # (крайние стоят на краю полотна), наклон наружу по Y
    for y0, dy in ((-p.fh2 - p.td, -p.tooth_lean), (p.fh2, p.tooth_lean)):
        for a, b in pegs(colc, p.bead_w - p.slot, -p.s2, p.s2):
            add(a, b, y0, y0 + p.td, zt0, zt1, 0.0, dy)
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
          % (p.clearance, 2 * (p.s2 + p.wall), 2 * (p.t2 + p.wall),
             2 * p.ox2, 2 * p.oy2))
    print("КОЛЫШКИ: боковые %d (шаг %.4f), верх/низ %d (шаг %.4f) — точно "
          "на центрах ниток" % (p.rows, p.bead_h, p.cols + 1, p.bead_w))
    print("ЗУБЬЯ: глубина %.2f, наклон от полотна %.2f мм (%.0f° от "
          "вертикали), канавка за ними %.2f мм — куда надевается нить"
          % (p.td, p.tooth_lean,
             57.29578 * (p.tooth_lean / p.tooth_h if p.tooth_h else 0.0),
             p.channel))
    print("ХВОСТЫ: по 2 прорези в каждой стенке (первая/последняя нить) "
          "шириной %.2f мм; углубление %.2f мм вдоль внешней стенки "
          "(+%.2f до юбки) — хвосты ложатся туда, суперклей до закрытия"
          % (p.slot, p.tail_groove, p.clearance))

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

