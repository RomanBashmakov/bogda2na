"""Анализ структуры STL: ASCII-occupancy по трём осям.
Использование: python _analyze_ref.py файл.stl [ось ...]
"""
import sys
import numpy as np
import trimesh

m = trimesh.load(sys.argv[1] if len(sys.argv) > 1 else "коробка_для_проводов.stl")
V, F = m.vertices, m.faces
tri = V[F]
print("габарит", m.extents, "треугольников", len(F), "watertight", m.is_watertight)


def occupancy(ax_name, n=56):
    ax = {"x": 0, "y": 1, "z": 2}[ax_name]
    oth = [i for i in range(3) if i != ax]
    b0, b1 = m.bounds
    g1 = np.linspace(b0[oth[0]] + 0.8, b1[oth[0]] - 0.8, n)
    g2 = np.linspace(b0[oth[1]] + 0.8, b1[oth[1]] - 0.8, n)
    rd = np.zeros(3)
    rd[ax] = 1.0
    e1 = tri[:, 1] - tri[:, 0]
    e2 = tri[:, 2] - tri[:, 0]
    h = np.cross(rd, e2)
    a = np.einsum("ij,ij->i", e1, h)
    ok = np.abs(a) > 1e-12
    f = np.zeros_like(a)
    f[ok] = 1.0 / a[ok]
    rows = []
    for v2 in g2:
        row = ""
        for v1 in g1:
            ro = np.zeros(3)
            ro[oth[0]] = v1
            ro[oth[1]] = v2
            s = ro - tri[:, 0]
            u = f * np.einsum("ij,ij->i", s, h)
            q = np.cross(s, e1)
            v = f * np.einsum("ij,ij->i", q, rd * np.ones_like(tri[:, 0]))
            t = f * np.einsum("ij,ij->i", e2, q)
            hit = ok & (u >= 0) & (u <= 1) & (v >= 0) & (u + v <= 1) & (t > 1e-9)
            row += "#" if hit.sum() % 2 else "."
        rows.append(row)
    return rows


args=sys.argv[2:] or ["x","y","z"]
for d in args:
    print(f"=== срез вдоль {d} (лучи вдоль {d}; # — материал) ===")
    for r in occupancy(d):
        print(r)
