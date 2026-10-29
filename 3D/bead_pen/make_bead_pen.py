#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_bead_pen.py — карандаш-раздатчик бисера: одно нажатие = одна бисерина.

Зачем: раскладка бисера по ячейкам матрицы (3D/STL_3d_matrix) вручную
медленная, сито даёт 0–3 бисерины в ячейку. Карандаш держит бисер одного
цвета; наводишь носом на ячейку, жмёшь клавишу — выпадает ровно одна.

Принцип (чистая механика, без электроники):
  куча → очередь:  бункер-воронка сужается в канал-магазин Ø чуть больше
                   бисерины (две рядом не проходят) — бисер стоит колонной;
  очередь → такт:  под каналом поперёк оси скользит пластинчатый слайдер
                   с окном-карманом глубиной ровно на одну бисерину
                   (две не входят: 2×min(Ø, H) > глубина > max(Ø, H)).
                   Покой: окно под каналом — нижняя бисерина колонны стоит
                   в окне на дне полости. Нажал: слайдер ушёл, окно встало
                   над выходным отверстием — бисерина провалилась в нос.
                   Отпустил: резинка вернула слайдер, окно снова под
                   каналом, колонна досыпала следующую. Дно полости глухое
                   везде, кроме выходного отверстия, — мимо окна бисер
                   не проходит никогда. Ровно одна бисерина за такт.

Детали: pen_body (корпус), pen_slider (слайдер, печатать 2–3 запасных),
pen_cap (крышка бункера), pen_assembly (полная сборка — все детали в
рабочих положениях; справочный файл для просмотра, НЕ печать),
stand_N (подставка на N карандашей носами вниз),
fit_test + fit_key (калибровочная пластина: каналы под бисер, поясок в
ячейку матрицы, пазы посадки слайдера).

Печать (Bambulab, сопло 0.4, PLA): все файлы уже в ориентации печати
(корпус — бункером вниз). Отверстия выходят уже номинала: канал магазина
и окно слайдера прогнать сверлом Ø2 мм.

Сборка: слайдер вставить в полость клапана клавишей наружу (клавиша
упирается в кронштейн и не даёт слайдеру выпасть), канцелярская резинка —
через отверстие в клавише, концами за два отверстия кронштейна. Засыпать
бисер сверху, надеть крышку. По одному карандашу на цвет.

Запуск:
    python3 make_bead_pen.py                  # всё: карандаш+подставка+калибровка
    python3 make_bead_pen.py --what pen       # только карандаш
    python3 make_bead_pen.py --what stand --slots 12
    python3 make_bead_pen.py --bead-d 2.2 --bead-h 1.9   # другой бисер

