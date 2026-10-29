import argparse

import trimesh
import numpy as np

ap = argparse.ArgumentParser(description="Матрица ячеек под бисер")
ap.add_argument("--plate", type=float, default=250.0,
                help="сторона квадратной пластины, мм (по умолчанию 250)")
ap.add_argument("--nx", type=int, help="число ячеек по горизонтали (пластина "
                 "растягивается вправо-вниз под заданную сетку)")
ap.add_argument("--ny", type=int, help="число ячеек по вертикали")
ap.add_argument("-o", "--out", help="имя выходного STL")

# --- Параметры (мм) ---
args = ap.parse_args()
plate_size = args.plate
nx_arg, ny_arg = args.nx, args.ny
thickness = 3.5            # бисерина полностью спрятана + запас
square_side = 3.0       # сторона квадратного отверстия
spacing = 3.75          # расстояние между центрами отверстий (стенка 0.75 мм)
border = 3.0            # кромка от края пластины до первой ячейки
# Канавки-«бороздки» для иголки: горизонтальные, вдоль каждого ряда,
# режут перегородки между соседними ячейками; ширина 1 мм, глубина
# thickness - groove_bottom_rest, под канавкой остаётся материал 1 мм.
groove_width = 1.0
groove_rest = 1.0       # материал под дном канавки
# Окантовка-ключ для сит: полосы слева и сверху, толщина 2 мм (от края
# до 2 мм — ложится на кромку), высота 1 мм над пластиной, длина ~1/3 стороны.
key_thickness = 2.0
key_height = 1.0
key_length = plate_size / 3.0

half = square_side / 2.0

if nx_arg and ny_arg:
    # Прямоугольная пластина под заданную сетку: ячейки прижаты
    # к левому-верхнему углу (стороны ключа), как у квадратных версий.
    plate_w = 2 * border + square_side + (nx_arg - 1) * spacing
    plate_h = 2 * border + square_side + (ny_arg - 1) * spacing
else:
    plate_w = plate_h = plate_size

half_w = plate_w / 2.0
half_h = plate_h / 2.0

# Количество отверстий: от линии сетки (border) до края минус ячейка
if nx_arg and ny_arg:
    n_x, n_y = nx_arg, ny_arg
else:
    n = int((plate_size - 2 * border - square_side) // spacing) + 1
    n_x = n_y = n
# Центры ячеек: ряд 0 прижат к ЛЕВОМУ-ВЕРХНЕМУ углу (стороны ключа),
# остаток поля уходит вправо-вниз.
start_x = -half_w + border + half
start_y = half_h - border - half
print(f"Пластина: {plate_w:g} x {plate_h:g} мм, отверстий: {n_x} x {n_y} = {n_x * n_y}")

# 1. Пластина
plate = trimesh.creation.box(extents=[plate_w, plate_h, thickness])

# 1а. Окантовка-ключ (лентами по левому и верхнему краю, поверх пластины)
key_parts = [
    trimesh.creation.box(extents=[key_thickness, key_length, key_height])
        .apply_translation([-half_w + key_thickness / 2.0,
                            half_h - key_length / 2.0,
                            thickness / 2.0 + key_height / 2.0]),
    trimesh.creation.box(extents=[key_length, key_thickness, key_height])
        .apply_translation([-half_w + key_length / 2.0,
                            half_h - key_thickness / 2.0,
                            thickness / 2.0 + key_height / 2.0]),
]
plate = trimesh.boolean.union([plate] + key_parts, engine='manifold',
                              process=True)

# 2. Шаблон одного квадратного "прутка" (вытянутый по Z куб)
#    Высота с запасом, чтобы точно проткнул пластину
prism_template = trimesh.creation.box(
    extents=[square_side, square_side, thickness + key_height + 2.0]
)

# 3. Трансформации для всех отверстий
transforms = []
for i in range(n_x):
    for j in range(n_y):
        x = start_x + i * spacing
        y = start_y - j * spacing
        T = np.eye(4)
        T[:3, 3] = [x, y, 0.0]
        transforms.append(T)

# 4. Объединяем все призмы в один меш (одна булева операция)
holes_cells = trimesh.util.concatenate(
    [prism_template.copy().apply_transform(T) for T in transforms]
)
print(f"Меш отверстий: {len(holes_cells.faces)} треугольников")

# 4а. Канавки-«бороздки» под иголку: горизонтальная канавка вдоль центра
#     каждого ряда (по Y — groove_width, по X — на всю ширину сетки),
#     режет перегородки между соседними ячейками. Сверху протыкает
#     насквозь, снизу дно на groove_rest от низа пластины.
groove_depth = thickness - groove_rest          # глубина от верха
# длина с запасом ±1 мм в кромку: торцы канавки НЕ должны совпадать
# с плоскостями стенок крайних ячеек (иначе вырожденные грани)
groove_len = (n_x - 1) * spacing + square_side + 2.0
groove_zc = -thickness / 2.0 + groove_rest + (groove_depth + 1.0) / 2.0
grooves = [
    trimesh.creation.box(
        extents=[groove_len, groove_width, groove_depth + 1.0])
        .apply_translation([start_x - half - 1.0 + groove_len / 2.0,
                            start_y - j * spacing, groove_zc])
    for j in range(n_y)
]
holes_grooves = trimesh.util.concatenate(grooves)
print(f"Канавок: {n_y} (ширина {groove_width:g} мм, глубина {groove_depth:g} мм)")

# 5. Булева разность: сначала ячейки, потом канавки (две отдельные
#    операции — manifold надёжнее, чем всё одним вычитанием)
result = trimesh.boolean.difference(
    [plate, holes_cells], engine='manifold', process=True
)
result = trimesh.boolean.difference(
    [result, holes_grooves], engine='manifold', process=True
)
# чистка вырожденных граней от совпадающих плоскостей (неwatertight у слайсеров)
result.merge_vertices()
result.update_faces(result.area_faces > 1e-10)
result.merge_vertices()
print(f"Готово: watertight={result.is_watertight}, "
      f"{len(result.faces)} треугольников")

# 6. Экспорт
if args.out:
    out = args.out
elif nx_arg and ny_arg:
    out = f"plate_with_square_holes_{nx_arg}x{ny_arg}.stl"
elif plate_size != 250.0:
    out = f"plate_with_square_holes_{plate_size:g}.stl"
else:
    out = "plate_with_square_holes.stl"
result.export(out)
print(f"STL сохранён: {out}")