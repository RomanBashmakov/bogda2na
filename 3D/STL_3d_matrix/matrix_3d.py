import trimesh
import numpy as np

# --- Параметры (мм) ---
plate_size = 250.0
thickness = 2.0
hole_dia = 3.0
spacing = 4.5

radius = hole_dia / 2.0

# Количество отверстий
n = int((plate_size - 2 * radius) // spacing) + 1
start = -(n - 1) * spacing / 2.0
print(f"Отверстий: {n} x {n} = {n * n}")

# 1. Пластина
plate = trimesh.creation.box(extents=[plate_size, plate_size, thickness])

# 2. Один общий меш из всех цилиндров (быстрее и надёжнее для boolean)
#    Высоту берём с запасом, чтобы цилиндры точно проткнули пластину
cyl_template = trimesh.creation.cylinder(
    radius=radius, height=thickness + 2.0, sections=32
)

# Собираем трансформации для всех отверстий
transforms = []
for i in range(n):
    for j in range(n):
        x = start + i * spacing
        y = start + j * spacing
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
result.export('plate_with_holes.stl')
print("STL сохранён: plate_with_holes.stl")