Выход: out/*.stl рядом со скриптом.
"""

import argparse
import math
import sys
from pathlib import Path

import trimesh

HERE = Path(__file__).resolve().parent


# ----------------------------------------------------------------- примитивы
def cyl(r, z0, z1, x=0.0, y=0.0, sections=64):
    """Цилиндр вдоль Z от z0 до z1."""
    T = trimesh.transformations.translation_matrix((x, y, (z0 + z1) / 2.0))
    return trimesh.creation.cylinder(radius=r, height=z1 - z0,
                                     transform=T, sections=sections)


def cyl_y(r, y0, y1, x=0.0, z=0.0, sections=32):
    """Цилиндр вдоль Y от y0 до y1 (отверстие под резинку)."""
    R = trimesh.transformations.rotation_matrix(math.pi / 2.0, [1, 0, 0])
    T = trimesh.transformations.translation_matrix((x, (y0 + y1) / 2.0, z))
    return trimesh.creation.cylinder(radius=r, height=y1 - y0,
                                     transform=T @ R, sections=sections)


def box(x0, x1, y0, y1, z0, z1):
    """Параллелепипед по границам."""
    T = trimesh.transformations.translation_matrix(
        ((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0))
    return trimesh.creation.box(extents=[x1 - x0, y1 - y0, z1 - z0],
                                transform=T)


def frustum(r0, z0, r1, z1):
    """Усечённый конус (воронка): радиус r0 на z0, r1 на z1 (r1 > r0)."""
    h = z1 - z0
    z_apex = z0 - r0 * h / (r1 - r0)          # вершина конуса ниже дна
    H = z1 - z_apex
    R = trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0])
    T = trimesh.transformations.translation_matrix((0, 0, z_apex + H / 2.0))
    cone = trimesh.creation.cone(radius=r1, height=H, transform=T @ R,
                                 sections=96)
    return trimesh.boolean.intersection(
        [cone, box(-50, 50, -50, 50, z0, z1 + 0.5)], engine="manifold")


def union_all(solids):
    m = trimesh.boolean.union(solids, engine="manifold")
    if m is None or not len(m.faces):
        sys.exit("Ошибка: пустой результат булева объединения")
    return m


def cut(mesh, cutters):
    # Вырезы объединяем в одно тело ПЕРЕД вычитанием: у пересекающихся
    # вырезов (канал/воронка/выход) manifold иначе оставляет мембраны.
    if len(cutters) > 1:
        cutters = [trimesh.boolean.union(cutters, engine="manifold")]
    m = trimesh.boolean.difference([mesh] + cutters,
                                   engine="manifold", process=True)
    if m is None or not len(m.faces):
        sys.exit("Ошибка: пустой результат булева вычитания")
    return m


def drop_internal_voids(m, name):
    """Убрать внутренние замкнутые оболочки (артефакты manifold, например
    полость между двумя соосными отверстиями резинки в кронштейне):
    деталь по дизайну монолитная, остаётся самая большая оболочка."""
    parts = m.split(only_watertight=False)
    if len(parts) <= 1:
        return m
    parts.sort(key=lambda p: p.volume, reverse=True)
    for p in parts[1:]:
        print("  убран внутренний карман %.3f см³ (%s)"
              % (p.volume / 1000.0, name))
    return parts[0]


# ------------------------------------------------------------------ параметры
def derive(bead_d, bead_h, clear):
    """Все производные размеры (мм). Система: Z — ось карандаша, нос внизу."""
    P = {}
    P["bead_d"], P["bead_h"], P["clear"] = bead_d, bead_h, clear
    P["hole"] = bead_d + 0.37                      # канал/окно: одна проходит, две нет
    P["cup_z"] = 2.0 * min(bead_d, bead_h) - 0.25  # глубина окна: одна влезает, две нет
    if P["cup_z"] < max(bead_d, bead_h) + 0.3:
        sys.exit("Ошибка: окно не подобрать для такого бисера "
                 "(глубина %.2f < %.2f)" % (P["cup_z"], max(bead_d, bead_h) + 0.3))
    P["stroke"] = P["hole"] + 1.3                  # такт: канал → выход, стенка между 1.3
    P["body_r"] = 8.0                              # корпус Ø16
    P["hollow_r"] = 6.8                            # внутренняя полость ствола Ø13.6
    P["spigot_r"] = 1.45                           # поясок носа Ø2.9 — в ячейку 3.0
    if 2.0 * P["spigot_r"] < P["hole"] + 0.7:
        sys.exit("Ошибка: стенка пояска носа тоньше 0.35 мм")
    # полость клапана: дно 13.8, потолок 19.5; слайдер ходит по дну
    P["plate_z0"] = 13.85                          # 0.05 над дном
    P["plate_z1"] = P["plate_z0"] + P["cup_z"]
    # посадка слайдера от --clear (0.15–0.5): полость клапана по пластине
    g = max(0.15, clear * 0.8)
    P["plate_y_half"] = P["hole"] / 2.0 + 1.3      # пластина (стенка вокруг окна)
    P["cav_y_half"] = P["plate_y_half"] + g        # полость клапана
    P["pad_y_half"] = P["cav_y_half"] - 0.1        # клавиша: входит в полость при нажатии
    return P


# ---------------------------------------------------------------------- корпус
def make_body(P):
    hole, stroke = P["hole"], P["stroke"]
    ex = -stroke                                 # ось выхода/носа
    solids = [
        cyl(P["body_r"], 6.0, 90.0, sections=96),       # ствол
        cyl(3.1, 3.0, 6.0, x=ex),                        # база носа Ø6.2
        cyl(P["spigot_r"], 1.2, 3.0, x=ex),              # поясок в ячейку
        box(15, 17, -2.5, 2.5, 10.5, 24.0),              # кронштейн резинки
        box(6, 16, -2.5, 2.5, 10.5, 12.5),               # нижнее плечо кронштейна
        box(6, 16, -2.5, 2.5, 21.2, 23.5),               # верхнее плечо кронштейна
    ]
    # косынка 45° над верхним плечом (в печати — под ним): наружный конец
    # плеча не висит. Нижнее плечо печатается мостом 5.6 мм — поддержек
    # не требует; вторая косынка не нужна: пара косынок запирает воздушный
    # карман между пластиной кронштейна и собой.
    R45 = trimesh.transformations.rotation_matrix(math.radians(45), [0, 1, 0])
    T = trimesh.transformations.translation_matrix((16.0, 0.0, 24.3))
    solids.append(trimesh.creation.box(extents=[2.2, 4.6, 2.2],
                                       transform=T @ R45))
    body = union_all(solids)
    cutters = [
        cyl(P["hollow_r"], 24.0, 88.6, sections=96),     # внутренность ствола
        frustum(hole / 2.0, 62.0, P["hollow_r"], 82.0),  # воронка бункера
        cyl(hole / 2.0, 19.45, 62.7),                    # канал-магазин
        box(-5.55, 8.05, -P["cav_y_half"], P["cav_y_half"], 13.8, 19.5),  # полость
        cyl((hole - 0.1) / 2.0, 1.0, 13.95, x=ex),     # выходной канал в нос
        cyl_y(1.3, -3.4, 3.4, x=16.0, z=12.2),           # резинка, нижняя
        cyl_y(1.3, -3.4, 3.4, x=16.0, z=21.2),           # резинка, верхняя
    ]
    return cut(body, cutters)


# -------------------------------------------------------------------- слайдер
def make_slider(P):
    """Слайдер в положении ПОКОЯ: окно-карман ровно под каналом (x=0).
    Нажатие = сдвиг на -stroke: окно ровно над выходом. Клавиша снаружи
    упирается в кронштейн резинки — это упор покоя и стоп от выпадения,
    хвост изнутри упирается в дальнюю стенку полости — упор нажатия."""
    hole = P["hole"]
    z0, z1 = P["plate_z0"], P["plate_z1"]
    solids = [
        box(-2.05, 10.8, -P["plate_y_half"], P["plate_y_half"], z0, z1),  # пластина
        box(9.5, 14.9, -P["pad_y_half"], P["pad_y_half"], z0, 18.85),     # клавиша
    ]
    s = union_all(solids)
    return cut(s, [
        cyl(hole / 2.0, z0 - 0.15, z1 + 0.15),     # окно-карман (насквозь по Z)
        cyl_y(1.3, -3.2, 3.2, x=12.2, z=16.5),     # отверстие под резинку
    ])


# --------------------------------------------------------------------- крышка
def make_cap(P):
    return union_all([
        cyl(6.5, 86.5, 90.3, sections=64),         # пробка в горловину Ø13.6
        cyl(7.8, 90.0, 92.0, sections=64),         # фланец
    ])


# -------------------------------------------------------------------- сборка
def make_assembly(body, slider, cap):
    """Полная сборка итогового изделия (справочный STL, не для печати):
    корпус в рабочей ориентации носом вниз, слайдер в положении покоя
    (окно под каналом — бисерина загружена), крышка надета. Несколько
    несоприкасающихся тел в одном файле."""
    return trimesh.util.concatenate([body.copy(), slider.copy(), cap.copy()])


# ------------------------------------------------------------------- подставка
def make_stand(n):
    """N гнёзд с шагом 20: карандаш стоит носом вниз, юбка Ø16 опускается
    в гнездо Ø16.4 до упора на ступеньку Ø4.5, нос проваливается в сквозное
    отверстие. Спереди над каждым гнездом лунка под бирку цвета."""
    pitch, wall = 20.0, 8.0
    W = n * pitch + 2 * wall
    st = union_all([box(-W / 2.0, W / 2.0, -18.0, 18.0, 0.0, 63.0)])
    cutters = []
    for i in range(n):
        xc = -W / 2.0 + wall + pitch / 2.0 + i * pitch
        cutters.append(cyl(8.2, 23.0, 64.0, x=xc, sections=64))   # гнездо
        cutters.append(cyl(2.25, -1.0, 23.5, x=xc))               # под нос, насквозь
        cutters.append(box(xc - 6.0, xc + 6.0, -18.3, -17.2, 48.0, 56.0))  # лунка бирки
    return cut(st, cutters)


# ------------------------------------------------------------ калибровка
def make_fit(P):
    """Пластина одним прогоном: 1) каналы Ø1.9–2.3 — где бисер проходит
    свободно (номинал канала магазина); 2) пояски Ø2.7–3.0 — посадка носа
    в ячейку матрицы 3.0; 3) пазы с зазорами 0.15–0.3 — посадка слайдера."""
    plate = union_all([box(-38, 38, -14, 14, 0, 4)])
    cutters = []
    for i in range(5):                                   # каналы под бисер
        d = 1.9 + 0.1 * i
        cutters.append(cyl(d / 2.0, -0.5, 4.5, x=-32 + 4.5 * i, y=9))
    pegs = []
    for i in range(4):                                   # пояски в ячейку
        d = 2.7 + 0.1 * i
        pegs.append(cyl(d / 2.0, 4.0, 7.0, x=-32 + 4 * i, y=-10))
    return cut(union_all([plate] + pegs), cutters), P["hole"]


def make_fit_key(P):
    """Ключ со ступенями под пазы калибровочной пластины (шаг = паз − 0.1)."""
    sy0, sz0 = 4.7, P["cup_z"]       # сечения пазов: 4.7+2c и cup_z+2c
    solids = [box(36, 50, -3, 3, 0, 5)]                  # ручка
    for i in range(4):
        c = 0.15 + 0.05 * i
        sy, sz = sy0 + 2 * c - 0.1, sz0 + 2 * c - 0.1
        solids.append(box(0 + 9 * i, 9 + 9 * i, -sy / 2, sy / 2,
                          2 - sz / 2, 2 + sz / 2))
    return union_all(solids)


# -------------------------------------------------------------------- проверки
def check_pen(body, slider, P):
    print("Проверки карандаша:")
    for name, m in (("корпус", body), ("слайдер", slider)):
        if not m.is_watertight:
            sys.exit("  FAIL: %s не замкнут" % name)
        print("  %s: замкнут, %d тр-ков, объём %.2f см³"
              % (name, len(m.faces), m.volume / 1000.0))
    for pos, dx in (("покой", 0.0), ("нажатие", -P["stroke"])):
        s = slider.copy()
        s.apply_translation((dx, 0.0, 0.0))
        inter = trimesh.boolean.intersection([body, s], engine="manifold")
        vol = inter.volume if inter is not None and len(inter.faces) else 0.0
        _, dist, _ = trimesh.proximity.closest_point(body, s.vertices)
        if vol > 1e-6:
            sys.exit("  FAIL: пересечение корпус/слайдер в положении «%s»"
                     " (%.3f мм³)" % (pos, vol))
        print("  %s: пересечений 0, мин. зазор %.2f мм" % (pos, dist.min()))
    # лучи: путь бисерины вниз по оси канала (x=0) и выхода (x=-stroke).
    # Берём ПЕРВОЕ пересечение (макс. z): куда упадёт бисерина.
    def ray_first_z(x, dx_s):
        s = slider.copy()
        s.apply_translation((dx_s, 0.0, 0.0))
        scene = trimesh.util.concatenate([body, s])
        rmi = trimesh.ray.ray_triangle.RayMeshIntersector(scene)
        locs, _, _ = rmi.intersects_location([[x, 0.0, 19.0]],
                                             [[0.0, 0.0, -1.0]])
        if len(locs) == 0:
            return None
        return locs[:, 2].max()
    zr = ray_first_z(0.0, 0.0)            # покой: бисерина в окне стоит на дне
    if zr is None or not (13.5 < zr < 14.1):
        sys.exit("  FAIL: в покое под каналом нет глухого дна (z=%s)" % zr)
    print("  покой, ось канала: бисерина встала на дно (z=%.2f)" % zr)
    zb = ray_first_z(0.0, -P["stroke"])   # нажатие: канал перекрыт слайдером
    if zb is None or not (P["plate_z1"] - 0.25 < zb < P["plate_z1"] + 0.1):
        sys.exit("  FAIL: при нажатии канал не перекрыт слайдером (z=%s)" % zb)
    print("  нажатие, ось канала: перекрыт слайдером (z=%.2f)" % zb)
    zf = ray_first_z(-P["stroke"], -P["stroke"])  # нажатие: свободный вылет
    if zf is not None:
        sys.exit("  FAIL: путь к носу не свободен (z=%s)" % zf)
    print("  нажатие, ось выхода: свободный вылет до носа (Ø%.2f)"
          % (P["hole"] - 0.1))
    # аналитика: окно и допуски
    stroke = P["stroke"]
    print("  такт %.2f мм; окно Ø%.2f×%.2f (бисер Ø%.2f×%.2f: одна да, две нет); "
          "стенка дна между каналом и выходом %.2f мм"
          % (stroke, P["hole"], P["cup_z"], P["bead_d"], P["bead_h"],
             stroke - P["hole"]))
    # вместимость
    rh = P["hole"] / 2.0
    v_ch = math.pi * rh * rh * (62.0 - 19.5)
    v_fu = math.pi / 3.0 * 20.0 * (P["hollow_r"] ** 2
                                   + P["hollow_r"] * rh + rh * rh)
    v_ho = math.pi * P["hollow_r"] ** 2 * (88.6 - 82.0)
    v_bd = math.pi * (P["bead_d"] / 2.0) ** 2 * P["bead_h"]
    n_est = int(0.55 * (v_ch + v_fu + v_ho) / v_bd)
    print("  вместимость ~%d бисерин" % n_est)
    return n_est


# ---------------------------------------------------------------------- экспорт
def to_bed(m):
    """Опустить на стол (min z = 0) — файл сразу в ориентации печати."""
    m = m.copy()
    m.apply_translation((0.0, 0.0, -m.bounds[0][2]))
    return m


def flip_z(m):
    """Перевернуть вверх ногами (корпус печатается бункером вниз)."""
    m = m.copy()
    R = trimesh.transformations.rotation_matrix(math.pi, [1, 0, 0])
    m.apply_transform(R)
    return to_bed(m)


def save(m, outdir, name):
    p = outdir / name
    m.export(p)
    print("%s: %.1f×%.1f×%.1f мм, %d тр-ков"
          % (name, m.extents[0], m.extents[1], m.extents[2], len(m.faces)))


def main():
    ap = argparse.ArgumentParser(
        description="Карандаш-раздатчик бисера: одно нажатие = одна бисерина (STL)")
    ap.add_argument("--bead-d", type=float, default=1.73,
                    help="Ø бисерины, мм (Delica 15/0 ≈ 1.73)")
    ap.add_argument("--bead-h", type=float, default=1.46,
                    help="высота бисерины, мм (Delica 15/0 ≈ 1.46)")
    ap.add_argument("--clear", type=float, default=0.25,
                    help="зазор посадки слайдера, мм (0.15–0.5)")
    ap.add_argument("--slots", type=int, default=8,
                    help="гнёзд в подставке (по умолчанию 8)")
    ap.add_argument("--what", choices=["pen", "stand", "fit", "all"],
                    default="all", help="что генерировать")
    ap.add_argument("-o", "--out", default=str(HERE / "out"),
                    help="папка выхода (по умолчанию ./out)")
    args = ap.parse_args()

    if not (1.0 <= args.bead_d <= 6.0 and 0.8 <= args.bead_h <= 6.0):
        sys.exit("Ошибка: несуразные размеры бисера")
    if not 0.1 <= args.clear <= 0.5:
        sys.exit("Ошибка: зазор 0.1–0.5 мм")
    if not 1 <= args.slots <= 20:
        sys.exit("Ошибка: гнёзд 1–20")
    P = derive(args.bead_d, args.bead_h, args.clear)
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    print("Бисер Ø%.2f×%.2f → канал/окно Ø%.2f, глубина окна %.2f, такт %.2f мм"
          % (P["bead_d"], P["bead_h"], P["hole"], P["cup_z"], P["stroke"]))

    if args.what in ("pen", "all"):
        body = drop_internal_voids(make_body(P), "корпус")
        slider = drop_internal_voids(make_slider(P), "слайдер")
        cap = drop_internal_voids(make_cap(P), "крышка")
        check_pen(body, slider, P)
        save(flip_z(body), outdir, "pen_body.stl")
        save(to_bed(slider), outdir, "pen_slider.stl")
        save(to_bed(cap), outdir, "pen_cap.stl")
        asm = make_assembly(body, slider, cap)
        if not asm.is_watertight:
            sys.exit("FAIL: сборка не замкнута")
        save(to_bed(asm), outdir, "pen_assembly.stl")
        print("pen_assembly.stl — справочная сборка (не печатать как одно целое)")
    if args.what in ("stand", "all"):
        st = drop_internal_voids(make_stand(args.slots), "подставка")
        if not st.is_watertight:
            sys.exit("FAIL: подставка не замкнута")
        save(to_bed(st), outdir, "stand_%d.stl" % args.slots)
    if args.what in ("fit", "all"):
        fit, hole = make_fit(P)
        key = make_fit_key(P)
        fit = drop_internal_voids(fit, "калибровка")
        key = drop_internal_voids(key, "ключ")
        if not (fit.is_watertight and key.is_watertight):
            sys.exit("FAIL: калибровка не замкнута")
        save(to_bed(fit), outdir, "fit_test.stl")
        save(to_bed(key), outdir, "fit_key.stl")
        print("Калибровка: каналы слева направо Ø1.9–2.3 (магазин %.2f), "
              "пояски Ø2.7–3.0 в ячейку 3.0, пазы зазор 0.15–0.30"
              % hole)


if __name__ == "__main__":
    main()




