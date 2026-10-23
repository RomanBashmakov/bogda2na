#!/usr/bin/env python3
"""Генератор модульных гребёнок для standing loom (Bambu A1).

Посадочный габарит как у оригинальной вставки obj_2:
сечение 15.18 x 2.5 мм (планка 9.9 мм + зубья 5.28 мм), вставляется
в прямоугольные прорези угловых стоек.

Зубья переработаны под 100 ниток:
- шаг 2.0 мм (бисер 11/0, Delica)
- зуб 0.5 мм, прорезь 1.5 мм (глубина 4.3 мм) — печатается без поддержек
- торцевые цапфы по 5.0 мм высотой планки 9.9 мм — как у оригинала
  obj_2 (зубья занимают 90 мм из 100 мм детали), вставляются в прорези
  угловых стоек (прорези — под высоту планки, без зубьев);
  между цапфой и первым зубом поле 0.75 мм

Модули: comb_50 (x2 шт) и comb_100. Ниток = прорезей = N.
Длина модуля = 2*N + 12 мм (112 мм / 212 мм).
"""
import os
import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))

PITCH = 2.0            # шаг зубьев
TOOTH_W = 1.25         # толщина зуба
SLOT_W = PITCH - TOOTH_W   # 0.75 мм — прорезь под нитку (вдвое уже прежней)
Z_T = 2.5              # толщина детали
H_BASE = 9.903         # высота планки (до верха основания)
H_TOT = 13.420        # полная высота: зуб на треть короче оригинала
                      # (было 15.178) — прочнее, слот глубиной 3.5 мм
SINK = 0.2             # притопление зубьев в планку (монолитность)
MARGIN = 0.75          # поле между цапфой и первым зубом
END_TAB = 5.0          # торцевая цапфа во всю высоту (как у obj_2)

Y_BASE0, Y_BASE1 = 0.0, H_BASE
Y_TOOTH0, Y_TOOTH1 = H_BASE - SINK, H_TOT
SLOT_FLOOR = H_BASE + 4.3 - 4.3  # низ прорези = верх планки


def box_mm(x0, x1, y0, y1, z0, z1):
    b = trimesh.creation.box(extents=[x1 - x0, y1 - y0, z1 - z0])
    b.apply_translation([(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2])
    return b


def make_module(threads):
    teeth = threads + 1
    length = 2 * threads + 2 * MARGIN + TOOTH_W + 2 * END_TAB

    parts = []
    # торцевые цапфы высотой планки (прорезь в стойках — только под планку)
    parts.append(box_mm(0, END_TAB, 0, H_BASE, 0, Z_T))
    parts.append(box_mm(length - END_TAB, length, 0, H_BASE, 0, Z_T))
    # планка и зубья
    parts.append(box_mm(0, length, Y_BASE0, Y_BASE1, 0, Z_T))
    h_tall = H_BASE + 1.1 * (H_TOT - H_BASE)   # удлинённые риски-зубья
    for k in range(teeth):
        x0 = END_TAB + MARGIN + k * PITCH
        # зубья №1, 11, 21, ..., (k с нуля) — на 10% выше
        h = h_tall if k % 10 == 0 else H_TOT
        parts.append(box_mm(x0, x0 + TOOTH_W, Y_TOOTH0, h, 0, Z_T))
    return trimesh.util.concatenate(parts), length, teeth


def make_stiffener(threads):
    """Усиливающая планка: посадка как у гребёнки (цапфы в прорези стоек),
    но без зубьев — под намотку не используется, только жёсткость."""
    length = 2 * threads + 2 * MARGIN + TOOTH_W + 2 * END_TAB
    m = box_mm(0, length, 0, H_BASE, 0, Z_T)
    return m, length


def export(name, threads):
    m, length, teeth = make_module(threads)
    path = os.path.join(HERE, name)
    m.export(path)
    print('%s: %d ниток, %d зубьев, %.1f мм, %d тр-ков, watertight=%s' %
          (name, threads, teeth, length, len(m.faces), m.is_watertight))


def export_stiffener(name, threads):
    m, length = make_stiffener(threads)
    path = os.path.join(HERE, name)
    m.export(path)
    print('%s: усиливающая планка, %.1f мм, %d тр-ков, watertight=%s' %
          (name, length, len(m.faces), m.is_watertight))


def main():
    export('comb_50_threads.stl', 50)     # печать x2
    export('comb_100_threads.stl', 100)   # целиком
    export_stiffener('stiffener_50_threads.stl', 50)    # печать x2
    export_stiffener('stiffener_100_threads.stl', 100)


if __name__ == '__main__':
    main()


