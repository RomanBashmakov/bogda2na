#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""img_belt.py — генератор печатных бисерных схем из произвольной картинки.

Что делает: постеризует картинку в N цветов, разбивает на клетки-бисерины
и выпускает схему в том же виде, что glitch.py / belt_rus.py (A4, титульная
страница, легенда с подсчётом бисерин, калибровка, SVG-блоки с линейками
и линиями отреза). Большое полотно режется на блоки и по колонкам,
и по рядам — каждый блок влезает на лист; нумерация рядов и колонок
глобальная, блоки склеиваются по номерам. Рендер переиспользуется
импортом из ../patterns/glitch.py.

Запуск (из любой папки):
    python3 img_generator/img_belt.py картинка.png -n 8
Выход: img_generator/out/<имя_картинки>.html

Зависимости: Pillow (pip install Pillow).
"""

import argparse
import datetime as dt
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
PATTERNS = SCRIPT_DIR.parent / "patterns"
sys.path.insert(0, str(PATTERNS))

import glitch  # noqa: E402

# совместимость констант Pillow старых/новых версий (9.x модульные, 10+ enum)
RESAMPLE_BOX = getattr(getattr(Image, "Resampling", Image), "BOX")
DITHER_NONE = getattr(getattr(Image, "Dither", Image), "NONE", 0)
DITHER_FS = getattr(getattr(Image, "Dither", Image), "FLOYDSTEINBERG", 3)

MIN_COLORS, MAX_COLORS = 2, 30


def lum(r, g, b):
    return 0.299 * r + 0.587 * g + 0.114 * b


def load_cells(img_path: Path, cols: int, n_colors: int, dither: bool):
    """Картинка → (сетка номеров цветов, палитра, исходный размер, ряды).

    Альфа кладётся на белый фон; уменьшение усреднением (BOX);
    постеризация медианным срезом без дизеринга (если не заказан).
    """
    if not img_path.exists():
        sys.exit(f"Картинка не найдена: {img_path}.")
    try:
        im = Image.open(img_path)
        im.load()
    except Exception as e:  # битый файл или не картинка
        sys.exit(f"Не читается картинка {img_path}: {e}.")

    rgba = im.convert("RGBA")
    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    rgb = Image.alpha_composite(bg, rgba).convert("RGB")

    w, h = rgb.size
    rows = max(1, round(cols * h / w))
    small = rgb.resize((cols, rows), RESAMPLE_BOX)

    q = small.quantize(colors=n_colors,
                       dither=DITHER_FS if dither else DITHER_NONE)
    flat_palette = q.getpalette() or []
    idx_counts = Counter(q.getdata())

    # порядок номеров: по частоте (№0 ≈ фон), при равенстве — тёмные раньше
    order = sorted(
        range(n_colors),
        key=lambda i: (-idx_counts.get(i, 0),
                       lum(*flat_palette[i * 3:i * 3 + 3])))
    new_id = {old: new for new, old in enumerate(order)}

    colors = []
    for new, old in enumerate(order):
        r, g, b = flat_palette[old * 3:old * 3 + 3]
        colors.append({"id": new,
                       "name": f"RGB {r} {g} {b}",
                       "hex": f"#{r:02x}{g:02x}{b:02x}"})

    data = list(q.getdata())
    grid = [[new_id[data[r * cols + c]] for c in range(cols)]
            for r in range(rows)]
    return grid, colors, (w, h), rows


def block_svg(grid, c0, c1, r0, r1, pal, pitch, circle_d, show_numbers=True):
    """SVG-блок: колонки c0..c1 (не вкл.), ряды r0..r1 (не вкл.).

    Нумерация колонок и рядов — глобальная (для склейки блоков),
    мм-размеры точные. Аналог glitch.segment_svg + сдвиг номеров рядов.
    """
    n, m = c1 - c0, r1 - r0
    w = glitch.GUTTER + n * pitch + 1.0
    h = glitch.RULER_H + m * pitch + 0.8
    out = [f'<svg width="{w:.2f}mm" height="{h:.2f}mm" '
           f'viewBox="0 0 {w:.3f} {h:.3f}" xmlns="http://www.w3.org/2000/svg">']
    # линейка колонок: засечка каждые 5, номер каждые 10 (глобальная нумерация)
    y0 = 2.3
    out.append(f'<line x1="{glitch.GUTTER:.2f}" y1="{y0}" '
               f'x2="{glitch.GUTTER + n * pitch:.2f}" y2="{y0}" '
               f'stroke="#777" stroke-width="0.15"/>')
    for i in range(n + 1):
        col = c0 + i
        if col % 5:
            continue
        x = glitch.GUTTER + i * pitch
        tall = col % 10 == 0
        out.append(f'<line x1="{x:.2f}" y1="{y0 - (1.1 if tall else 0.6):.2f}" '
                   f'x2="{x:.2f}" y2="{y0}" stroke="#777" stroke-width="0.15"/>')
        if tall and i < n:
            out.append(f'<text x="{x + pitch / 2:.2f}" y="0.55" font-size="1.5" '
                       f'fill="#777" text-anchor="middle" '
                       f'font-family="sans-serif">{col + 1}</text>')
    # сетка кружков, номера рядов — глобальные
    rad = circle_d / 2.0
    for r in range(m):
        row = grid[r0 + r]
        cy = glitch.RULER_H + r * pitch + pitch / 2
        out.append(f'<text x="{glitch.GUTTER - 0.7:.2f}" y="{cy:.2f}" '
                   f'font-size="1.6" fill="#555" text-anchor="end" '
                   f'dominant-baseline="central" '
                   f'font-family="sans-serif">{r0 + r + 1}</text>')
        for j in range(n):
            num = row[c0 + j]
            color = pal["colors"][num]
            cx = glitch.GUTTER + j * pitch + pitch / 2
            out.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{rad:.2f}" '
                       f'fill="{color["hex"]}"/>')
            if show_numbers:
                s = str(num)
                out.append(f'<text x="{cx:.2f}" y="{cy:.2f}" '
                           f'font-size="{glitch.num_font_size(circle_d, s):.2f}" '
                           f'fill="{glitch.ink_for(color["hex"])}" '
                           f'text-anchor="middle" dominant-baseline="central" '
                           f'font-family="sans-serif">{s}</text>')
    out.append("</svg>")
    return "".join(out)


def render_document(grid, pal, counts, args, img_size):
    """Сборка HTML: блоки ≤ листа по ширине и высоте, склейка по номерам."""
    cols, rows_n = len(grid[0]), len(grid)
    pitch, circle_d = args.pitch_mm, args.circle_d_mm
    used = [c for c in pal["colors"] if counts.get(c["id"], 0)]
    total = rows_n * cols
    usable_h = glitch.PAGE_H - 2 * glitch.PAGE_MARGIN

    # сколько клеток блока влезает по ширине и по высоте листа
    seg_cols = max(1, min(int((glitch.PRINT_SAFE_W - glitch.GUTTER - 1.0)
                              // pitch), cols))
    extra_h = (glitch.TITLE_H + glitch.RULER_H + 0.8
               + glitch.CUT_H + glitch.SEG_GAP)
    seg_rows = max(1, min(int((usable_h - extra_h) // pitch), rows_n))

    col_chunks = [(c0, min(c0 + seg_cols, cols))
                  for c0 in range(0, cols, seg_cols)]
    row_bands = [(r0, min(r0 + seg_rows, rows_n))
                 for r0 in range(0, rows_n, seg_rows)]
    # порядок чтения картинки: полоса рядов за полосой, внутри — слева направо
    blocks = [(c0, c1, r0, r1) for r0, r1 in row_bands for c0, c1 in col_chunks]
    heights = [extra_h + (r1 - r0) * pitch for (c0, c1, r0, r1) in blocks]
    assert max(heights) <= usable_h + 1e-9, "блок выше полезной высоты листа"

    header_h = min(100.0 + 6.4 * len(used) + 10.0, usable_h * 0.85)
    pages, cap = [[]], usable_h - header_h
    for i, bh in enumerate(heights):
        if cap < bh:
            pages.append([])
            cap = usable_h
        pages[-1].append(i)
        cap -= bh
    n_pages = len(pages)

    now = dt.datetime.now()
    p_rows = [
        ("Картинка", f"{args.image.name} · {img_size[0]}×{img_size[1]} px"
                     + (" · зеркально" if args.mirror else "")),
        ("Изделие", f"{cols} колонок × {rows_n} рядов = "
                    f"{cols * pitch:.1f} × {rows_n * pitch:.1f} мм"),
        ("Кружки", f"шаг {pitch:g} мм · диаметр {circle_d:.1f} мм"),
        ("Всего бисерин", f"{total:,}".replace(",", " ")),
        ("Постеризация", f"{len(used)} цветов · медианный срез · "
                         + ("дизеринг Флойда—Стейнберга" if args.dither
                            else "без дизеринга")),
        ("Разбивка", f"{len(blocks)} блоков · до {seg_cols} колонок × "
                    f"{seg_rows} рядов в блоке · склейка по номерам"),
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
<h1>{glitch.esc(args.title)} — схема из картинки</h1>
<div class="sub">постеризация {len(used)} цветов · страниц: {n_pages} · блоков: {len(blocks)}</div>
<table class="params">{params}</table>
{glitch.ruler_svg(100.0)}
</div>
<div class="card">
<h2>Обозначения — палитра «из картинки {glitch.esc(args.image.stem)}»</h2>
<table class="legend">
<tr><th>№</th><th></th><th>Название</th><th>HEX</th><th>Бисерин</th><th>Доля</th></tr>
{leg}
<tr class="total"><td></td><td></td><td>Итого</td><td></td>
<td>{total}</td><td>100&nbsp;%</td></tr>
</table>
</div>
"""
    block_htmls = []
    for i, (c0, c1, r0, r1) in enumerate(blocks, 1):
        block_htmls.append(
            f'<div class="seg"><div class="seg-title">Блок {i} из {len(blocks)} · '
            f'колонки {c0 + 1}–{c1} · ряды {r0 + 1}–{r1}</div>'
            + block_svg(grid, c0, c1, r0, r1, pal, pitch, circle_d,
                        args.numbers)
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
                        f'{glitch.esc(args.title)} — стр. {pi} · блоки '
                        f'{page[0] + 1}–{page[-1] + 1} из {len(blocks)}</div>'
                        + glitch.ruler_svg(50.0, "мера 50 мм"))
        for bi in page:
            body.append(block_htmls[bi])
        body.append("</div>")

    doc = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{glitch.esc(args.title)} — схема из картинки</title>
