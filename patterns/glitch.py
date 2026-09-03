#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
glitch.py — генератор печатных схем бисерных поясов с глитч-надписями.

Что делает
----------
* растрирует надпись многоцветным пиксельным шрифтом 7×6 из файла type.txt:
  каждый пиксель буквы несёт свой цвет 0-5 (слева пурпурный/жёлтый, в середине
  белый, справа голубой/синий) — «шлейф» зашит в сам шрифт;
* искажения (выпадения пикселей, сдвиг срезов, блэкауты) — опционально,
  флаги --dropout / --slices / --blackout, сила — --glitch;
* строит сетку кружочков с фиксированным шагом в миллиметрах — под печатную
  оснастку с отверстиями: расстояния и диаметры всегда одинаковы;
* номер внутри кружка — порядковый номер цвета из палитры (номер коробочки):
  достал бисерину из коробочки №N → положил на кружок №N;
* выпускает самодостаточный HTML (A4, inline SVG): сегменты пояса с линейками
  и линиями отреза, легенда с подсчётом бисерин, калибровочная линейка.

Зависимости: только стандартная библиотека Python 3.8+.

Пример
------
    python3 glitch.py -t belt_90 --text "ГЛИТЧ" \\
        --seed 42 --title "Пояс №1" --out out/poyas1.html
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
DEFAULT_CONFIG = HERE / "config.json"
DEFAULT_FONT = HERE / "type.txt"

# Шрифт: глиф 7 колонок × 6 рядов, клетка — цифра цвета 0-5 (0 = фон).
GLYPH_W, GLYPH_H = 7, 6

# --- Геометрия страницы A4 (мм) ---
PAGE_W, PAGE_H = 210.0, 297.0   # портрет
PAGE_MARGIN = 8.0               # поля печати (CSS @page)
PRINT_SAFE_W = 182.0            # консервативная ширина печати: сегменты
                                # влезают даже при полях браузера/принтера
                                # «по умолчанию» (~12.7 мм на сторону)
GUTTER = 7.0                    # поле слева под номера рядов
RULER_H = 3.6                   # линейка колонок над сеткой
CUT_H = 8.8                     # линия отреза: текст + отступы (реальная высота)
TITLE_H = 4.3                   # заголовок сегмента
SEG_GAP = 1.0                   # отбивка между сегментами (.seg margin)

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

# --------------------------------------------------------- ШРИФТ 7×6 ---
# Многоцветный пиксельный шрифт живёт в type.txt: глиф = строка-метка +
# 6 строк по 7 цифр 0-5 (0 — фон/пусто, 1-5 — цвета = номера коробочек).
# Шрифт можно править в файле — код перечитывает его при каждом запуске.


