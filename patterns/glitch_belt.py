#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
glitch_belt.py — генератор печатных схем бисерных поясов с глитч-надписями.

Что делает
----------
* растрирует надпись (латиница/кириллица) встроенным шрифтом 5×7;
* накладывает глитч-эффекты: RGB-сдвиг (маджента/циан), сдвиг срезов,
  «выпадения» пикселей, блэкаут-блоки;
* строит сетку кружочков с фиксированным шагом в миллиметрах — под печатную
  оснастку с отверстиями: расстояния и диаметры всегда одинаковы;
* номер внутри кружка — порядковый номер цвета из палитры (номер коробочки):
  достал бисерину из коробочки №N → положил на кружок №N;
* выпускает самодостаточный HTML (A4, inline SVG): сегменты пояса с линейками
  и линиями отреза, легенда с подсчётом бисерин, калибровочная линейка.

Зависимости: только стандартная библиотека Python 3.8+.

Пример
------
    python3 glitch_belt.py --text "ГЛИТЧ" --length-cm 90 --width-cm 4 \\
        --pitch-mm 2.5 --seed 42 --title "Пояс №1" --out out/poyas1.html
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_PALETTE = HERE / "palette.json"

# --- Геометрия страницы A4 (мм) ---
PAGE_W, PAGE_H = 210.0, 297.0   # портрет
PAGE_MARGIN = 8.0               # поля печати
GUTTER = 7.0                    # поле слева под номера рядов
RULER_H = 3.6                   # линейка колонок над сеткой
CUT_H = 4.6                     # место под линию отреза после сегмента
TITLE_H = 4.2                   # заголовок сегмента

CSS = """
@page { size: A4 portrait; margin: 8mm; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body { font-family: "DejaVu Sans", "PT Sans", "Segoe UI", Arial, sans-serif;
       color: #1b1b1b; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.page { page-break-after: always; }
.page:last-child { page-break-after: auto; }
h1 { font-size: 5.2mm; margin: 0 0 1.2mm; letter-spacing: 0.2mm; }
h2 { font-size: 4.2mm; margin: 0 0 2mm; }
.sub { font-size: 3mm; color: #555; margin: 0 0 3mm; }
.card { border: 0.35mm solid #333; border-radius: 2mm; padding: 4mm; margin: 0 0 4mm; }
table { border-collapse: collapse; }
.params td { font-size: 3.1mm; padding: 0.9mm 2.5mm 0.9mm 0; vertical-align: top; }
.params td.k { color: #666; white-space: nowrap; width: 44mm; }
.legend th { font-size: 2.8mm; color: #666; text-align: left; font-weight: 600;
             padding: 0 2.5mm 1.2mm 0; border-bottom: 0.3mm solid #333; }
.legend td { font-size: 3.1mm; padding: 1.4mm 2.5mm 1.4mm 0;
             border-bottom: 0.2mm solid #ddd; }
.legend .num { font-weight: 700; font-size: 4mm; }
.legend .total td { border-bottom: none; font-weight: 700; }
.swatch { display: inline-block; width: 5mm; height: 5mm; border-radius: 50%;
          border: 0.25mm solid #aaa; vertical-align: -1.1mm; }
.seg { margin: 0 0 1mm; }
.seg-title { font-size: 2.9mm; color: #444; margin: 0 0 0.8mm; }
.cut { border-top: 0.3mm dashed #9a9a9a; margin: 2.2mm 0 3.2mm; font-size: 2.6mm;
       color: #8a8a8a; text-align: right; }
@media screen {
  body { background: #d9d9d9; padding: 6mm 0; }
  .page { background: #fff; width: 194mm; min-height: 281mm; margin: 0 auto 6mm;
          padding: 8mm; box-shadow: 0 1mm 3mm rgba(0,0,0,.35); }
}
@media print {
  .page { padding: 0; margin: 0; width: auto; box-shadow: none; }
}
"""

