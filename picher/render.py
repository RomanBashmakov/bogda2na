#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render.py — печатная A4-схема из JSON-схемы редактора picher.

Что делает: читает схему picher (picher/schemes/<имя>.json) и выпускает
печатный HTML в том же виде, что glitch.py / belt_rus.py (A4, титульная
страница, легенда с подсчётом бисерин, калибровка, SVG-блоки с линейками
и линиями отреза). Пустые клетки (−1) печатаются цветом №0 (фон).
Большое полотно режется на блоки и по колонкам, и по рядам — каждый блок
влезает на лист; нумерация рядов и колонок глобальная, блоки склеиваются
по номерам. Рендер переиспользуется импортом из ../patterns/glitch.py.

Запуск (из любой папки):
    python3 picher/render.py picher/schemes/моя_схема.json
Выход: picher/out/<имя схемы>.html
       + папка <имя>_colsN_colorsM/ — одноцветные схемы: файл
         <имя>_<№>.html на каждый цвет (№ = номер коробочки)
Шпаргалка с примерами: python3 picher/render.py help
(она же показывается при запуске без аргументов).

Этим же модулем пользуется web/app.py для кнопки «Распечатать A4»
в редакторе (функция write_outputs). Зависимости — только стандартная
библиотека, Pillow не нужен.
"""

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PATTERNS = SCRIPT_DIR.parent / "patterns"
if str(PATTERNS) not in sys.path:
    sys.path.insert(0, str(PATTERNS))

import glitch  # noqa: E402

HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}")


def build_scheme(data):
    """Сырой dict схемы (cols/rows/colors/cells) → представление рендера.

    Пустые клетки (−1) превращаются в цвет №0 (фон). Ошибки данных —
    ValueError с понятным текстом.
    """
    try:
        cols, rows = int(data["cols"]), int(data["rows"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("cols/rows: нужны целые числа")
    if not (1 <= cols <= 2000 and 1 <= rows <= 500):
        raise ValueError("Размер: колонок 1–2000, рядов 1–500")
    colors = data.get("colors")
    if not isinstance(colors, list) or not 1 <= len(colors) <= 64:
        raise ValueError("Цветов должно быть 1–64")
    for c in colors:
        if not isinstance(c, dict) or not HEX_RE.fullmatch(
                str(c.get("hex", ""))):
            raise ValueError("Каждый цвет: {name, hex}, hex вида #rrggbb")
    cells = data.get("cells")
    if not isinstance(cells, list):
        raise ValueError("cells: нужен список")
    if len(cells) != cols * rows:
        raise ValueError(f"cells: длина {len(cells)} ≠ cols×rows = "
                         f"{cols * rows}")
    for v in cells:
        if not isinstance(v, int) or not -1 <= v < len(colors):
            raise ValueError("cells: значения — номер цвета или -1 (пусто)")

    # −1 → №0: пустые клетки печатаются цветом фона
    grid = [[max(cells[r * cols + c], 0) for c in range(cols)]
            for r in range(rows)]
    counts = Counter(v for row in grid for v in row)
    pal = {"name": str(data.get("name") or "схема picher"),
           "colors": [{"id": i, "name": str(c.get("name", ""))[:60],
                       "hex": str(c["hex"])}
                      for i, c in enumerate(colors)]}
    return {"name": pal["name"], "cols": cols, "rows": rows,
            "grid": grid, "pal": pal, "counts": counts}


def block_svg(grid, c0, c1, r0, r1, pal, pitch, circle_d, show_numbers=True,
              only_color=None):
    """SVG-блок: колонки c0..c1 (не вкл.), ряды r0..r1 (не вкл.).

    Нумерация колонок и рядов — глобальная (для склейки блоков),
    мм-размеры точные. Аналог glitch.segment_svg + сдвиг номеров рядов.
    only_color — режим одноцветной схемы (см. glitch.segment_svg).
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
            if only_color is not None:
                if num == only_color:
                    out.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" '
                               f'r="{rad:.2f}" fill="{color["hex"]}"/>')
                    out.append(glitch.center_mark_svg(cx, cy, circle_d,
                                                      color["hex"]))
                else:
                    out.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" '
                               f'r="{rad:.2f}" fill="none" '
                               f'stroke="#999999" stroke-width="0.12"/>')
                continue
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


