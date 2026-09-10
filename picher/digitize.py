#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""digitize.py — оцифровка картинки в схему для редактора picher.

Что делает: постеризует картинку в N цветов и пишет сетку клеток-бисерин
в формате редактора picher — JSON в picher/schemes/. Дальше схему правят
в редакторе (веб-интерфейс, вкладка «Рисовать схему», или сразу
http://127.0.0.1:8000/picher?name=<имя>) и печатают оттуда кнопкой
«Распечатать A4» (picher/render.py). Печатные HTML-схемы из картинки
рождаются только через редактор.

Запуск (из любой папки):
    python3 picher/digitize.py картинка.png -n 8
Выход: picher/schemes/<имя_картинки>.json
Шпаргалка с примерами: python3 picher/digitize.py help
(она же показывается при запуске без аргументов).

Зависимости: Pillow. Один раз запусти setup.sh (Linux/macOS) или setup.cmd
(Windows) из корня проекта — скрипт создаст .venv и поставит requirements.txt.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMES = SCRIPT_DIR / "schemes"

# совместимость констант Pillow старых/новых версий (9.x модульные, 10+ enum)
RESAMPLE_BOX = getattr(getattr(Image, "Resampling", Image), "BOX")
DITHER_NONE = getattr(getattr(Image, "Dither", Image), "NONE", 0)
DITHER_FS = getattr(getattr(Image, "Dither", Image), "FLOYDSTEINBERG", 3)


def _getdata(im):
    """Пиксели картинки: get_flattened_data (Pillow 12+) или getdata."""
    return im.get_flattened_data() if hasattr(im, "get_flattened_data") \
        else im.getdata()

MIN_COLORS, MAX_COLORS = 2, 30
MAX_COLS, MAX_ROWS = 2000, 500      # лимиты сетки редактора picher
BAD_NAME = re.compile(r"[^0-9A-Za-zА-Яа-яЁё._-]")


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
    idx_counts = Counter(_getdata(q))

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

    data = list(_getdata(q))
    grid = [[new_id[data[r * cols + c]] for c in range(cols)]
            for r in range(rows)]
    return grid, colors, (w, h), rows


def print_help_card() -> None:
    """Короткая шпаргалка: запуск, как работает, частые флаги, файлы."""
    L = ["Оцифровка картинки в схему редактора picher (JSON)",
         "",
         "ЗАПУСК — примеры (из любой папки проекта):",
         "  python3 picher/digitize.py картинка.png -n 8",
         "  python3 picher/digitize.py koi.png --cols 100 --dither",
         "  python3 picher/digitize.py koi.png -n 12 --name моя_схема",
         "",
         "КАК ЭТО РАБОТАЕТ:",
         "  картинка → постеризация в N цветов → клетки-бисерины →",
         "  JSON-схема picher/schemes/<имя>.json;",
         "  ряды сетки считаются из пропорций картинки при длине --cols;",
         "  дальше — правка в редакторе и печать кнопкой «Распечатать A4»",
         "  (picher/render.py, A4, кружки, легенда, одноцветные файлы).",
         "",
         "ЧАСТО ИСПОЛЬЗУЕТСЯ:",
         "  -n N           сколько цветов оставить (2-30, по умолчанию 7)",
         "  --cols N       длина изделия в клетках (по умолчанию 200)",
         "  --dither       дизеринг Флойда—Стейнберга (по умолчанию выкл.)",
         "  --mirror       зеркальная схема",
         "  --name ИМЯ     имя схемы в picher (по умолчанию имя картинки)",
         "",
         "ФАЙЛЫ:",
         "  схема ложится в picher/schemes/<имя>.json (формат редактора:",
         "  {version, cols, rows, colors, cells}); схема с тем же именем",
         "  перезаписывается.",
         "",
         "Полный список параметров: python3 picher/digitize.py --help"]
    print("\n".join(L))


def parse_args(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    if not args or args[0] == "help":
        print_help_card()
        raise SystemExit(0)
    p = argparse.ArgumentParser(
        prog="digitize.py",
        description="Оцифровка картинки в схему редактора picher "
                    "(постеризация в N цветов → JSON в picher/schemes/).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("image", type=Path, help="файл картинки (PNG/JPEG/…)")
    p.add_argument("-n", "--colors", type=int, default=7,
                   help=f"сколько цветов оставить ({MIN_COLORS}–{MAX_COLORS})")
    p.add_argument("--cols", type=int, default=200,
                   help="длина изделия в клетках-колонках")
    p.add_argument("--dither", action="store_true",
                   help="дизеринг Флойда—Стейнберга (по умолчанию чистые пятна)")
    p.add_argument("--mirror", action="store_true",
                   help="зеркальная схема (для техник с обратным чтением)")
    p.add_argument("--name", default="",
                   help="имя схемы в picher (по умолчанию имя картинки)")
    return p.parse_args(args)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not MIN_COLORS <= args.colors <= MAX_COLORS:
        sys.exit(f"--colors должен быть от {MIN_COLORS} до {MAX_COLORS}, "
                 f"получено {args.colors}.")
    if args.cols < 1:
        sys.exit("--cols должен быть целым числом ≥ 1.")
    if args.cols > MAX_COLS:
        sys.exit(f"--cols до {MAX_COLS} (лимит сетки редактора picher), "
                 f"получено {args.cols}.")

    grid, colors, img_size, rows = load_cells(
        args.image, args.cols, args.colors, args.dither)
    if args.mirror:
        grid = [row[::-1] for row in grid]
    cols = args.cols
    if rows > MAX_ROWS:
        sys.exit(f"Из пропорций картинки выходит {rows} рядов — редактор "
                 f"держит до {MAX_ROWS}. Уменьшите --cols "
                 f"(примерно до {max(1, cols * MAX_ROWS // rows)}).")

    name = BAD_NAME.sub("_", (args.name or args.image.stem).strip())
    cells = [v for row in grid for v in row]
    assert len(cells) == rows * cols
    assert set(cells) <= {c["id"] for c in colors}

    data = {"version": 1, "name": name, "cols": cols, "rows": rows,
            "colors": [{"name": c["name"], "hex": c["hex"]} for c in colors],
            "cells": cells}
    SCHEMES.mkdir(parents=True, exist_ok=True)
    out = SCHEMES / f"{name}.json"
    out.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")
    # контроль: файл читается обратно и совпадает клетка в клетку
    assert json.loads(out.read_text(encoding="utf-8")) == data

    counts = Counter(cells)
    print(f"Картинка: {args.image} · {img_size[0]}×{img_size[1]} px · "
          f"рядов из пропорций: {rows}")
    print(f"Постеризация: {len(counts)} цветов · "
          + ("дизеринг" if args.dither else "без дизеринга")
          + (" · зеркально" if args.mirror else ""))
    print(f"Сетка: {cols} × {rows} клеток")
    print("Бисерины по коробочкам:")
    for c in colors:
        if counts.get(c["id"]):
            print(f"  №{c['id']} {c['hex']} {c['name']}: {counts[c['id']]}")
    print(f"СХЕМА: {name}")
    print(f"Готово: {out}")
    print("Дальше: правьте в редакторе и печатайте кнопкой «Распечатать A4» "
          "(веб-интерфейс → «Рисовать схему»).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
