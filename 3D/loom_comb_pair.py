"""Парные гребёнки для ткачкого станка (стоячий станок, standing loom).

Две одинаковые гребёнки стоят параллельно, чистый просвет между ними
GAP_MM. Снизу соединены пластиной — сечение в виде перевёрнутой буквы «П».

Нити натягиваются поперёк, в щели между зубьями: зубьев N_TEETH,
щелей N_TEETH-1 (по числу нитей).

Все размеры в мм.
"""

import argparse

import numpy as np
import trimesh

ap = argparse.ArgumentParser(description="Парные гребёнки с нижней пластиной (П-профиль)")
ap.add_argument("-o", "--out", default="loom_comb_pair_33x2.stl", help="имя выходного STL")

# --- Параметры (мм) ---
args = ap.parse_args()

N_TEETH = 33            # число зубьев на одной гребёнке (щелей/нитей — на 1 меньше)
PITCH = 2.0             # шаг зубьев: расстояние между центрами соседних зубьев
SLOT = 0.75             # ширина щели под нить (шаг минус толщина зуба)
TOOTH_W = PITCH - SLOT  # ширина зуба вдоль длины = 1.25
TOOTH_H = 4.0           # высота зуба над основанием
TOOTH_T = 2.5           # толщина зуба/гребёнки (поперёк, между гребёнками)
TIP_T = 1.0             # толщина заострённой вершины зуба
TIP_H = 1.0             # высота конуса заострения (верхняя часть зуба)
BASE_H = 20.0           # высота основания гребёнки (под зубьями)
MARGIN = 3.0            # поле на основании за крайними зубьями
GAP_MM = 25.0           # чистый просвет между гребёнками (между внутренними стенками)
PLATE_T = 2.5           # толщина нижней соединительной пластины
DEPTH = 2.5             # толщина всего профиля по Z (как у исходных деталей станка)

length = 2 * MARGIN + TOOTH_W + (N_TEETH - 1) * PITCH   # 70 мм
length = 70.0  # согласованная общая длина; зубья центрируются (центры -32..+32)
overall_y = GAP_MM + 2 * TOOTH_T                        # 30 мм
overall_z = PLATE_T + BASE_H + TOOTH_H                  # 26.5 мм

print(f"Гребёнки: зубьев {N_TEETH} x2, шаг {PITCH} мм, щель {SLOT} мм, "
      f"просвет {GAP_MM} мм; габарит {length:g} x {overall_y:g} x {overall_z:g} мм")

parts = []

# 1. Нижняя соединительная пластина: вровень с внешними стенками гребёнок;
#    с одной стороны (по +X) удлинена на HANDLE_MM — ушко, чтобы защипнуть пальцами
HANDLE_MM = 10.0
plate = trimesh.creation.box(extents=[length + HANDLE_MM, overall_y, PLATE_T])
plate.apply_translation([HANDLE_MM / 2.0, 0.0, PLATE_T / 2.0])
parts.append(plate)

# 2. Профиль одного зуба в плоскости (ширина X — высота Z):
#    снизу вверх стенкой полной ширины TOOTH_W, верхний TIP_H сужается клином
#    по ширине (в плоскости нити) — нить вскальзывает в паз по скосам.
#    Толщина по Y постоянная TOOTH_T, экструдируем по Y.
z0 = PLATE_T + BASE_H                      # низ зуба
z1 = z0 + TOOTH_H - TIP_H                  # начало заострения
z2 = z0 + TOOTH_H                          # вершина

half_t = TOOTH_T / 2.0
half_w = TOOTH_W / 2.0
tip_w = TOOTH_W * (TIP_T / TOOTH_T)        # ширина вершины (та же пропорция, в плоскости X)
half_tw = tip_w / 2.0

# Контур зуба в плоскости (X, Z), против часовой стрелки
poly = [
    (-half_w, z0),
    (half_w, z0),
    (half_w, z1),
    (half_tw, z2),
    (-half_tw, z2),
    (-half_w, z1),
]


def prism_from_poly(poly, y_lo, y_hi):
    """Призма: полигон (x,z), вытянутый вдоль Y от y_lo до y_hi."""
    n = len(poly)
    bot = [[x, y_lo, z] for x, z in poly]
    top = [[x, y_hi, z] for x, z in poly]
    vertices = np.array(bot + top, dtype=float)
    faces = []
    # крышки: веером от вершины 0. Полигон CCW в (X,Z) даёт нормаль -Y,
    # поэтому нижняя крышка (y_lo) — по порядку, верхняя (y_hi) — в обратном.
    for i in range(1, n - 1):
        faces.append([0, i, i + 1])
        faces.append([n, n + i + 1, n + i])
    # боковые грани
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, n + i, n + j])
        faces.append([i, n + j, j])
    mesh = trimesh.Trimesh(vertices=vertices, faces=np.array(faces), process=True)
    assert mesh.is_watertight and mesh.is_volume, "призма зуба не замкнута"
    return mesh