def render_document(scheme, title, pitch_mm, circle_d_mm, numbers=True,
                    only_color=None):
    """Сборка HTML: блоки ≤ листа по ширине и высоте, склейка по номерам.

    only_color — одноцветная схема этого цвета.
    """
    cols, rows_n = scheme["cols"], scheme["rows"]
    grid, pal, counts = scheme["grid"], scheme["pal"], scheme["counts"]
    name = scheme["name"]
    pitch, circle_d = pitch_mm, circle_d_mm
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
    # порядок чтения схемы: полоса рядов за полосой, внутри — слева направо
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
        ("Схема", f"«{name}» · редактор picher · {cols}×{rows_n} клеток"),
        ("Изделие", f"{cols} колонок × {rows_n} рядов = "
                    f"{cols * pitch:.1f} × {rows_n * pitch:.1f} мм"),
        ("Кружки", f"шаг {pitch:g} мм · диаметр {circle_d:.1f} мм"),
        ("Всего бисерин", f"{total:,}".replace(",", " ")),
        ("Палитра", f"{len(used)} цветов · пустые клетки = фон №0"),
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
    if only_color is None:
        h1_txt = f"{glitch.esc(title)} — схема"
        sub_txt = (f"схема из редактора picher · страниц: {n_pages} · "
                   f"блоков: {len(blocks)}")
    else:
        col = pal["colors"][only_color]
        h1_txt = (f"{glitch.esc(title)} — одноцветная схема · "
                  f"цвет №{only_color} {glitch.esc(col['name'])}")
        sub_txt = (f"закрашен только цвет №{only_color} ({col['hex']}) · "
                   f"крестик — центр бисерины · страниц: {n_pages} · "
                   f"блоков: {len(blocks)}")
    header_card = f"""
<div class="card">
<h1>{h1_txt}</h1>
<div class="sub">{sub_txt}</div>
<table class="params">{params}</table>
{glitch.ruler_svg(100.0)}
</div>
<div class="card">
<h2>Обозначения — палитра схемы «{glitch.esc(name)}»</h2>
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
                        numbers, only_color)
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
                        f'{glitch.esc(title)} — стр. {pi} · блоки '
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
<title>{h1_txt}</title>
<style>{glitch.CSS}</style>
</head>
<body>
{"".join(body)}
</body>
</html>
"""
    meta = dict(pages=n_pages, blocks=len(blocks), used=len(used),
                col_chunks=len(col_chunks), row_bands=len(row_bands),
                seg_cols=seg_cols, seg_rows=seg_rows,
                split=rows_n > seg_rows)
    return doc, meta


def write_outputs(data, *, name, title=None, pitch_mm=4.5, circle_d_mm=3.0,
                  numbers=True, out_dir=None, file_stem=None):
    """Схема (dict редактора) → основной HTML + одноцветные в out_dir.

    name — имя схемы (для титульной страницы), file_stem — база имён
    файлов (по умолчанию name). Возвращает {main, folder, singles, meta}.
    Плохие параметры/данные — ValueError с понятным текстом.
    """
    if pitch_mm <= 0.2:
        raise ValueError(f"Шаг сетки {pitch_mm:g} мм слишком мал "
                         f"(минимум 0.2 мм).")
    if not 0.8 <= circle_d_mm < pitch_mm:
        raise ValueError(f"Диаметр кружка {circle_d_mm:g} мм должен быть "
                         f"от 0.8 мм и меньше шага {pitch_mm:g} мм.")
    scheme = build_scheme(data)
    scheme["name"] = name
    title = (title or "").strip() or name
    file_stem = file_stem or name

    doc, meta = render_document(scheme, title, pitch_mm, circle_d_mm, numbers)
    cols, rows_n = scheme["cols"], scheme["rows"]
    assert doc.count("<circle ") == rows_n * cols
    assert doc.count("</html>") == 1

    out_dir = Path(out_dir) if out_dir else SCRIPT_DIR / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{file_stem}.html").write_text(doc, encoding="utf-8")

    # одноцветные схемы: папка рядом с основной, файл на каждый цвет
    used = [c for c in scheme["pal"]["colors"]
            if scheme["counts"].get(c["id"], 0)]
    folder = f"{file_stem}_cols{cols}_colors{len(used)}"
    colors_dir = out_dir / folder
    colors_dir.mkdir(parents=True, exist_ok=True)
    singles = []
    for c in used:
        doc_c, _ = render_document(scheme, title, pitch_mm, circle_d_mm,
                                   numbers, only_color=c["id"])
        assert doc_c.count("<circle ") == rows_n * cols
        assert doc_c.count("</html>") == 1
        single = f"{folder}/{file_stem}_{c['id']}.html"
        (out_dir / single).write_text(doc_c, encoding="utf-8")
        singles.append(single)
    return {"main": f"{file_stem}.html", "folder": folder,
            "singles": singles, "meta": meta}


