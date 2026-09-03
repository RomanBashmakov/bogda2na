#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""belt_rus.py — генератор схемы пояса belt_90 с этническим русским
геометрическим орнаментом: ромб → крест → ёлочка, раппорт 40×10 клеток,
5 повторов = 200×10 (= 900×45 мм, шаг 4.5, кружок ⌀3 — пресет belt_90
из patterns/config.json). Выход — HTML в том же виде, что выдаёт glitch.py
(A4, SVG-сегменты, легенда, калибровка). Рендер переиспользуется
импортом из ../patterns/glitch.py.

Запуск (из любой папки):  python3 belt_rus_generator/belt_rus.py
Выход:                    belt_rus_generator/out/poyas_etno.html
"""

import datetime as dt
import sys
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PATTERNS = SCRIPT_DIR.parent / "patterns"
sys.path.insert(0, str(PATTERNS))

import glitch  # noqa: E402

COLS, ROWS, RAP, REPEATS = 200, 10, 40, 5
PITCH, CIRCLE_D = 4.5, 3.0
TITLE = "Пояс этно · ромб-крест-ёлочка"
OUT = SCRIPT_DIR / "out" / "poyas_etno.html"

W, SC, CR, BK, GD, GR, BL = range(7)  # белый, алый, багряный, чёрный, золото, зелёный, синий

PAL = {"name": "этнический русский", "colors": [
    {"id": W,  "name": "Белый (фон)", "hex": "#f4f4f4"},
    {"id": SC, "name": "Алый",        "hex": "#d21f26"},
    {"id": CR, "name": "Багряный",    "hex": "#7a1420"},
    {"id": BK, "name": "Чёрный",      "hex": "#141414"},
    {"id": GD, "name": "Золотой",     "hex": "#e8b537"},
    {"id": GR, "name": "Зелёный",     "hex": "#2e7d43"},
    {"id": BL, "name": "Синий",       "hex": "#2e4fd8"},
]}


def build_rapport():
    """Один раппорт орнамента: 10 рядов × 40 колонок, клетки = № цвета."""
    g = [[W] * RAP for _ in range(ROWS)]
    for c in range(RAP):                          # окантовка ленты
        g[0][c], g[1][c], g[8][c], g[9][c] = BK, SC, SC, BK
    for c0 in (0, 18, 30):                        # разделители мотивов
        for r in (3, 6):
            g[r][c0] = g[r][c0 + 1] = BK
    # ромб: алый контур, багряное ядро, золотые вершины и отростки-«репьи»
    for c in (9, 10):
        g[2][c] = g[7][c] = GD
    for c in (8, 11):
        g[3][c] = g[6][c] = SC
    for r in (4, 5):
        g[r][7], g[r][12] = SC, SC
        for c in (5, 6, 13, 14):
            g[r][c] = GD
        g[r][9] = g[r][10] = CR
    # крест: зелёный, середина и концы золотые
    for c in (24, 25):
        g[2][c] = g[7][c] = GD
        g[3][c] = g[6][c] = GR
        g[4][c] = g[5][c] = GD
    for r in (4, 5):
        g[r][21] = g[r][28] = GD
        for c in (22, 23, 26, 27):
            g[r][c] = GR
    # ёлочка: три яруса стрелок, верхушка алая
    for r0 in (2, 4, 6):
        for c in (35, 36):
            g[r0][c] = SC if r0 == 2 else BL
        for c in (33, 34, 37, 38):
            g[r0 + 1][c] = BL
    return g


def build_grid():
    rap = build_rapport()
    return [row * REPEATS for row in rap]


def render_document(grid, pal, counts, title):
    """Та же сборка HTML, что в glitch.render_document, поля — про орнамент."""
    cols, rows_n = len(grid[0]), len(grid)
    pitch, circle_d = PITCH, CIRCLE_D
    used = [c for c in pal["colors"] if counts.get(c["id"], 0)]
    total = rows_n * cols

    seg_cols = int((glitch.PRINT_SAFE_W - glitch.GUTTER - 1.0) // pitch)
    seg_cols = max(1, min(seg_cols, cols))
    segments = [(c0, min(c0 + seg_cols, cols)) for c0 in range(0, cols, seg_cols)]
    seg_h = glitch.RULER_H + rows_n * pitch + 0.8
    block_h = glitch.TITLE_H + seg_h + glitch.CUT_H + glitch.SEG_GAP
    usable_h = glitch.PAGE_H - 2 * glitch.PAGE_MARGIN

    header_h = min(100.0 + 6.4 * len(used) + 10.0, usable_h * 0.85)
    pages, cap = [[]], usable_h - header_h
    for i in range(len(segments)):
        if cap < block_h and pages[-1]:
            pages.append([])
            cap = usable_h
        pages[-1].append(i)
        cap -= block_h
    n_pages = len(pages)

    now = dt.datetime.now()
    p_rows = [
        ("Рисунок", "«ромб → крест → ёлочка» · раппорт 40 колонок × 5 повторов"),
        ("Изделие", f"{cols} колонок × {rows_n} рядов = "
                    f"{cols * pitch:.1f} × {rows_n * pitch:.1f} мм"),
        ("Кружки", f"шаг {pitch:g} мм · диаметр {circle_d:.1f} мм"),
        ("Всего бисерин", f"{total:,}".replace(",", " ")),
        ("Палитра", "7 цветов · фон белый (№0)"),
        ("Стиль", "геометрический этнический русский орнамент"),
        ("Дата", now.strftime("%d.%m.%Y %H:%M")),
    ]
    params = "".join(f'<tr><td class="k">{glitch.esc(k)}</td>'
                     f'<td>{glitch.esc(v)}</td></tr>' for k, v in p_rows)
    leg = "".join(
        f'<tr><td class="num">{c["id"]}</td>'
        f'<td><span class="swatch" style="background:{c["hex"]}"></span></td>'
        f'<td>{glitch.esc(c["name"])}</td><td>{c["hex"]}</td>'
        f'<td>{counts[c["id"]]}</td>'
        f'<td>{counts[c["id"]] * 100.0 / total:.1f} %</td></tr>'
        for c in used)
    header_card = f"""