def comb_wall(y_center):
    """Одна гребёнка: основание-стенка + все зубья. Возвращает список мешей."""
    wall = trimesh.creation.box(extents=[length, TOOTH_T, BASE_H])
    wall.apply_translation([0.0, y_center, PLATE_T + BASE_H / 2.0])
    meshes = [wall]
    x0 = -(N_TEETH - 1) * PITCH / 2.0   # центр первого зуба: -32, последнего: +32
    for i in range(N_TEETH):
        x = x0 + i * PITCH
        tooth = prism_from_poly(
            [(px + x, pz) for px, pz in poly],
            y_center - half_t, y_center + half_t,
        )
        meshes.append(tooth)
    return meshes


# 3. Две гребёнки: внутренние стенки на y = ±GAP_MM/2
parts += comb_wall(GAP_MM / 2.0 + TOOTH_T / 2.0)
parts += comb_wall(-(GAP_MM / 2.0 + TOOTH_T / 2.0))

# --- Облегчение (жёсткость не нужна: деталь только позиционирует бисерины) ---
cutters = []

# Окна в основаниях гребёнок — круглые отверстия (короткие мостики при печати,
# поддержек почти нет): ряд из HOLE_N отверстий HOLE_D по центру основания
HOLE_D = 10.0        # диаметр отверстий
HOLE_N = 5           # штук в ряд
z_mid = PLATE_T + BASE_H / 2.0
for y in (GAP_MM / 2.0 + TOOTH_T / 2.0, -(GAP_MM / 2.0 + TOOTH_T / 2.0)):
    for i in range(HOLE_N):
        x = -length / 2.0 + (length) * (i + 1) / (HOLE_N + 1)
        h = trimesh.creation.cylinder(radius=HOLE_D / 2.0, height=TOOTH_T + 1.0,
                                      sections=32)
        rot = trimesh.transformations.rotation_matrix(np.radians(90.0), [1, 0, 0])
        h.apply_transform(rot)
        h.apply_translation([x, y, z_mid])
        cutters.append(h)

# Пазы в пластине насквозь: под стенками и по краям цельная окантовка RIM,
# между ними — поперечные рёбра RIB_W через RIB_STEP, остальное прорезано насквозь
RIB_W = 2.5          # ширина поперечных рёбер
RIB_STEP = 20.0      # шаг рёбер
RIM = 2.5            # цельная окантовка по периметру (в т.ч. под стенками)
WIN_END = 4.0        # цельные торцы пластины по краям пазов
pocket_z0, pocket_z1 = 0.0, PLATE_T
pocket_x0, pocket_x1 = -length / 2.0 + WIN_END, length / 2.0 + HANDLE_MM - WIN_END
pocket_y0, pocket_y1 = -overall_y / 2.0 + RIM, overall_y / 2.0 - RIM
pocket = trimesh.creation.box(extents=[pocket_x1 - pocket_x0,
                                       pocket_y1 - pocket_y0,
                                       pocket_z1 - pocket_z0])
pocket.apply_translation([(pocket_x0 + pocket_x1) / 2.0,
                          (pocket_y0 + pocket_y1) / 2.0,
                          (pocket_z0 + pocket_z1) / 2.0])
# рёбра внутри кармана (оставляем материал)
ribs = trimesh.util.concatenate([
    trimesh.creation.box(extents=[RIB_W, pocket_y1 - pocket_y0,
                                  pocket_z1 - pocket_z0])
        .apply_translation([x, 0.0, (pocket_z0 + pocket_z1) / 2.0])
    for x in np.arange(pocket_x0 + RIB_STEP, pocket_x1, RIB_STEP)
])
cutters.append(trimesh.boolean.difference([pocket, ribs], engine="manifold", process=True))

# 4. Объединение в одно тело и выборка облегчающих полостей
solid = trimesh.boolean.union(parts, engine="manifold", process=True)
result = trimesh.boolean.difference([solid] + cutters, engine="manifold", process=True)
assert result.is_watertight

result.export(args.out)
print(f"Треугольников: {len(result.faces)}, watertight: {result.is_watertight}, "
      f"габарит: {result.extents}")
print(f"STL сохранён: {args.out}")
