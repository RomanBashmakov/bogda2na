import trimesh
import numpy as np

# --- Параметры (мм) ---
plate_size = 250.0
thickness = 2.0
square_side = 3.0       # сторона квадратного отверстия
spacing = 4.5           # расстояние между центрами отверстий

half = square_side / 2.0

# Количество отверстий
n = int((plate_size - 2 * half) // spacing) + 1
start = -(n - 1) * spacing / 2.0
print(f"Отверстий: {n} x {n} = {n * n}")

# 1. Пластина
plate = trimesh.creation.box(extents=[plate_size, plate_size, thickness])

# 2. Шаблон одного квадратного "прутка" (вытянутый по Z куб)
#    Высота с запасом, чтобы точно проткнул пластину
prism_template = trimesh.creation.box(
    extents=[square_side, square_side, thickness + 2.0]
)

# 3. Трансформации для всех отверстий
transforms = []
for i in range(n):
    for j in range(n):
        x = start + i * spacing
        y = start + j * spacing
        T = np.eye(4)
        T[:3, 3] = [x, y, 0.0]
        transforms.append(T)

# 4. Объединяем все призмы в один меш (одна булева операция)
holes = trimesh.util.concatenate(
    [prism_template.copy().apply_transform(T) for T in transforms]
)
print(f"Меш отверстий: {len(holes.faces)} треугольников")

# 5. Булева разность
result = trimesh.boolean.difference(
    [plate, holes], engine='manifold', process=True
)

# 6. Экспорт
result.export('plate_with_square_holes.stl')
print("STL сохранён: plate_with_square_holes.stl")