<div class="card">
<h1>{glitch.esc(title)} — схема пояса</h1>
<div class="sub">этнический орнамент · страниц: {n_pages} · сегментов: {len(segments)}</div>
<table class="params">{params}</table>
{glitch.ruler_svg(100.0)}
</div>
<div class="card">
<h2>Обозначения — палитра «{glitch.esc(pal.get("name", ""))}»</h2>
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
            + glitch.segment_svg(grid, c0, c1, pal, pitch, circle_d, True)
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
                        f'{glitch.esc(title)} — стр. {pi} · сегменты '
                        f'{page[0] + 1}–{page[-1] + 1} из {len(segments)}</div>'
                        + glitch.ruler_svg(50.0, "мера 50 мм"))
        for i in page:
            body.append(seg_blocks[i])
        body.append("</div>")

    doc = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{glitch.esc(title)} — схема пояса</title>
<style>{glitch.CSS}</style>
</head>
<body>
{"".join(body)}
</body>
</html>
"""
    meta = dict(pages=n_pages, segments=len(segments),
                seg_cols=seg_cols, seg_w_mm=seg_cols * pitch)
    return doc, meta


def main() -> int:
    grid = build_grid()
    assert len(grid) == ROWS and all(len(r) == COLS for r in grid)
    counts = Counter(v for row in grid for v in row)
    assert sum(counts.values()) == ROWS * COLS == 2000
    assert set(counts) <= set(range(7))
    expected = {W: 810, SC: 450, CR: 20, BK: 460, GD: 120, GR: 60, BL: 80}
    assert dict(counts) == expected, (dict(counts), expected)

    print("Раппорт 40×10 (один повтор):")
    for row in build_rapport():
        print("  " + "".join(str(v) for v in row))

    doc, meta = render_document(grid, PAL, counts, TITLE)
    assert doc.count("<circle ") == 2000
    assert doc.count("</html>") == 1
    assert meta["seg_w_mm"] + glitch.GUTTER + 1.0 <= glitch.PRINT_SAFE_W

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")

    print("Пресет: belt_90 (config.json)")
    print("Рисунок: ромб → крест → ёлочка · раппорт 40 колонок × 5 повторов")
    print(f"Сетка: {COLS} × {ROWS} = {COLS * PITCH:.1f} × {ROWS * PITCH:.1f} мм · "
          f"шаг {PITCH:g} мм · кружок ⌀{CIRCLE_D:.2f} мм")
    print("Бисерины по коробочкам:")
    for c in PAL["colors"]:
        print(f"  №{c['id']} {c['hex']} {c['name']}: {counts[c['id']]}")
    print(f"Страниц: {meta['pages']} · сегментов: {meta['segments']}")
    print(f"Готово: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
