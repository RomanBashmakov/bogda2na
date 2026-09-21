#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""service/app.py — онлайн-конструктор «картина из бисера по вашей картинке».

Запуск из корня проекта:
    python3 service/app.py                 # http://127.0.0.1:8100
    python3 service/app.py --no-browser
    python3 service/app.py --host 0.0.0.0 --port 8080   # для выкладки

Поток клиента: загрузка картинки → формат (A6/A5/A4) и уровень цвета
(Простая 3 / Детальная 7 / Максимум 10) → сервер постеризует картинку
(picher/digitize.py, Pillow) → клиент правит пиксели в мини-редакторе →
«Готово» → сервер считает цену (таблица в config.json) и рисует рендер
«бисер в раме» с водяным знаком (service/beads.py) → «Заказать» →
заказ копится в service/orders/NNN/ (уведомления — позже, отдельно).

Что принципиально НЕ отдаётся в браузер: производственная схема
(кружки с номерами коробочек — внутренний инструмент мастера,
см. service/scheme_from_order.py), формула/таблица цен (клиент получает
только число) и рендер без водяного знака.

Зависимости: flask, Pillow (requirements.txt корня проекта).
"""

import argparse
import importlib.util
import json
import os
import re
import secrets
import sys
import threading
import time
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template, request, \
    send_from_directory

SRV = Path(__file__).resolve().parent
ROOT = SRV.parent
UPLOADS = SRV / "uploads"
RENDERS = SRV / "renders"
ORDERS = SRV / "orders"
DIGITIZE_PY = ROOT / "picher" / "digitize.py"

UPLOAD_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
BAD_NAME = re.compile(r"[\r\n\t]")
ORDER_RE = re.compile(r"^\d{4}$")
ORDER_LOCK = threading.Lock()


class BadInput(Exception):
    """Плохие данные запроса — текст уходит в ответ 400."""


def load_config() -> dict:
    try:
        cfg = json.loads((SRV / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"Не читается service/config.json: {e}.")
    for fmt, f in cfg["formats"].items():
        if not (1 <= f["cols"] <= 2000 and 1 <= f["rows"] <= 2000):
            sys.exit(f"Формат {fmt}: сетка вне пределов редактора.")
        if f["cols"] * f["rows"] > 40000:
            sys.exit(f"Формат {fmt}: {f['cols'] * f['rows']} клеток — "
                     f"больше лимита 40000.")
    for lvl in cfg["levels"]:
        if not 2 <= lvl["colors"] <= 30:
            sys.exit(f"Уровень {lvl['id']}: цветов должно быть 2–30.")
        if lvl["id"] not in cfg["prices"][list(cfg["prices"])[0]]:
            sys.exit(f"Уровню {lvl['id']} нет цены в prices.")
    return cfg


CFG = load_config()
FORMATS = {k: (v["cols"], v["rows"], v["label"])
           for k, v in CFG["formats"].items()}
LEVELS = {l["id"]: l for l in CFG["levels"]}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = \
    int(CFG["upload_max_mb"]) * 1024 * 1024


def _digitize_mod():
    """Модуль picher/digitize.py (постеризация картинки)."""
    try:
        spec = importlib.util.spec_from_file_location(
            "picher_digitize", DIGITIZE_PY)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except ImportError as e:
        raise BadInput(f"Pillow не установлена ({e}) — см. setup.sh.")


def _beads_mod():
    """Модуль service/beads.py (рендер бисера и водяной знак)."""
    sys.path.insert(0, str(SRV))
    try:
        import beads
        return beads
    except ImportError as e:
        raise BadInput(f"Не импортируется service/beads.py: {e}.")


def grid_dims(fmt: str, orient: str):
    """(cols, rows) формата с учётом ориентации."""
    c, r, _ = FORMATS[fmt]
    return (c, r) if orient == "portrait" else (r, c)


def crop_box(w: int, h: int, crop, cols: int, rows: int):
    """Кроп подгоняется к пропорции cols:rows (центр сохраняется)."""
    if not crop:
        x, y, cw, ch = 0, 0, w, h
    else:
        try:
            x = max(0, min(int(crop["x"]), w - 1))
            y = max(0, min(int(crop["y"]), h - 1))
            cw = max(1, min(int(crop["w"]), w - x))
            ch = max(1, min(int(crop["h"]), h - y))
        except (KeyError, TypeError, ValueError):
            raise BadInput("Кроп должен быть {x, y, w, h} в пикселях.")
    target = cols / rows
    if cw / ch > target:                      # шире, чем надо — сужаем
        cw2 = max(1, round(ch * target))
        x = max(0, min(x + (cw - cw2) // 2, w - cw2))
        cw = cw2
    else:                                     # выше, чем надо — низим
        ch2 = max(1, round(cw / target))
        y = max(0, min(y + (ch - ch2) // 2, h - ch2))
        ch = ch2
    return x, y, cw, ch


def _fmt_orient_level(p):
    fmt = str(p.get("format") or "")
    orient = str(p.get("orient") or "portrait")
    level = str(p.get("level") or "")
    if fmt not in FORMATS:
        raise BadInput("Неизвестный формат.")
    if orient not in ("portrait", "landscape"):
        raise BadInput("Ориентация — portrait или landscape.")
    if level not in LEVELS:
        raise BadInput("Неизвестный уровень цвета.")
    return fmt, orient, level


def _grid(p):
    """Валидация сетки из запроса → (fmt, orient, level, colors, cells,
    cols, rows)."""
    fmt, orient, level = _fmt_orient_level(p)
    cols, rows = grid_dims(fmt, orient)
    colors = p.get("colors")
    cells = p.get("cells")
    if not isinstance(colors, list) or not 1 <= len(colors) <= 30:
        raise BadInput("Палитра — список из 1–30 цветов.")
    colors = [str(c) for c in colors]
    for c in colors:
        if not HEX_RE.match(c):
            raise BadInput(f"Цвет «{c}» не похож на #rrggbb.")
    if not isinstance(cells, list) or len(cells) != cols * rows:
        raise BadInput(f"Сетка должна быть из {cols * rows} клеток.")
    for v in cells:
        if not isinstance(v, int) or not 0 <= v < len(colors):
            raise BadInput("В клетках — номера цветов палитры.")
    return fmt, orient, level, colors, cells, cols, rows


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/config")
def api_config():
    """Форматы и уровни для интерфейса. Цены — только в /api/render."""
    return jsonify(
        formats={k: {"cols": v[0], "rows": v[1], "label": v[2]}
                 for k, v in FORMATS.items()},
        levels=CFG["levels"],
        upload_max_mb=int(CFG["upload_max_mb"]))


@app.post("/api/digitize")
def api_digitize():
    """Картинка + кроп + формат + уровень → пиксельная сетка (JSON)."""
    image = request.files.get("image")
    if image is None or not image.filename:
        return jsonify(ok=False, error="Приложите картинку."), 400
    ext = Path(image.filename).suffix.lower()
    if ext not in UPLOAD_EXT:
        return jsonify(ok=False,
                       error=f"Файл .{ext or '?'} не поддерживается "
                             "(нужно png/jpg/jpeg/gif/bmp/webp)."), 400
    try:
        fmt, orient, level = _fmt_orient_level(request.form)
    except BadInput as e:
        return _err(e)
    cols, rows = grid_dims(fmt, orient)
    try:
        crop = json.loads(request.form.get("crop") or "null")
    except ValueError:
        return jsonify(ok=False, error="Кроп — не JSON."), 400

    UPLOADS.mkdir(parents=True, exist_ok=True)
    uid = secrets.token_hex(8)
    src = UPLOADS / f"{uid}{ext}"
    try:
        image.save(src)
    except OSError as e:
        return jsonify(ok=False, error=f"Не удалось сохранить: {e}."), 500
    try:
        from PIL import Image
        with Image.open(src) as im:
            w, h = im.size
    except Exception:
        src.unlink(missing_ok=True)
        return jsonify(ok=False, error="Картинка не читается."), 400
    if w < cols or h < rows:
        src.unlink(missing_ok=True)
        return jsonify(ok=False, error=f"Картинка {w}×{h} px слишком мала "
                                       f"для {cols}×{rows} бисерин."), 400

    x, y, cw, ch = crop_box(w, h, crop, cols, rows)
    tmp = UPLOADS / f".{uid}.crop.png"
    try:
        with Image.open(src) as im:
            im.convert("RGB").crop((x, y, x + cw, y + ch)).save(tmp)
        grid, colors, _size, rows_out = _digitize_mod().load_cells(
            tmp, cols, LEVELS[level]["colors"], bool(CFG["dither"]))
    except BadInput as e:
        src.unlink(missing_ok=True)
        return _err(e)
    except Exception as e:
        src.unlink(missing_ok=True)
        return jsonify(ok=False, error=f"Оцифровка не удалась: {e}."), 500
    finally:
        tmp.unlink(missing_ok=True)
    if rows_out != rows:                      # страховка от округлений
        src.unlink(missing_ok=True)
        return jsonify(ok=False, error=f"Из пропорций вышло {rows_out} "
                                       f"рядов вместо {rows}."), 500
    return jsonify(ok=True, upload_id=uid, cols=cols, rows=rows,
                   colors=[c["hex"] for c in colors],
                   cells=[v for row in grid for v in row])


def _err(e):
    return jsonify(ok=False, error=str(e)), 400


@app.post("/api/render")
def api_render():
    """Сетка → водяной рендер PNG + цена (числом, без таблицы)."""
    p = request.get_json(force=True, silent=True) or {}
    try:
        fmt, orient, level, colors, cells, cols, rows = _grid(p)
        beads = _beads_mod()
        rid = secrets.token_hex(8)
        RENDERS.mkdir(parents=True, exist_ok=True)
        img = beads.render_picture(colors, cells, cols, rows,
                                   watermark=CFG["watermark"])
        img.save(RENDERS / f"{rid}.png")
    except BadInput as e:
        return _err(e)
    except Exception as e:
        return jsonify(ok=False, error=f"Рендер не удался: {e}."), 500
    return jsonify(ok=True, price=CFG["prices"][fmt][level],
                   render_id=rid, url=f"/renders/{rid}.png",
                   beads=len(cells), format=fmt, orient=orient,
                   level=level, level_label=LEVELS[level]["label"])


@app.get("/renders/<name>")
def renders_static(name):
    return send_from_directory(RENDERS, name)


def _upload_path(uid):
    if not re.fullmatch(r"[0-9a-f]{4,32}", str(uid or "")):
        raise BadInput("Неверный upload_id.")
    if UPLOADS.is_dir():
        for f in UPLOADS.iterdir():
            if f.is_file() and f.stem == uid:
                return f
    raise BadInput("Загруженная картинка не найдена (устарела?).")


@app.post("/api/order")
def api_order():
    """Готовый заказ → service/orders/NNN/ (order.json + исходник +
    пиксельная версия + водяной рендер). Уведомления — позже."""
    p = request.get_json(force=True, silent=True) or {}
    try:
        fmt, orient, level, colors, cells, cols, rows = _grid(p)
        name = BAD_NAME.sub(" ", str(p.get("name") or "")).strip()
        contact = BAD_NAME.sub(" ", str(p.get("contact") or "")).strip()
        comment = BAD_NAME.sub(" ", str(p.get("comment") or "")).strip()
        if not 1 <= len(name) <= 100:
            raise BadInput("Имя — 1–100 символов.")
        if not 1 <= len(contact) <= 200:
            raise BadInput("Контакт — 1–200 символов.")
        if len(comment) > 1000:
            raise BadInput("Комментарий — до 1000 символов.")
        src = _upload_path(p.get("upload_id"))
        rid = str(p.get("render_id") or "")
        if not re.fullmatch(r"[0-9a-f]{4,32}", rid) \
                or not (RENDERS / f"{rid}.png").is_file():
            raise BadInput("Рендер не найден — вернитесь и нажмите «Готово».")
        beads = _beads_mod()
        order = {"num": None,
                 "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                 "format": fmt, "orient": orient, "level": level,
                 "level_label": LEVELS[level]["label"],
                 "price": CFG["prices"][fmt][level],
                 "name": name, "contact": contact, "comment": comment,
                 "cols": cols, "rows": rows, "colors": colors,
                 "cells": cells}
        ORDERS.mkdir(parents=True, exist_ok=True)
        with ORDER_LOCK:
            nums = [int(d.name) for d in ORDERS.iterdir()
                    if d.is_dir() and ORDER_RE.match(d.name)]
            order["num"] = f"{((max(nums) + 1) if nums else 1):04d}"
            odir = ORDERS / order["num"]
            odir.mkdir(parents=True)
            (odir / "order.json").write_text(
                json.dumps(order, ensure_ascii=False, indent=1),
                encoding="utf-8")
            beads.render_pixels(colors, cells, cols, rows).save(
                odir / "pixels.png")
            beads.render_picture(colors, cells, cols, rows,
                                 watermark=CFG["watermark"]).save(
                odir / "render.png")
            (odir / f"source{src.suffix}").write_bytes(src.read_bytes())
    except BadInput as e:
        return _err(e)
    except Exception as e:
        return jsonify(ok=False, error=f"Заказ не сохранён: {e}."), 500
    return jsonify(ok=True, order=order["num"], price=order["price"])


def main():
    ap = argparse.ArgumentParser(
        description="Конструктор картин из бисера (2N)")
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("PORT", 8100)))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true",
                    help="не открывать браузер автоматически")
    args = ap.parse_args()
    url = f"http://{args.host}:{args.port}"
    print(f"Конструктор картин: {url}  (Ctrl+C — остановить)")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