def load_font(path: Path) -> dict:
    """Шрифт из type.txt: {символ: 6 кортежей по 7 цифр 0-5}.

    Блоки разделяются пустыми строками; блок из одной строки — комментарий.
    Метка «_» обозначает пробел.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        sys.exit(f"Не читается файл шрифта {path}: {e}")
    blocks, cur = [], []
    for ln in raw.splitlines():
        if ln.strip():
            cur.append(ln)
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)

    glyphs: dict = {}
    for block in blocks:
        if len(block) == 1:          # строка-комментарий (шапка файла)
            continue
        if len(block) != 1 + GLYPH_H:
            sys.exit(f"Шрифт {path}: блок «{block[0]}» — нужно "
                     f"{1 + GLYPH_H} строк (метка + {GLYPH_H} рядов), "
                     f"получено {len(block)}.")
        label = " " if block[0] == "_" else block[0]
        if len(label) != 1:
            sys.exit(f"Шрифт {path}: «{block[0]}» — метка глифа должна "
                     f"быть одним символом.")
        rows = []
        for i, row in enumerate(block[1:], 1):
            if len(row) != GLYPH_W or set(row) - set("012345"):
                sys.exit(f"Шрифт {path}: глиф «{block[0]}», строка {i}: "
                         f"«{row}» — нужно {GLYPH_W} цифр из 0-5.")
            rows.append(tuple(int(d) for d in row))
        if label in glyphs:
            sys.exit(f"Шрифт {path}: глиф «{block[0]}» определён дважды.")
        glyphs[label] = tuple(rows)
    if not glyphs:
        sys.exit(f"Шрифт {path}: не найдено ни одного глифа.")
    return glyphs


def text_width(text: str, tracking: int) -> int:
    """Ширина строки в колонках при заданном трекинге (промежутке)."""
    if not text:
        return 0
    return GLYPH_W * len(text) + tracking * (len(text) - 1)


def render_text(text: str, font: dict, tracking: int):
    """Растеризация строки шрифтом 7×6 → 6 списков из цифр 0-5."""
    rows: list[list[int]] = [[] for _ in range(GLYPH_H)]
    last = len(text) - 1
    for i, ch in enumerate(text):
        g = font[ch]
        for r in range(GLYPH_H):
            rows[r].extend(g[r])
        if i != last:
            for r in range(GLYPH_H):
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


# --------------------------------------------------------------- КОНФИГ ---

N_COLORS = 6  # цифры шрифта 0-5

# Запасные цвета — когда пресет не задаёт свои. Порядок = цифры шрифта.
FALLBACK_COLORS = (
    ("Чёрный (фон)", "#141414"),
    ("Пурпурный", "#b23ad6"),
    ("Жёлтый", "#f5c518"),
    ("Белый", "#f4f4f4"),
    ("Голубой", "#3fb8e8"),
    ("Синий", "#2e4fd8"),
)


def _norm_hex(v, what: str) -> str:
    hexv = str(v).lstrip("#")
    if len(hexv) == 3:
        hexv = "".join(x * 2 for x in hexv)
    if len(hexv) != 6 or any(c not in "0123456789abcdefABCDEF" for c in hexv):
        sys.exit(f"Конфиг: плохой HEX {v!r} у цвета {what}.")
    return "#" + hexv.lower()


def load_config(path: Path, preset):
    """Пресет из конфига. Без -t возвращает {} — работают флаги и запасные
    значения. Ключи конфига, начинающиеся с «_», — комментарии.
    """
    if preset is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        sys.exit(f"Не читается файл конфига {path}: {e}")
    except json.JSONDecodeError as e:
        sys.exit(f"Конфиг {path}: повреждённый JSON ({e}).")
    presets = {k: v for k, v in data.items() if not k.startswith("_")}
    if preset not in presets:
        names = ", ".join(sorted(presets)) or "пресетов нет"
        sys.exit(f"В конфиге {path} нет пресета «{preset}». Доступны: {names}.")
    cfg = presets[preset]
    if not isinstance(cfg, dict):
        sys.exit(f"Конфиг {path}: пресет «{preset}» должен быть объектом "
                 f"{{...}}, а не списком или числом.")
    return cfg


def make_palette(cfg: dict, preset) -> dict:
    """Палитра из пресета (поле colors) либо запасная: 6 цветов, id = 0-5."""
    raw = cfg.get("colors")
    if raw is None:
        items = [{"name": n, "hex": h} for n, h in FALLBACK_COLORS]
        name = "запасная RGB Split"
    else:
        if not isinstance(raw, list) or len(raw) != N_COLORS:
            sys.exit(f"Конфиг: поле colors пресета должно быть списком из "
                     f"{N_COLORS} цветов (цифры шрифта 0-5).")
        items = [{"name": str(c.get("name", f"цвет {i}")),
                  "hex": _norm_hex(c.get("hex", "#000000"), f"№{i}")}
                 for i, c in enumerate(raw)]
        name = str(preset)
    for i, c in enumerate(items):
        c["id"] = i
    return {"name": name, "colors": items}


# --------------------------------------------------------- СЕТКА+ГЛИТЧ ---

def build_grid(text, cols, rows_n, *, tracking, glitch, seed, pal, font,
               mirror=False, symmetrize=True,
               dropout=False, slices=False, blackout=False):
    """Сетка пояса rows_n×cols с центрированной многоцветной надписью.

    Ячейка — целое число: № цвета из палитры = цифра шрифта (№ коробочки).
    Цветной «шлейф» зашит в сам шрифт; искажения — по флагам.
    """
    if rows_n < GLYPH_H:
        sys.exit(f"Ширина пояса — {rows_n} рядов, а текст занимает {GLYPH_H}. "
                 f"Увеличьте --rows (или поле rows в пресете).")
    tr, tr_adj = pick_tracking(text, cols, tracking, symmetrize)
    tgrid = render_text(text, font, tr)
    W = text_width(text, tr)
    if W > cols - 2:
        sys.exit(f"Надпись ({W} колонок при трекинге {tr}) не влезает "
                 f"в сетку ({cols} колонок). Увеличьте --cols или "
                 f"сократите текст.")

    free, free_v = cols - W, rows_n - GLYPH_H
    left, right = free // 2, free - free // 2
    top, bottom = free_v // 2, free_v - free_v // 2

    c_bg = pal["colors"][0]["id"]

    grid = [[c_bg] * cols for _ in range(rows_n)]
    rng = random.Random(seed)
    g = max(0.0, min(1.0, glitch))

    # 1) надпись: цвет каждого пикселя берётся из шрифта
    for r in range(GLYPH_H):
        row = grid[top + r]
        for c in range(W):
            if tgrid[r][c]:
                row[left + c] = tgrid[r][c]
    # 2) «выпадения» пикселей в фон — только с флагом --dropout
    if dropout:
        p_dim = 0.25 * g
        for r in range(GLYPH_H):
            for c in range(W):
                if tgrid[r][c] and grid[top + r][left + c] != c_bg:
                    if rng.random() < p_dim:
                        grid[top + r][left + c] = c_bg
    # 3) сдвиг срезов — только с флагом --slices
    if slices:
        zone0, zone1 = max(0, top - 1), min(rows_n, top + GLYPH_H + 1)
        opts = ([d for d in (-3, -2, -1, 1, 2, 3)]
                [: 2 + int(round(2 * g))] or [1])
        for _ in range(max(1, round(g * rows_n * 0.5))):
            h = rng.choice((1, 1, 2))
            r_hi = max(zone0 + 1, zone1 - h + 1)
            r0 = rng.randrange(zone0, r_hi)
            d = rng.choice(opts)
            for r in range(r0, min(r0 + h, rows_n)):
                row = grid[r]
                grid[r] = row[d:] + row[:d]
    # 4) блэкаут-блоки — только с флагом --blackout
    if blackout:
        zone0, zone1 = max(0, top - 1), min(rows_n, top + GLYPH_H + 1)
        for _ in range(int(round(g * 3))):
            bw, bh = rng.randint(4, 10), rng.randint(1, 2)
            r_hi = max(zone0 + 1, zone1 - bh + 1)
            r0 = rng.randrange(zone0, r_hi)
            lo, hi = max(0, left), min(cols - bw, left + W)
            if hi > lo:
                c0 = rng.randrange(lo, hi + 1)
                for r in range(r0, r0 + bh):
                    for c in range(c0, c0 + bw):
                        grid[r][c] = c_bg

    if mirror:
        grid = [row[::-1] for row in grid]

    stats = dict(tracking=tr, tracking_adjusted=tr_adj, text_w=W,
                 left=left, right=right, top=top, bottom=bottom)
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
            color = pal["colors"][num]
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
    circle_d = args.circle_d_mm
    used = [c for c in pal["colors"] if counts.get(c["id"], 0)]
    total = rows_n * cols

    # --- сегменты и страницы ---
    # ширину считаем от консервативной печатной ширины: сетка не выйдет за
    # лист, даже если диалог печати применит поля больше CSS-ных 8 мм
    seg_cols = int((PRINT_SAFE_W - GUTTER - 1.0) // pitch)
    seg_cols = max(1, min(seg_cols, cols))
    segments = [(c0, min(c0 + seg_cols, cols)) for c0 in range(0, cols, seg_cols)]
    seg_h = RULER_H + rows_n * pitch + 0.8
    block_h = TITLE_H + seg_h + CUT_H + SEG_GAP
    usable_h = PAGE_H - 2 * PAGE_MARGIN

    warnings = []
    if block_h > usable_h:
        warnings.append(f"Сегмент ({block_h:.0f} мм) выше полезной высоты листа "
                        f"({usable_h:.0f} мм) — уменьшите ширину пояса или шаг.")

    header_h = min(100.0 + 6.4 * len(used) + 10.0, usable_h * 0.85)
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
    fx = ["многоцветный шрифт (type.txt)"]
    if args.dropout:
        fx.append("выпадения")
    if args.slices:
        fx.append("срезы")
    if args.blackout:
        fx.append("блэкауты")
    fx.append(trk)
    p_rows = [
        ("Надпись", f"«{args.text}»" + (" · зеркально" if args.mirror else "")),
        ("Изделие", f"{cols} колонок × {rows_n} рядов = "
                    f"{cols * pitch:.1f} × {rows_n * pitch:.1f} мм"),
        ("Кружки", f"шаг {pitch:g} мм · диаметр {circle_d:.1f} мм"),
        ("Всего бисерин", f"{total:,}".replace(",", " ")),
        ("Эффекты", " · ".join(fx)),
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

def print_help_card() -> None:
    """Короткая шпаргалка: пример запуска, пресеты, частые флаги."""
    L = ["Генератор печатных схем бисерных надписей (HTML · A4 · точные мм)",
         "",
         "ЗАПУСК — примеры (из папки со скриптом):",
         '  python3 glitch.py -t bracelet_19 --text "БОГДАННА"',
         '  python3 glitch.py -t belt_90 --text "ГЛИТЧ"'
         " --out out/poyas1.html",
         '  python3 glitch.py --cols 100 --rows 10 --text "ЭХО"',
         ""]
    try:
        data = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
        presets = sorted(k for k, v in data.items()
                         if not k.startswith("_") and isinstance(v, dict))
    except (OSError, json.JSONDecodeError):
        data, presets = {}, []
    if presets:
        L.append(f"ПРЕСЕТЫ ({DEFAULT_CONFIG.name}):")
        for name in presets:
            v = data[name]
            parts = []
            if "cols" in v or "rows" in v:
                parts.append(f"{v.get('cols', '?')}×{v.get('rows', '?')} клеток")
            if v.get("pitch_mm") is not None:
                parts.append(f"шаг {v['pitch_mm']:g} мм")
            if v.get("circle_d_mm") is not None:
                parts.append(f"кружок {v['circle_d_mm']:g} мм")
            desc = " · ".join(parts) if parts else "размеры в конфиге"
            L.append(f"  -t {name}{' ' * max(1, 14 - len(name))}{desc}")
        L.append("")
    L += ["ЧАСТО ИСПОЛЬЗУЕТСЯ:",
          '  --text "ТЕКСТ"      надпись (строчные → ЗАГЛАВНЫЕ)',
          "  --cols N, --rows N  размер полотна в клетках (переопределяют пресет)",
          "  --out ФАЙЛ          выходной HTML (по умолчанию out/<надпись>.html)",
          "  --no-numbers        кружки без цифр-номеров коробочек",
          "  --mirror            зеркальная схема",
          "  --seed N            вариант искажений (--dropout/--slices/--blackout)",
          "",
          "ФАЙЛЫ (лежат рядом со скриптом):",
          "  config.json — пресеты: размеры, кружочки, цвета бисера",
          "  type.txt    — шрифт: глиф = метка + 6 строк по 7 цифр 0-5",
          "",
          "Полный список параметров: python3 glitch.py --help"]
    print("\n".join(L))


def parse_args(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    if not args or args[0] == "help":
        print_help_card()
        raise SystemExit(0)
    p = argparse.ArgumentParser(
        prog="glitch.py",
        description="Генератор печатных схем бисерных поясов с глитч-надписями "
                    "(HTML, A4, точные миллиметры).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("-c", "--config", type=Path, default=DEFAULT_CONFIG,
                   help="файл конфига с пресетами (JSON)")
    p.add_argument("-t", "--preset", default=None,
                   help="имя пресета из конфига, напр. bracelet_19")
    p.add_argument("--text", required=True,
                   help="надпись (латиница/кириллица; нижний регистр → верхний)")
    p.add_argument("--cols", type=int, default=None,
                   help="длина изделия в клетках-колонках "
                        "(по умолчанию: пресет -t или 360)")
    p.add_argument("--rows", type=int, default=None,
                   help="ширина изделия в рядах (по умолчанию: пресет -t или 16)")
    p.add_argument("--pitch-mm", type=float, default=None,
                   help="шаг сетки — расстояние между центрами кружочков, мм "
                        "(по умолчанию: пресет -t или 2.5)")
    p.add_argument("--circle-d-mm", type=float, default=None,
                   help="диаметр кружочка, мм (по умолчанию: пресет -t или шаг − 0.4)")
    p.add_argument("--glitch", type=float, default=0.5,
                   help="сила искажений 0…1 для --dropout/--slices/"
                        "--blackout (на чистый текст не влияет)")
    p.add_argument("--dropout", action="store_true",
                   help="«выпадения» пикселей текста в фон (по умолчанию выкл.)")
    p.add_argument("--slices", action="store_true",
                   help="сдвиг горизонтальных срезов (по умолчанию выкл.)")
    p.add_argument("--blackout", action="store_true",
                   help="блэкаут-блоки: куски надписи пропадают (по умолчанию выкл.)")
    p.add_argument("--seed", type=int, default=42,
                   help="зерно генератора — схема воспроизводима")
    p.add_argument("--tracking", type=int, default=1,
                   help="промежуток между буквами, колонок")
    p.add_argument("--font", type=Path, default=None,
                   help="файл шрифта (по умолчанию: пресет -t или type.txt)")
    p.add_argument("--no-symmetrize", action="store_true",
                   help="не подгонять трекинг ради равных полей")
    p.add_argument("--mirror", action="store_true",
                   help="зеркальная схема (для техник с обратным чтением)")
    p.add_argument("--no-numbers", dest="numbers", action="store_false",
                   help="печатать кружки без номеров")
    p.add_argument("--title", default="",
                   help="заголовок схемы (по умолчанию — текст)")
    p.add_argument("--out", type=Path, default=None,
                   help="выходной HTML (по умолчанию out/<имя>.html)")
    p.set_defaults(numbers=True)
    return p.parse_args(args)


def main(argv=None) -> int:
    args = parse_args(argv)
    text = " ".join(args.text.upper().split())
    if not text:
        sys.exit("Пустая надпись.")
    cfg = load_config(args.config, args.preset)

    def resolve(cli, key, fallback):
        """Приоритет: флаг командной строки → поле пресета → запасное."""
        if cli is not None:
            return cli
        v = cfg.get(key)
        return fallback if v is None else v

    def as_cells(v, what):
        """Размер полотна — целое число клеток ≥ 1."""
        if (isinstance(v, bool) or not isinstance(v, (int, float))
                or float(v) != int(v) or int(v) < 1):
            sys.exit(f"Размер полотна ({what}) должен быть целым числом "
                     f"клеток от 1, получено: {v!r}.")
        return int(v)

    cols = as_cells(resolve(args.cols, "cols", 360), "колонки")
    rows_n = as_cells(resolve(args.rows, "rows", 16), "ряды")
    pitch = float(resolve(args.pitch_mm, "pitch_mm", 2.5))
    circle_d = resolve(args.circle_d_mm, "circle_d_mm", None)
    if circle_d is None:
        circle_d = pitch - 0.4          # запасное правило, как раньше
    circle_d = float(circle_d)

    if not 0.0 <= args.glitch <= 1.0:
        sys.exit("--glitch должен быть от 0 до 1.")
    if pitch <= 0.2:
        sys.exit(f"Шаг сетки {pitch:g} мм слишком мал (минимум 0.2 мм).")
    if circle_d < 0.8:
        sys.exit(f"Диаметр кружка {circle_d:.2f} мм слишком мал "
                 f"(минимум 0.8 мм).")
    if circle_d >= pitch:
        sys.exit(f"Диаметр кружка {circle_d:.2f} мм не меньше шага "
                 f"{pitch:g} мм — кружки слипнутся, уменьшите circle_d_mm.")

    pal = make_palette(cfg, args.preset)
    font_path = args.font
    if font_path is None:
        font_path = Path(cfg["font"]) if cfg.get("font") else DEFAULT_FONT
    if not font_path.is_absolute():
        cand = args.config.parent / font_path
        font_path = cand if cand.exists() else HERE / font_path
    font = load_font(font_path)
    unknown = sorted({ch for ch in text if ch not in font})
    if unknown:
        sys.exit("В шрифте нет символов: " + ", ".join(unknown)
                 + ". Добавьте глифы в файл шрифта.")

    # дальше по конвейеру — одни и те же поля args
    args.pitch_mm, args.circle_d_mm = pitch, circle_d

    grid, stats = build_grid(
        text, cols, rows_n, tracking=args.tracking, glitch=args.glitch,
        seed=args.seed, pal=pal, font=font,
        mirror=args.mirror, symmetrize=not args.no_symmetrize,
        dropout=args.dropout, slices=args.slices, blackout=args.blackout)
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

    if args.preset:
        print(f"Пресет: {args.preset} · {args.config}")
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