def print_help_card() -> None:
    """Короткая шпаргалка: запуск, как работает, частые флаги, файлы."""
    L = ["Печатная A4-схема из JSON-схемы редактора picher (HTML · точные мм)",
         "",
         "ЗАПУСК — примеры (из любой папки проекта):",
         "  python3 picher/render.py picher/schemes/моя_схема.json",
         "  python3 picher/render.py схема.json --pitch-mm 5 --circle-d-mm 3.5",
         "  python3 picher/render.py схема.json --no-numbers --out shema.html",
         "",
         "КАК ЭТО РАБОТАЕТ:",
         "  JSON схемы picher → SVG-блоки с кружками-бисеринами → HTML под A4",
         "  (титульная страница, легенда с подсчётом бисерин, калибровка,",
         "   линии отреза); пустые клетки (−1) печатаются цветом №0 (фон);",
         "  большое полотно режется на блоки под лист A4, склейка — по",
         "  глобальным номерам рядов и колонок.",
         "",
         "ЧАСТО ИСПОЛЬЗУЕТСЯ:",
         "  --pitch-mm ШАГ    шаг сетки — между центрами кружков, мм (4.5)",
         "  --circle-d-mm D   диаметр кружочка, мм (3.0)",
         "  --title ТЕКСТ     заголовок схемы (по умолчанию имя схемы)",
         "  --no-numbers      кружки без цифр-номеров коробочек",
         "  --out ФАЙЛ        выходной HTML (по умолчанию picher/out/<имя>.html)",
         "",
         "ФАЙЛЫ:",
         "  печатная схема — picher/out/<имя>.html; рядом папка",
         "  <имя>_colsN_colorsM/: одноцветные схемы, файл <имя>_<№>.html на",
         "  каждый цвет (№ = номер коробочки; закрашен только этот цвет,",
         "  крестик — центр бисерины, остальные кружки — прозрачные контуры);",
         "  этим же модулем пользуется веб-интерфейс (кнопка",
         "  «Распечатать A4» в редакторе); общие части рендера —",
         "  ../patterns/glitch.py (импорт).",
         "",
         "Полный список параметров: python3 picher/render.py --help"]
    print("\n".join(L))


def parse_args(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    if not args or args[0] == "help":
        print_help_card()
        raise SystemExit(0)
    p = argparse.ArgumentParser(
        prog="render.py",
        description="Печатная A4-схема из JSON-схемы редактора picher "
                    "(кружки-бисерины, легенда, одноцветные файлы; большое "
                    "полотно режется на блоки под лист).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("scheme", type=Path,
                   help="файл JSON-схемы picher (например "
                        "picher/schemes/моя_схема.json)")
    p.add_argument("--pitch-mm", type=float, default=4.5,
                   help="шаг сетки — расстояние между центрами кружочков, мм")
    p.add_argument("--circle-d-mm", type=float, default=3.0,
                   help="диаметр кружочка, мм")
    p.add_argument("--no-numbers", dest="numbers", action="store_false",
                   help="печатать кружки без цифр-номеров коробочек")
    p.add_argument("--title", default="", help="заголовок схемы")
    p.add_argument("--out", type=Path, default=None,
                   help="выходной HTML (по умолчанию picher/out/<имя>.html)")
    p.set_defaults(numbers=True)
    return p.parse_args(args)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        data = json.loads(args.scheme.read_text(encoding="utf-8"))
    except OSError as e:
        sys.exit(f"Не читается {args.scheme}: {e}.")
    except ValueError as e:
        sys.exit(f"Файл битой JSON-схемы {args.scheme}: {e}.")

    name = args.scheme.stem
    try:
        if args.out is not None:
            files = write_outputs(data, name=name, title=args.title,
                                  pitch_mm=args.pitch_mm,
                                  circle_d_mm=args.circle_d_mm,
                                  numbers=args.numbers,
                                  out_dir=args.out.parent,
                                  file_stem=args.out.stem)
        else:
            files = write_outputs(data, name=name, title=args.title,
                                  pitch_mm=args.pitch_mm,
                                  circle_d_mm=args.circle_d_mm,
                                  numbers=args.numbers)
    except ValueError as e:
        sys.exit(str(e))

    meta = files["meta"]
    print(f"Схема: {args.scheme} · заголовок: {args.title or name}")
    print(f"Кружки: шаг {args.pitch_mm:g} мм · ⌀{args.circle_d_mm:g} мм · "
          + ("без цифр" if not args.numbers else "с номерами коробочек"))
    if meta["split"]:
        print(f"  ⚠ полотно выше листа: разбито на {meta['row_bands']} полосы "
              f"рядов по ≤{meta['seg_rows']} — склеивайте блоки по номерам "
              "рядов и колонок")
    print(f"Блоков: {meta['blocks']} ({meta['col_chunks']} полос колонок × "
          f"{meta['row_bands']} полос рядов)")
    print(f"Цветов с бисером: {meta['used']}")
    print(f"Страниц: {meta['pages']}")
    out_root = args.out.parent if args.out is not None else SCRIPT_DIR / "out"
    print(f"Одноцветные схемы: {out_root / files['folder']} · "
          f"файлов: {len(files['singles'])}")
    print(f"Готово: {out_root / files['main']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