# ------------------------------------------------------------- ШРИФТ 5×7 ---
# Глиф: (ширина в колонках, 7 строк). Бит 0 — правая колонка.
FONT = {
    # Латиница
    "A": (5, (0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11)),
    "B": (5, (0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E)),
    "C": (5, (0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E)),
    "D": (5, (0x1C, 0x12, 0x11, 0x11, 0x11, 0x12, 0x1C)),
    "E": (5, (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F)),
    "F": (5, (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10)),
    "G": (5, (0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F)),
    "H": (5, (0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11)),
    "I": (5, (0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E)),
    "J": (5, (0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C)),
    "K": (5, (0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11)),
    "L": (5, (0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F)),
    "M": (5, (0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11)),
    "N": (5, (0x11, 0x11, 0x19, 0x15, 0x13, 0x11, 0x11)),
    "O": (5, (0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E)),
    "P": (5, (0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10)),
    "Q": (5, (0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D)),
    "R": (5, (0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11)),
    "S": (5, (0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E)),
    "T": (5, (0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04)),
    "U": (5, (0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E)),
    "V": (5, (0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04)),
    "W": (5, (0x11, 0x11, 0x11, 0x15, 0x15, 0x15, 0x0A)),
    "X": (5, (0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11)),
    "Y": (5, (0x11, 0x11, 0x11, 0x0A, 0x04, 0x04, 0x04)),
    "Z": (5, (0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F)),
    # Цифры
    "0": (5, (0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E)),
    "1": (5, (0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E)),
    "2": (5, (0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F)),
    "3": (5, (0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E)),
    "4": (5, (0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02)),
    "5": (5, (0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E)),
    "6": (5, (0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E)),
    "7": (5, (0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08)),
    "8": (5, (0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E)),
    "9": (5, (0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C)),
    # Кириллица
    "А": (5, (0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11)),
    "Б": (5, (0x1F, 0x10, 0x10, 0x1E, 0x11, 0x11, 0x1E)),
    "В": (5, (0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E)),
    "Г": (5, (0x1F, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10)),
    "Д": (5, (0x0E, 0x11, 0x11, 0x11, 0x11, 0x1F, 0x11)),
    "Е": (5, (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F)),
    "Ё": (5, (0x0A, 0x1F, 0x10, 0x1E, 0x10, 0x10, 0x1F)),
    "Ж": (5, (0x15, 0x15, 0x15, 0x0E, 0x15, 0x15, 0x15)),
    "З": (5, (0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E)),
    "И": (5, (0x11, 0x11, 0x13, 0x15, 0x19, 0x11, 0x11)),
    "Й": (5, (0x06, 0x11, 0x13, 0x15, 0x19, 0x11, 0x11)),
    "К": (5, (0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11)),
    "Л": (5, (0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11)),
    "М": (5, (0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11)),
    "Н": (5, (0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11)),
    "О": (5, (0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E)),
    "П": (5, (0x1F, 0x11, 0x11, 0x11, 0x11, 0x11, 0x11)),
    "Р": (5, (0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10)),
    "С": (5, (0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E)),
    "Т": (5, (0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04)),
    "У": (5, (0x11, 0x11, 0x11, 0x0A, 0x04, 0x04, 0x04)),
    "Ф": (5, (0x04, 0x0E, 0x15, 0x15, 0x15, 0x0E, 0x04)),
    "Х": (5, (0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11)),
    "Ц": (5, (0x15, 0x15, 0x15, 0x15, 0x15, 0x1F, 0x01)),
    "Ч": (5, (0x11, 0x11, 0x11, 0x0F, 0x01, 0x01, 0x01)),
    "Ш": (5, (0x15, 0x15, 0x15, 0x15, 0x15, 0x15, 0x1F)),
    "Щ": (5, (0x15, 0x15, 0x15, 0x15, 0x15, 0x1F, 0x01)),
    "Ъ": (5, (0x18, 0x10, 0x10, 0x1E, 0x11, 0x11, 0x1E)),
    "Ы": (5, (0x11, 0x11, 0x11, 0x1D, 0x13, 0x13, 0x1D)),
    "Ь": (5, (0x10, 0x10, 0x10, 0x1E, 0x11, 0x11, 0x1E)),
    "Э": (5, (0x0E, 0x11, 0x01, 0x0F, 0x01, 0x11, 0x0E)),
    "Ю": (6, (0b100110, 0b101001, 0b101001, 0b101001, 0b101001, 0b101001, 0b100110)),
    "Я": (5, (0x0F, 0x11, 0x11, 0x0F, 0x05, 0x09, 0x11)),
    # Знаки
    " ": (3, (0, 0, 0, 0, 0, 0, 0)),
    ".": (1, (0, 0, 0, 0, 0, 1, 1)),
    ",": (2, (0, 0, 0, 0, 0b01, 0b01, 0b10)),
    "!": (1, (1, 1, 1, 1, 1, 0, 1)),
    "?": (5, (0x0E, 0x11, 0x01, 0x02, 0x04, 0x00, 0x04)),
    "-": (5, (0, 0, 0, 0x1F, 0, 0, 0)),
    "+": (5, (0, 0b00100, 0b00100, 0b11111, 0b00100, 0b00100, 0)),
    "/": (5, (0b00001, 0b00001, 0b00010, 0b00100, 0b01000, 0b10000, 0b10000)),
    "#": (5, (0b01010, 0b11111, 0b01010, 0b01010, 0b01010, 0b11111, 0b01010)),
    "@": (5, (0x0E, 0x11, 0x15, 0x17, 0x14, 0x11, 0x0E)),
    ":": (1, (0, 1, 1, 0, 1, 1, 0)),
    "'": (1, (1, 1, 0, 0, 0, 0, 0)),
    "*": (5, (0, 0b01010, 0b00100, 0b11111, 0b00100, 0b01010, 0)),
    "_": (5, (0, 0, 0, 0, 0, 0, 0b11111)),
    "(": (2, (0b01, 0b10, 0b10, 0b10, 0b10, 0b10, 0b01)),
    ")": (2, (0b10, 0b01, 0b01, 0b01, 0b01, 0b01, 0b10)),
}
def glyph(ch: str):
    """Глиф символа (или «?» для неизвестного)."""
    return FONT.get(ch, FONT["?"])