<style>{glitch.CSS}</style>
</head>
<body>
{"".join(body)}
</body>
</html>
"""
    meta = dict(pages=n_pages, blocks=len(blocks),
                col_chunks=len(col_chunks), row_bands=len(row_bands),
                seg_cols=seg_cols, seg_rows=seg_rows,
                split=rows_n > seg_rows)
    return doc, meta


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="img_belt.py",
        description="Генератор печатных бисерных схем из картинки "
                    "(HTML · A4 · точные мм; постеризация + сетка кружков; "
                    "большое полотно режется на блоки под лист).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("image", type=Path, help="файл картинки (PNG/JPEG/…)")
    p.add_argument("-n", "--colors", type=int, default=7,
                   help=f"сколько цветов оставить ({MIN_COLORS}–{MAX_COLORS})")
    p.add_argument("--cols", type=int, default=200,
                   help="длина изделия в клетках-колонках")
    p.add_argument("--pitch-mm", type=float, default=4.5,
                   help="шаг сетки — расстояние между центрами кружочков, мм")
    p.add_argument("--circle-d-mm", type=float, default=3.0,
                   help="диаметр кружочка, мм")
    p.add_argument("--dither", action="store_true",
                   help="дизеринг Флойда—Стейнберга (по умолчанию чистые пятна)")
    p.add_argument("--mirror", action="store_true",
                   help="зеркальная схема (для техник с обратным чтением)")
    p.add_argument("--no-numbers", dest="numbers", action="store_false",
                   help="печатать кружки без цифр-номеров коробочек")
    p.add_argument("--title", default="", help="заголовок схемы")
    p.add_argument("--out", type=Path, default=None,
                   help="выходной HTML (по умолчанию out/<имя картинки>.html)")
    p.set_defaults(numbers=True)
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not MIN_COLORS <= args.colors <= MAX_COLORS:
        sys.exit(f"--colors должен быть от {MIN_COLORS} до {MAX_COLORS} "
                 f"(цифры в кружках), получено {args.colors}.")
    if args.cols < 1:
        sys.exit("--cols должен быть целым числом ≥ 1.")
    if args.pitch_mm <= 0.2:
        sys.exit(f"Шаг сетки {args.pitch_mm:g} мм слишком мал (минимум 0.2 мм).")
    if not 0.8 <= args.circle_d_mm < args.pitch_mm:
        sys.exit(f"Диаметр кружка {args.circle_d_mm:g} мм должен быть "
                 f"от 0.8 мм и меньше шага {args.pitch_mm:g} мм.")

    grid, colors, img_size, rows = load_cells(
        args.image, args.cols, args.colors, args.dither)
    if args.mirror:
        grid = [row[::-1] for row in grid]

    cols = args.cols
    pal = {"name": f"из картинки {args.image.stem}", "colors": colors}
    counts = Counter(v for row in grid for v in row)
    assert sum(counts.values()) == rows * cols
    assert set(counts) <= {c["id"] for c in colors}

    if not args.title:
        args.title = args.image.stem
    doc, meta = render_document(grid, pal, counts, args, img_size)
    assert doc.count("<circle ") == rows * cols
    assert doc.count("</html>") == 1

    out = args.out
    if out is None:
        out = SCRIPT_DIR / "out" / f"{args.image.stem}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")

    print(f"Картинка: {args.image} · {img_size[0]}×{img_size[1]} px · "
          f"рядов из пропорций: {rows}")
    print(f"Постеризация: {len(counts)} цветов · "
          + ("дизеринг" if args.dither else "без дизеринга"))
    print(f"Сетка: {cols} × {rows} = {cols * args.pitch_mm:.1f} × "
          f"{rows * args.pitch_mm:.1f} мм · шаг {args.pitch_mm:g} мм · "
          f"кружок ⌀{args.circle_d_mm:.2f} мм")
    if meta["split"]:
        print(f"  ⚠ полотно выше листа: разбито на {meta['row_bands']} полосы "
              f"рядов по ≤{meta['seg_rows']} — склеивайте блоки по номерам "
              "рядов и колонок")
    print(f"Блоков: {meta['blocks']} ({meta['col_chunks']} полос колонок × "
          f"{meta['row_bands']} полос рядов)")
    print("Бисерины по коробочкам:")
    for c in colors:
        if counts.get(c["id"]):
            print(f"  №{c['id']} {c['hex']} {c['name']}: {counts[c['id']]}")
    print(f"Страниц: {meta['pages']}")
    print(f"Готово: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
