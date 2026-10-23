#!/usr/bin/env python3
"""4 отверстия под магниты 6x3 (сквозные, ось Z) + прорези для пальцев.

Левый рельс: магниты (17.5, 100) и (17.5, 120), прорезь Y 104..116.
Правый рельс: магниты (238, 120) и (238, 140), прорезь Y 124..136.
Иголка лежит поперёк двух магнитов; сквозная прорезь — чтобы подцепить пальцем.
"""
# -*- coding: utf-8 -*-
"""4 гнезда под магниты 6x3 со стенкой-дном 1 мм (магнит выступает ~1 мм)
+ сквозные прорези до края рельса (защип иголки двумя пальцами).

Левый рельс: магниты X=12.55 (вдвое ближе к внешнему краю X=7.62), Y=100/120;
  прорезь Y 104..116, от края X 7.0 до 17.5.
Правый рельс: магниты X=243.25 (край X=248.38), Y=120/140;
  прорезь Y 124..136, X 238.0..249.0.
Дно гнезда: z=1.0 (рельс 3.0 мм -> глубина гнезда 2.0, магнит 3 мм выступает 1 мм).
"""
import numpy as np
import trimesh
import manifold3d

m = trimesh.load('obj_1_standing loom no_text.stl')

def to_manifold(mesh):
    mf = manifold3d.Mesh(
        vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
        tri_verts=np.asarray(mesh.faces, dtype=np.uint32))
    mf.merge()  # склеить совпадающие вершины/грани
    return manifold3d.Manifold(mesh=mf)

def to_trimesh(man):
    mf = man.to_mesh()
    return trimesh.Trimesh(vertices=np.asarray(mf.vert_properties)[:, :3],
                           faces=np.asarray(mf.tri_verts), process=True)

base = to_manifold(m)

FLOOR_Z = 1.0   # стенка-дно 1 мм

tools = []
def cyl(x, y):
    c = trimesh.creation.cylinder(radius=3.0, height=6.0, sections=64)  # ось Z
    c.apply_translation([x, y, FLOOR_Z + 3.0])  # дно гнезда на z=1.0
    tools.append(to_manifold(c))

def slot(x0, x1, y0, y1):
    b = trimesh.creation.box(extents=[x1 - x0, y1 - y0, 10.0])
    b.apply_translation([(x0 + x1) / 2, (y0 + y1) / 2, 0])
    tools.append(to_manifold(b))

# левый рельс: магниты в 20 мм, вдвое ближе к внешнему краю (7.62)
cyl(12.55, 100); cyl(12.55, 120)
slot(7.0, 17.5, 104.0, 116.0)      # до самого края
# правый рельс
cyl(243.25, 120); cyl(243.25, 140)
slot(238.0, 249.0, 124.0, 136.0)

result = base
for t in tools:
    result = result - t

out = to_trimesh(result)
out.export('obj_1_standing loom magnets.stl')
print('граней:', len(out.faces), 'watertight:', out.is_watertight,
      'bounds:', out.bounds.round(2).tolist())