def text_width(text: str, tracking: int) -> int:
    """Ширина строки в колонках при заданном трекинге (промежутке)."""
    if not text:
        return 0
    return sum(glyph(ch)[0] for ch in text) + tracking * (len(text) - 1)


def render_text(text: str, tracking: int):
    """Растеризация строки шрифтом 5×7 → 7 списков из 0/1."""
    rows: list[list[int]] = [[] for _ in range(7)]
    last = len(text) - 1
    for i, ch in enumerate(text):
        w, g = glyph(ch)
        for r in range(7):
            bits = g[r]
            rows[r].extend((bits >> (w - 1 - c)) & 1 for c in range(w))
        if i != last:
            for r in range(7):
                rows[r].extend([0] * tracking)
    return rows


def pick_tracking(text: str, cols: int, want: int, symmetrize: bool):
    """Подбор трекинга, при котором поля слева/справа строго равны.

    Возвращает (трекинг, подгоняли_ли). Если варианта нет — исходный трекинг.
    """
    if not symmetrize:
        return want, False
    cands = [want]
    cands += [want + d for d in range(1, 6)]
    cands += [want - d for d in range(1, max(1, want) + 1)]
    seen: set[int] = set()
    for t in cands:
        if t < 0 or t in seen:
            continue
        seen.add(t)
        free = cols - text_width(text, t)
        if free >= 2 and free % 2 == 0:
            return t, t != want
    return want, False


# ------------------------------------------------------------ ПАЛИТРА ---

REQUIRED_ROLES = ("bg", "main", "fringe_left", "fringe_right")


