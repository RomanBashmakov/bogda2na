#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""beads.py — рендер «картины из бисера» на Pillow.

Два выхода:
  * render_pixels()  — пиксельная версия (цветные квадраты-клетки),
    без рамы и водяного знака; кладётся в архив заказа;
  * render_picture() — финальный рендер: бисерины с бликами в паспарту
    и деревянной раме + диагональный водяной знак (клиенту — только так).

Используется service/app.py; сам по себе не запускается.
"""

import random
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

MAT_COLOR = (244, 239, 230)      # паспарту — тёплый кремовый
MAT_BEVEL = (211, 203, 188)      # внутренняя тень паспарту
WOOD_DARK = (74, 55, 38)         # рама — тёмный орех
WOOD_LIGHT = (139, 106, 73)
GOLD = (198, 165, 92)            # золотая линия у паспарту


def _rgb(hex_color: str):
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def _mul(rgb, k):
    return tuple(min(255, max(0, int(v * k))) for v in rgb)


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _check(colors, cells, cols, rows):
    if not isinstance(colors, list) or not 1 <= len(colors) <= 30:
        raise ValueError("Палитра — список из 1–30 цветов.")
    rgb = []
    for c in colors:
        if not isinstance(c, str) or not HEX_RE.match(c):
            raise ValueError(f"Цвет «{c}» не похож на #rrggbb.")
        rgb.append(_rgb(c))
    if not isinstance(cells, list) or len(cells) != cols * rows:
        raise ValueError(f"Сетка должна быть из {cols * rows} клеток.")
    for v in cells:
        if not isinstance(v, int) or not 0 <= v < len(rgb):
            raise ValueError("В клетках — номера цветов палитры.")
    return rgb


def _font(size: int):
    """Жирный шрифт для водяного знака; деградация до builtin."""
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
              "/Library/Fonts/Arial Bold.ttf",
              "C:\\Windows\\Fonts\\arialbd.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    try:                       # Pillow ≥ 9.2 умеет размер у builtin
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def render_pixels(colors, cells, cols, rows, cell=16):
    """Пиксельная версия заказа: квадраты-клетки, тонкая сетка."""
    rgb = _check(colors, cells, cols, rows)
    img = Image.new("RGB", (cols * cell, rows * cell), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for r in range(rows):
        for c in range(cols):
            d.rectangle((c * cell, r * cell,
                         (c + 1) * cell - 1, (r + 1) * cell - 1),
                        fill=rgb[cells[r * cols + c]])
    for i in range(cols + 1):              # вертикальные линии сетки
        d.line((i * cell - 0.5, 0, i * cell - 0.5, rows * cell - 1),
               fill=(0, 0, 0), width=1)
    for i in range(rows + 1):
        d.line((0, i * cell - 0.5, cols * cell - 1, i * cell - 0.5),
               fill=(0, 0, 0), width=1)
    return img


# совместимость констант Pillow старых/новых версий (как в digitize.py)
RESAMPLE_BICUBIC = getattr(getattr(Image, "Resampling", Image), "BICUBIC")


def _bead_field(rgb, cells, cols, rows, s):
    """Поле бисерин: кружки с ободком, бликом и разбросом тона."""
    art = Image.new("RGB", (cols * s, rows * s), MAT_COLOR)
    d = ImageDraw.Draw(art)
    rnd = random.Random(20260921)
    for r in range(rows):
        for c in range(cols):
            base = _mul(rgb[cells[r * cols + c]],
                        rnd.uniform(0.93, 1.07))     # живой разброс тона
            x0, y0 = c * s, r * s
            d.ellipse((x0, y0, x0 + s - 1, y0 + s - 1),
                      fill=_mul(base, 0.74))          # тёмный ободок
            k = max(2, s // 7)                        # фаска бисерины
            d.ellipse((x0 + k, y0 + k, x0 + s - 1 - k, y0 + s - 1 - k),
                      fill=base)
            hw = max(2, s // 4)                       # блик слева сверху
            hh = max(1, s // 6)
            d.ellipse((x0 + k + 1, y0 + k + 1,
                       x0 + k + hw, y0 + k + hh),
                      fill=_mix(base, (255, 255, 255), 0.55))
    return art


def _frame(total_w, total_h, fw, mw):
    """Рама и паспарту под поле бисерин: холст, готовый к paste."""
    img = Image.new("RGB", (total_w, total_h), WOOD_DARK)
    d = ImageDraw.Draw(img)
    for i in range(fw):                               # градиент дерева
        t = i / max(1, fw - 1)
        col = _mix(WOOD_DARK, WOOD_LIGHT, 1 - abs(2 * t - 1))
        d.rectangle((i, i, total_w - 1 - i, total_h - 1 - i),
                    outline=col, width=1)
    d.rectangle((fw - 3, fw - 3, total_w - fw + 2, total_h - fw + 2),
                outline=GOLD, width=2)                # золотая линия
    d.rectangle((fw, fw, total_w - 1 - fw, total_h - 1 - fw),
                fill=MAT_COLOR)                       # паспарту
    d.rectangle((fw + 2, fw + 2,
                 total_w - 3 - fw, total_h - 3 - fw),
                outline=MAT_BEVEL, width=1)           # тень выреза
    return img


def _watermark(img, text, opacity):
    """Диагональная плитка из текста поверх всей картинки."""
    if not text or opacity <= 0:
        return img
    opacity = min(0.9, max(0.05, opacity))
    alpha = int(255 * opacity)
    fs = max(22, min(90, img.width // 12))
    font = _font(fs)
    tmp = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    box = tmp.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0] + fs, box[3] - box[1] + fs
    tile = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    td = ImageDraw.Draw(tile)
    td.text((fs // 2 - box[0], fs // 2 - box[1]), text, font=font,
            fill=(0, 0, 0, alpha // 2))               # тень
    td.text((fs // 2 - box[0] + 1, fs // 2 - box[1] + 1), text, font=font,
            fill=(255, 255, 255, alpha))
    tile = tile.rotate(-30, expand=True, resample=RESAMPLE_BICUBIC)
    tw, th = tile.size
    out = img.convert("RGBA")
    row = 0
    for y in range(-th, img.height + th, th * 2 // 3):
        off = (tw // 2) if row % 2 else 0             # «кирпичная» раскладка
        for x in range(-tw - off, img.width + tw, tw * 5 // 4):
            out.alpha_composite(tile, (x + off, y))
        row += 1
    return out.convert("RGB")


def render_picture(colors, cells, cols, rows, watermark=None):
    """Финальный рендер: бисер в паспарту и раме (+ водяной знак)."""
    rgb = _check(colors, cells, cols, rows)
    s = max(7, min(18, 1600 // max(cols, rows)))      # px на бисерину
    fw = max(30, s * 4)                               # ширина рамы
    mw = max(26, s * 3)                               # паспарту
    w, h = cols * s, rows * s
    img = _frame(w + 2 * (fw + mw), h + 2 * (fw + mw), fw, mw)
    img.paste(_bead_field(rgb, cells, cols, rows, s), (fw + mw, fw + mw))
    if watermark:
        img = _watermark(img, str(watermark.get("text") or ""),
                         float(watermark.get("opacity") or 0))
    return img
