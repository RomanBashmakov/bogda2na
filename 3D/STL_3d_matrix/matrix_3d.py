import argparse

import trimesh
import numpy as np

ap = argparse.ArgumentParser(description="Матрица ячеек под бисер")
ap.add_argument("--plate", type=float, default=250.0,
                help="сторона квадратной пластины, мм (по умолчанию 250)")
ap.add_argument("-o", "--out", help="имя выходного STL")

# --- Параметры (мм) ---
plate_size = ap.parse_args().plate
thickness = 1.0
hole_dia = 3.0
spacing = 3.75          # шаг центров ячеек (стенка между ячейками 0.75 мм)
border = 3.0            # кромка от края пластины до первой ячейки
# Окантовка-ключ для сит: полосы слева и сверху, толщина 2 мм (от края
# до 2 мм — ложится на кромку), высота 1 мм над пластиной, длина ~1/3 стороны.
key_thickness = 2.0
key_height = 1.0
key_length = plate_size / 3.0

radius = hole_dia / 2.0
half_plate = plate_size / 2.0

# Количество отверстий: от линии сетки (border) до plate_size-border-hole
n = int((plate_size - 2 * border - hole_dia) // spacing) + 1
# Центры ячеек: ряд 0 прижат к ЛЕВОМУ-ВЕРХНЕМУ углу (стороны ключа),
# остаток поля уходит вправо-вниз.
start_x = -half_plate + border + radius
start_y = half_plate - border - radius
print(f"Отверстий: {n} x {n} = {n * n}")

# 1. Пластина
plate = trimesh.creation.box(extents=[plate_size, plate_size, thickness])

# 1а. Окантовка-ключ (лентами по левому и верхнему краю, поверх пластины)
key_parts = [
    trimesh.creation.box(extents=[key_thickness, key_length, key_height])
        .apply_translation([-half_plate + key_thickness / 2.0,
                            half_plate - key_length / 2.0,
                            thickness / 2.0 + key_height / 2.0]),
    trimesh.creation.box(extents=[key_length, key_thickness, key_height])
        .apply_translation([-half_plate + key_length / 2.0,
                            half_plate - key_thickness / 2.0,
                            thickness / 2.0 + key_height / 2.0]),
]
plate = trimesh.boolean.union([plate] + key_parts, engine='manifold',
                              process=True)

# 2. Один общий меш из всех цилиндров (быстрее и надёжнее для boolean)
#    Высоту берём с запасом, чтобы цилиндры точно проткнули пластину
cyl_template = trimesh.creation.cylinder(
    radius=radius, height=thickness + key_height + 2.0, sections=32
)
cyl_template.apply_translation([0, 0, 0])  # центрирован по Z, протыкает насквозь

# Собираем трансформации для всех отверстий
transforms = []
for i in range(n):
    for j in range(n):
        x = start_x + i * spacing
        y = start_y - j * spacing
        T = np.eye(4)
        T[:3, 3] = [x, y, 0.0]
        transforms.append(T)

# Дублируем шаблон и применяем трансформации
holes = cyl_template.copy()
holes = trimesh.util.concatenate(
    [cyl_template.copy().apply_transform(T) for T in transforms]
)
print(f"Меш отверстий: {len(holes.faces)} треугольников")

# 3. Булева разность (одна операция)
result = trimesh.boolean.difference(
    [plate, holes], engine='manifold', process=True
)

# 4. Экспорт
out = ap.parse_args().out or (
    "plate_with_holes.stl" if plate_size == 250.0
    else f"plate_with_holes_{plate_size:g}.stl")
result.export(out)
print(f"STL сохранён: {out}")