def load_palette(path: Path) -> dict:
    """Палитра из JSON: список цветов, id = позиция (№ коробочки)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    colors = data.get("colors") or []
    if not colors:
        sys.exit(f"Палитра {path}: пустой список colors.")
    roles: dict[str, int] = {}
    for i, c in enumerate(colors, start=1):
        c["id"] = i
        c.setdefault("name", f"цвет {i}")
        hexv = str(c.get("hex", "#000000")).lstrip("#")
        if len(hexv) == 3:
            hexv = "".join(x * 2 for x in hexv)
        if len(hexv) != 6:
            sys.exit(f"Палитра {path}: плохой HEX у цвета №{i}.")
        c["hex"] = "#" + hexv.lower()
        roles[str(c.get("role", ""))] = i
    missing = [r for r in REQUIRED_ROLES if r not in roles]
    if missing:
        sys.exit(f"Палитра {path}: нет ролей: {', '.join(missing)}.")
    data["role"] = roles
    return data


# --------------------------------------------------------- СЕТКА+ГЛИТЧ ---

def build_grid(text, cols, rows_n, *, tracking, glitch, seed, pal,
               rgb_shift=0, mirror=False, symmetrize=True):
    """Сетка пояса rows_n×cols с центрированной глитч-надписью.

    Ячейка — целое число: № цвета из палитры (№ коробочки).
    """
    if rows_n < 7:
        sys.exit(f"Ширина пояса — {rows_n} рядов, а текст занимает 7. "
                 f"Увеличьте --width-cm или уменьшите --pitch-mm.")
    tr, tr_adj = pick_tracking(text, cols, tracking, symmetrize)
    tgrid = render_text(text, tr)
    W = text_width(text, tr)
    if W > cols - 2:
        sys.exit(f"Надпись ({W} колонок при трекинге {tr}) не влезает "
                 f"в сетку ({cols} колонок). Увеличьте длину или сократите текст.")

    free, free_v = cols - W, rows_n - 7
    left, right = free // 2, free - free // 2
    top, bottom = free_v // 2, free_v - free_v // 2

    role = pal["role"]
    c_bg, c_main = role["bg"], role["main"]
    c_fl, c_fr = role["fringe_left"], role["fringe_right"]

    grid = [[c_bg] * cols for _ in range(rows_n)]
    rng = random.Random(seed)
    g = max(0.0, min(1.0, glitch))
    shift = rgb_shift if rgb_shift > 0 else max(1, int(1 + 1.5 * g + 0.5))

    def put_text():
        for r in range(7):
            row = grid[top + r]
            for c in range(W):
                if tgrid[r][c]:
                    row[left + c] = c_main

    if g <= 0:
        put_text()
    else:
        # 1) RGB-сдвиг: маджена слева, циан справа (только по фону)
        for r in range(7):
            row = grid[top + r]
            for c in range(W):
                if tgrid[r][c]:
                    for cc, col_id in ((left + c - shift, c_fl),
                                       (left + c + shift, c_fr)):
                        if 0 <= cc < cols and row[cc] == c_bg:
                            row[cc] = col_id
        # 2) основной текст поверх
        put_text()
        # 3) «выпадения» пикселей (бисерина пропадает в фон)
        p_dim = 0.25 * g
        for r in range(7):
            for c in range(W):
                if tgrid[r][c] and grid[top + r][left + c] == c_main:
                    if rng.random() < p_dim:
                        grid[top + r][left + c] = c_bg
        # 4) сдвиг срезов: горизонтальные полосы едут влево/вправо
        zone0, zone1 = max(0, top - 1), min(rows_n, top + 8)
        opts = [d for d in (-3, -2, -1, 1, 2, 3)][: 2 + int(round(2 * g))] or [1]
        for _ in range(max(1, round(g * rows_n * 0.5))):
            h = rng.choice((1, 1, 2))
            r_hi = max(zone0 + 1, zone1 - h + 1)
            r0 = rng.randrange(zone0, r_hi)
            d = rng.choice(opts)
            for r in range(r0, min(r0 + h, rows_n)):
                row = grid[r]
                grid[r] = row[d:] + row[:d]
        # 5) блэкаут-блоки: куски надписи «пропадают»
        for _ in range(int(round(g * 3))):
            bw, bh = rng.randint(4, 10), rng.randint(1, 2)
            r_hi = max(zone0 + 1, zone1 - bh + 1)
            r0 = rng.randrange(zone0, r_hi)
            lo, hi = max(0, left - shift), min(cols - bw, left + W + shift)
            if hi > lo:
                c0 = rng.randrange(lo, hi + 1)
                for r in range(r0, r0 + bh):
                    for c in range(c0, c0 + bw):
                        grid[r][c] = c_bg

    if mirror:
        grid = [row[::-1] for row in grid]

    stats = dict(tracking=tr, tracking_adjusted=tr_adj, text_w=W,
                 left=left, right=right, top=top, bottom=bottom,
                 rgb_shift=shift)
    return grid, stats


# ---------------------------------------------------------------- SVG ---

def esc(s) -> str:
    return html.escape(str(s), quote=True)


def luminance(hexcolor: str) -> float:
    v = hexcolor.lstrip("#")
    r, g, b = (int(v[i:i + 2], 16) for i in (0, 2, 4))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def ink_for(hexcolor: str) -> str:
    """Цвет цифры внутри кружка — контрастная к заливке."""
    return "#111111" if luminance(hexcolor) > 0.55 else "#ffffff"


def num_font_size(circle_d: float, s: str) -> float:
    n = len(s)
    k = 0.74 if n == 1 else 0.58 if n == 2 else 0.46
    return circle_d * k


def segment_svg(grid, c0, c1, pal, pitch, circle_d, show_numbers=True) -> str:
    """SVG-сегмент сетки: колонки c0..c1 (не вкл.), мм-размеры точные."""
    rows_n = len(grid)
    n = c1 - c0
    w = GUTTER + n * pitch + 1.0
    h = RULER_H + rows_n * pitch + 0.8
    out = [f'<svg width="{w:.2f}mm" height="{h:.2f}mm" '
           f'viewBox="0 0 {w:.3f} {h:.3f}" xmlns="http://www.w3.org/2000/svg">']
    # линейка колонок: засечка каждые 5, номер каждые 10 (глобальная нумерация)
    y0 = 2.3
    out.append(f'<line x1="{GUTTER:.2f}" y1="{y0}" '
               f'x2="{GUTTER + n * pitch:.2f}" y2="{y0}" '
               f'stroke="#777" stroke-width="0.15"/>')
    for i in range(n + 1):
        col = c0 + i
        if col % 5:
            continue
        x = GUTTER + i * pitch
        tall = col % 10 == 0
        out.append(f'<line x1="{x:.2f}" y1="{y0 - (1.1 if tall else 0.6):.2f}" '
                   f'x2="{x:.2f}" y2="{y0}" stroke="#777" stroke-width="0.15"/>')
        if tall and i < n:
            out.append(f'<text x="{x + pitch / 2:.2f}" y="0.55" font-size="1.5" '
                       f'fill="#777" text-anchor="middle" '
                       f'font-family="sans-serif">{col + 1}</text>')
    # сетка кружков
    rad = circle_d / 2.0
    for r, row in enumerate(grid):
        cy = RULER_H + r * pitch + pitch / 2
        out.append(f'<text x="{GUTTER - 0.7:.2f}" y="{cy:.2f}" font-size="1.6" '
                   f'fill="#555" text-anchor="end" dominant-baseline="central" '
                   f'font-family="sans-serif">{r + 1}</text>')
        for j in range(n):
            num = row[c0 + j]
            color = pal["colors"][num - 1]
            cx = GUTTER + j * pitch + pitch / 2
            out.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{rad:.2f}" '
                       f'fill="{color["hex"]}"/>')
            if show_numbers:
                s = str(num)
                out.append(f'<text x="{cx:.2f}" y="{cy:.2f}" '
                           f'font-size="{num_font_size(circle_d, s):.2f}" '
                           f'fill="{ink_for(color["hex"])}" text-anchor="middle" '
                           f'dominant-baseline="central" '
                           f'font-family="sans-serif">{s}</text>')
    out.append("</svg>")
    return "".join(out)


def ruler_svg(width_mm: float = 100.0, caption: str = "") -> str:
    """Калибровочная линейка: проверка, что печать идёт в масштабе 1:1."""
    h = 6.4
    cap = caption or f"калибровка: длина линии = {width_mm:.0f} мм"
    out = [f'<svg width="{width_mm}mm" height="{h}mm" viewBox="0 0 {width_mm:.2f} {h}" '
           f'xmlns="http://www.w3.org/2000/svg">']
    y = 3.4
    out.append(f'<line x1="0" y1="{y}" x2="{width_mm}" y2="{y}" '
               f'stroke="#333" stroke-width="0.25"/>')
    for mm in range(int(width_mm) + 1):
        tall, mid = mm % 25 == 0, mm % 5 == 0
        hh = 1.8 if tall else 1.0 if mid else 0.5
        out.append(f'<line x1="{mm}" y1="{y - hh}" x2="{mm}" y2="{y}" '
                   f'stroke="#333" stroke-width="0.15"/>')
        if tall:
            out.append(f'<text x="{mm}" y="{y - 2.1}" font-size="1.7" fill="#333" '
                       f'text-anchor="middle" font-family="sans-serif">{mm}</text>')
    out.append(f'<text x="{width_mm}" y="{h - 0.2}" font-size="1.9" fill="#555" '
               f'text-anchor="end" font-family="sans-serif">{esc(cap)}</text>')
    out.append("</svg>")
    return "".join(out)


# ---------------------------------------------------------------- HTML ---

def render_document(grid, pal, args, stats, counts):
    """Сборка самодостаточного HTML. Возвращает (html, meta)."""
    cols, rows_n = len(grid[0]), len(grid)
    pitch = args.pitch_mm
    circle_d = pitch - args.circle_gap
    used = [c for c in pal["colors"] if counts.get(c["id"], 0)]
    total = rows_n * cols

    # --- сегменты и страницы ---
    seg_cols = int((PAGE_W - 2 * PAGE_MARGIN - GUTTER - 1.0) // pitch)
    seg_cols = max(1, min(seg_cols, cols))
    segments = [(c0, min(c0 + seg_cols, cols)) for c0 in range(0, cols, seg_cols)]
    seg_h = RULER_H + rows_n * pitch + 0.8
    block_h = TITLE_H + seg_h + CUT_H
    usable_h = PAGE_H - 2 * PAGE_MARGIN

    warnings = []
    if block_h > usable_h:
        warnings.append(f"Сегмент ({block_h:.0f} мм) выше полезной высоты листа "
                        f"({usable_h:.0f} мм) — уменьшите ширину пояса или шаг.")

    header_h = min(78.0 + 6.4 * len(used) + 10.0, usable_h * 0.85)
    pages, cap = [[]], usable_h - header_h
    for i in range(len(segments)):
        if cap < block_h and pages[-1]:
            pages.append([])
            cap = usable_h
        pages[-1].append(i)
        cap -= block_h

    n_pages = len(pages)

    # --- карточка-заголовок + легенда ---
    now = dt.datetime.now()
    title = args.title or args.text
    trk = (f"трекинг {stats['tracking']}"
           + (" (подогнан для равных полей)" if stats["tracking_adjusted"] else ""))
    p_rows = [
        ("Надпись", f"«{args.text}»" + (" · зеркально" if args.mirror else "")),
        ("Изделие", f"{args.length_cm:g} × {args.width_cm:g} см "
                    f"(сетка {cols * pitch:.1f} × {rows_n * pitch:.1f} мм)"),
        ("Сетка", f"{cols} колонок × {rows_n} рядов · шаг {pitch:g} мм · "
                  f"кружок ⌀{circle_d:.1f} мм"),
        ("Всего бисерин", f"{total:,}".replace(",", " ")),
        ("Эффекты", f"glitch {args.glitch:g} · RGB-сдвиг {stats['rgb_shift']} · {trk}"),
        ("Поля текста", f"слева/справа {stats['left']}/{stats['right']} · "
                        f"сверху/снизу {stats['top']}/{stats['bottom']} колонок"),
        ("Воспроизводимость", f"seed {args.seed}"),
        ("Дата", now.strftime("%d.%m.%Y %H:%M")),
    ]
    params = "".join(f'<tr><td class="k">{esc(k)}</td><td>{esc(v)}</td></tr>'
                     for k, v in p_rows)
    leg = "".join(
        f'<tr><td class="num">{c["id"]}</td>'
        f'<td><span class="swatch" style="background:{c["hex"]}"></span></td>'
        f'<td>{esc(c["name"])}</td><td>{c["hex"]}</td>'
        f'<td>{counts[c["id"]]}</td>'
        f'<td>{counts[c["id"]] * 100.0 / total:.1f} %</td></tr>'
        for c in used)
    header_card = f"""
<div class="card">
<h1>{esc(title)} — схема пояса</h1>
<div class="sub">глитч-надпись · страниц: {n_pages} · сегментов: {len(segments)}</div>
<table class="params">{params}</table>
{ruler_svg(100.0)}
</div>
<div class="card">
<h2>Обозначения — палитра «{esc(pal.get("name", ""))}»</h2>
<table class="legend">
<tr><th>№</th><th></th><th>Название</th><th>HEX</th><th>Бисерин</th><th>Доля</th></tr>
{leg}
<tr class="total"><td></td><td></td><td>Итого</td><td></td>
<td>{total}</td><td>100&nbsp;%</td></tr>
</table>
</div>
"""

    seg_blocks = []
    for i, (c0, c1) in enumerate(segments, 1):
        seg_blocks.append(
            f'<div class="seg"><div class="seg-title">Сегмент {i} из {len(segments)} · '
            f'колонки {c0 + 1}–{c1} · ряды 1–{rows_n}</div>'
            + segment_svg(grid, c0, c1, pal, pitch, circle_d, args.numbers)
            + '<div class="cut">✂ линия отреза</div></div>')

    body = []
    first = True
    for pi, page in enumerate(pages, 1):
        body.append('<div class="page">')
        if first:
            body.append(header_card)
            first = False
        else:
            body.append(f'<div class="sub" style="margin:0 0 3mm">'
                        f'{esc(title)} — стр. {pi} · сегменты '
                        f'{page[0] + 1}–{page[-1] + 1} из {len(segments)}</div>'
                        + ruler_svg(50.0, "мера 50 мм"))
        for i in page:
            body.append(seg_blocks[i])
        body.append("</div>")

    doc = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} — схема пояса</title>
<style>{CSS}</style>
</head>
<body>
{"".join(body)}
</body>
</html>
"""
    meta = dict(pages=n_pages, segments=len(segments), warnings=warnings)
    return doc, meta


# ----------------------------------------------------------------- CLI ---

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="glitch_belt.py",
        description="Генератор печатных схем бисерных поясов с глитч-надписями "
                    "(HTML, A4, точные миллиметры).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--text", required=True,
                   help="надпись (латиница/кириллица; нижний регистр → верхний)")
    p.add_argument("--length-cm", type=float, default=90.0, help="длина изделия, см")
    p.add_argument("--width-cm", type=float, default=4.0, help="ширина изделия, см")
    p.add_argument("--pitch-mm", type=float, default=2.5,
                   help="шаг сетки (межцентровое расстояние), мм")
    p.add_argument("--circle-gap", type=float, default=0.4,
                   help="зазор между кружками, мм (диаметр = шаг − зазор)")
    p.add_argument("--glitch", type=float, default=0.5,
                   help="интенсивность глитча 0…1 (0 = чистый текст)")
    p.add_argument("--seed", type=int, default=42,
                   help="зерно генератора — схема воспроизводима")
    p.add_argument("--tracking", type=int, default=1,
                   help="промежуток между буквами, колонок")
    p.add_argument("--no-symmetrize", action="store_true",
                   help="не подгонять трекинг ради равных полей")
    p.add_argument("--rgb-shift", type=int, default=0,
                   help="сдвиг RGB-каналов, колонок (0 = авто)")
    p.add_argument("--mirror", action="store_true",
                   help="зеркальная схема (для техник с обратным чтением)")
    p.add_argument("--no-numbers", dest="numbers", action="store_false",
                   help="печатать кружки без номеров")
    p.add_argument("--palette", type=Path, default=DEFAULT_PALETTE,
                   help="файл палитры JSON")
    p.add_argument("--title", default="",
                   help="заголовок схемы (по умолчанию — текст)")
    p.add_argument("--out", type=Path, default=None,
                   help="выходной HTML (по умолчанию patterns/out/<имя>.html)")
    p.set_defaults(numbers=True)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    text = " ".join(args.text.upper().split())
    if not text:
        sys.exit("Пустая надпись.")
    unknown = sorted({ch for ch in text if ch not in FONT})
    if unknown:
        sys.exit("В шрифте 5×7 нет символов: " + ", ".join(unknown))
    if not 0.0 <= args.glitch <= 1.0:
        sys.exit("--glitch должен быть от 0 до 1.")
    if args.pitch_mm <= 0.2:
        sys.exit("--pitch-mm слишком мал (минимум 0.2 мм).")
    circle_d = args.pitch_mm - args.circle_gap
    if circle_d < 0.8:
        sys.exit(f"Диаметр кружка {circle_d:.2f} мм слишком мал — "
                 f"уменьшите --circle-gap.")

    pal = load_palette(args.palette)
    cols = max(1, round(args.length_cm * 10.0 / args.pitch_mm))
    rows_n = max(1, round(args.width_cm * 10.0 / args.pitch_mm))

    grid, stats = build_grid(
        text, cols, rows_n, tracking=args.tracking, glitch=args.glitch,
        seed=args.seed, pal=pal, rgb_shift=args.rgb_shift,
        mirror=args.mirror, symmetrize=not args.no_symmetrize)
    counts = Counter(v for row in grid for v in row)
    assert sum(counts.values()) == rows_n * cols, "счётчик бисерин не сходится"

    doc, meta = render_document(grid, pal, args, stats, counts)

    out = args.out
    if out is None:
        slug = re.sub(r"[^0-9A-Za-zА-Яа-яЁё]+", "_",
                      args.title or text).strip("_") or "belt"
        out = HERE / "out" / f"{slug}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")

    print(f"Надпись: {text}")
    print(f"Сетка: {cols} × {rows_n} = {cols * args.pitch_mm:.1f} × "
          f"{rows_n * args.pitch_mm:.1f} мм · шаг {args.pitch_mm:g} мм · "
          f"кружок ⌀{circle_d:.2f} мм")
    sym = ("равные" if stats["left"] == stats["right"]
           else f"{stats['left']}/{stats['right']} — НЕ равные")
    print(f"Текст: {stats['text_w']} колонок · поля слева/справа {sym} · "
          f"сверху/снизу {stats['top']}/{stats['bottom']}")
    if stats["top"] != stats["bottom"]:
        print("  ⚠ нечётный свободный ряд по вертикали — поля отличаются на 1 ряд")
    print("Бисерины по коробочкам:")
    for c in pal["colors"]:
        if counts.get(c["id"]):
            print(f"  №{c['id']} {c['hex']} {c['name']}: {counts[c['id']]}")
    for w in meta["warnings"]:
        print(f"⚠ {w}")
    print(f"Страниц: {meta['pages']} · сегментов: {meta['segments']}")
    print(f"Готово: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
