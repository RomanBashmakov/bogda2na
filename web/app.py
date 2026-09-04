#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""web/app.py — локальный веб-интерфейс для генераторов схем (Flask).

Запуск из корня проекта:
    python3 web/app.py                 # http://127.0.0.1:8000
    python3 web/app.py --no-browser    # не открывать браузер самому
    python3 web/app.py --port 8080

Что делает:
  * формы запуска трёх генераторов — patterns/glitch.py,
    belt_rus_generator/belt_rus.py (параметров нет), img_generator/img_belt.py;
  * загрузка картинок для img_belt.py в web/uploads/ + повторный выбор;
  * список готовых схем из out/ каждого генератора: просмотр в новой
    вкладке (/view/<gen>/<файл>) и удаление (основной файл + папки
    одноцветных схем <имя>_colsN_colorsM/);
  * stdout/stderr скрипта и ссылки на созданные файлы.

Генераторы запускаются subprocess'ом интерпретатором .venv, если он есть
(как в setup.sh), иначе текущим. Сервер слушает только 127.0.0.1.
Зависимость — flask (requirements.txt); при системном Python без pip:
sudo apt install python3-flask.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, \
    send_from_directory

WEB_DIR = Path(__file__).resolve().parent
ROOT = WEB_DIR.parent
UPLOADS = WEB_DIR / "uploads"

GENERATORS = {
    "glitch": {"script": ROOT / "patterns" / "glitch.py",
               "dir": ROOT / "patterns", "label": "Надпись"},
    "belt":   {"script": ROOT / "belt_rus_generator" / "belt_rus.py",
               "dir": ROOT / "belt_rus_generator", "label": "Этно-пояс"},
    "img":    {"script": ROOT / "img_generator" / "img_belt.py",
               "dir": ROOT / "img_generator", "label": "Картинка"},
}

UPLOAD_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
COLORS_DIR_RE = re.compile(r"_cols\d+_colors\d+$")
BAD_NAME = re.compile(r"[^0-9A-Za-zА-Яа-яЁё._-]")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024


class BadInput(Exception):
    """Плохие параметры формы — текст уходит в ответ 400."""


def python_bin() -> str:
    """Интерпретатор для запуска генераторов: .venv, иначе текущий."""
    for cand in (ROOT / ".venv" / "bin" / "python",
                 ROOT / ".venv" / "Scripts" / "python.exe"):
        if cand.exists():
            return str(cand)
    return sys.executable


def out_dir(gen: str) -> Path:
    return GENERATORS[gen]["dir"] / "out"


def _num(value, cast, label):
    try:
        return cast(str(value).strip())
    except (TypeError, ValueError):
        raise BadInput(f"«{label}»: нужно число")


def _out_path(gen, value):
    """--out из формы: только имя файла, всегда внутри out/ генератора."""
    name = BAD_NAME.sub("_", str(value or "").strip())
    if not name:
        return None
    if not name.lower().endswith(".html"):
        name += ".html"
    return out_dir(gen) / name


def build_argv(gen, p):
    """argv (список, без shell) для запуска генератора по данным формы."""
    if gen == "belt":
        return [str(GENERATORS["belt"]["script"])]
    argv = [str(GENERATORS[gen]["script"])]
    if gen == "glitch":
        text = str(p.get("text") or "").strip()
        if not text:
            raise BadInput("Укажите надпись")
        argv += ["--text", text]
        if p.get("preset"):
            argv += ["-t", str(p["preset"])]
        ints = (("cols", "длина"), ("rows", "ряды"), ("tracking", "трекинг"),
                ("seed", "seed"))
        for key, label in ints:
            if str(p.get(key) or "").strip():
                argv += ["--" + key, str(_num(p[key], int, label))]
        floats = (("pitch-mm", "шаг сетки"), ("circle-d-mm", "диаметр кружка"),
                  ("glitch", "сила искажений"))
        for key, label in floats:
            if str(p.get(key) or "").strip():
                argv += ["--" + key, str(_num(p[key], float, label))]
        for flag in ("dropout", "slices", "blackout", "no-symmetrize",
                     "mirror", "no-numbers"):
            if p.get(flag):
                argv.append("--" + flag)
        for key in ("font", "title"):
            if str(p.get(key) or "").strip():
                argv += ["--" + key, str(p[key]).strip()]
        out = _out_path("glitch", p.get("out"))
        if out:
            argv += ["--out", str(out)]
        return argv
    # img
    image = str(p.get("image") or "").strip()
    if not image:
        raise BadInput("Выберите картинку")
    path = UPLOADS / BAD_NAME.sub("_", image)
    if not path.is_file():
        raise BadInput(f"Картинки «{image}» нет в загрузках")
    argv.append(str(path))
    if str(p.get("colors") or "").strip():
        argv += ["-n", str(_num(p["colors"], int, "цвета"))]
    if str(p.get("cols") or "").strip():
        argv += ["--cols", str(_num(p["cols"], int, "длина"))]
    for key, label in (("pitch-mm", "шаг сетки"), ("circle-d-mm", "диаметр")):
        if str(p.get(key) or "").strip():
            argv += ["--" + key, str(_num(p[key], float, label))]
    for flag in ("dither", "mirror", "no-numbers"):
        if p.get(flag):
            argv.append("--" + flag)
    if str(p.get("title") or "").strip():
        argv += ["--title", str(p["title"]).strip()]
    out = _out_path("img", p.get("out"))
    if out:
        argv += ["--out", str(out)]
    return argv


def snapshot_out():
    """{gen: {путь относительно out/: mtime}} по всем html в out/."""
    snap = {}
    for gen in GENERATORS:
        files = {}
        od = out_dir(gen)
        if od.is_dir():
            for f in od.rglob("*.html"):
                if f.is_file():
                    files[str(f.relative_to(od))] = f.stat().st_mtime
        snap[gen] = files
    return snap


def scan_schemes():
    """Список генераций: основной html + его папки _colsN_colorsM."""
    schemes = []
    for gen, info in GENERATORS.items():
        od = out_dir(gen)
        if not od.is_dir():
            continue
        for f in sorted(od.iterdir()):
            if not (f.is_file() and f.suffix.lower() == ".html"):
                continue
            folders = [d for d in od.iterdir()
                       if d.is_dir() and d.name.startswith(f.stem + "_cols")
                       and COLORS_DIR_RE.search(d.name)]
            newest = max(folders, key=lambda d: d.stat().st_mtime, default=None)
            single = []
            if newest:
                single = sorted(x.name for x in newest.iterdir()
                                if x.is_file() and x.suffix.lower() == ".html")
            st = f.stat()
            schemes.append({
                "gen": gen, "gen_label": info["label"], "name": f.name,
                "size": st.st_size, "mtime": st.st_mtime,
                "folder": newest.name if newest else None,
                "single": single,
            })
    return schemes


def scan_uploads():
    items = []
    if UPLOADS.is_dir():
        for f in sorted(UPLOADS.iterdir(), key=lambda x: -x.stat().st_mtime):
            if f.is_file() and f.suffix.lower() in UPLOAD_EXT:
                items.append({"name": f.name, "size": f.stat().st_size,
                              "mtime": f.stat().st_mtime})
    return items


def load_presets():
    cfg = GENERATORS["glitch"]["dir"] / "config.json"
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [k for k in data if not k.startswith("_")]


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def api_state():
    return jsonify(presets=load_presets(), uploads=scan_uploads(),
                   schemes=scan_schemes())


@app.get("/view/<gen>/<path:name>")
def view(gen, name):
    if gen not in GENERATORS:
        abort(404)
    return send_from_directory(out_dir(gen), name)


@app.post("/api/run/<gen>")
def api_run(gen):
    if gen not in GENERATORS:
        abort(404)
    p = request.get_json(force=True, silent=True) or {}
    try:
        argv = build_argv(gen, p)
    except BadInput as e:
        return jsonify(ok=False, error=str(e)), 400
    before = snapshot_out()
    try:
        proc = subprocess.run(
            [python_bin()] + argv, cwd=str(GENERATORS[gen]["dir"]),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=600)
    except subprocess.TimeoutExpired:
        return jsonify(ok=False, error="Скрипт не завершился за 10 минут"), 504
    except OSError as e:
        return jsonify(ok=False, error=f"Не удалось запустить: {e}"), 500
    created = []
    for gen2, files in snapshot_out().items():
        for rel, mtime in files.items():
            if rel not in before[gen2] or mtime > before[gen2][rel] + 1e-6:
                created.append({"gen": gen2, "name": rel})
    # основной файл (без «/») — первым
    created.sort(key=lambda c: ("/" in c["name"], c["name"]))
    ok = proc.returncode == 0
    return jsonify(ok=ok, stdout=proc.stdout, stderr=proc.stderr,
                   created=created)


@app.post("/api/upload")
def api_upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify(ok=False, error="Файл не выбран"), 400
    name = BAD_NAME.sub("_", Path(f.filename).name)
    if Path(name).suffix.lower() not in UPLOAD_EXT:
        return jsonify(ok=False, error="Нужна картинка: "
                       + ", ".join(sorted(UPLOAD_EXT))), 400
    UPLOADS.mkdir(parents=True, exist_ok=True)
    dest = UPLOADS / name
    if dest.exists():
        dest = UPLOADS / f"{int(time.time())}_{name}"
    f.save(dest)
    return jsonify(ok=True, name=dest.name)


@app.post("/api/uploads/delete")
def api_uploads_delete():
    name = (request.get_json(force=True, silent=True) or {}).get("name", "")
    path = UPLOADS / BAD_NAME.sub("_", str(name))
    if not path.is_file():
        return jsonify(ok=False, error="Нет такой загрузки"), 404
    path.unlink()
    return jsonify(ok=True)


@app.post("/api/schemes/delete")
def api_schemes_delete():
    data = request.get_json(force=True, silent=True) or {}
    gen, name = data.get("gen", ""), str(data.get("name", ""))
    if (gen not in GENERATORS or "/" in name or "\\" in name
            or ".." in name or not name.lower().endswith(".html")):
        return jsonify(ok=False, error="Плохое имя схемы"), 400
    od = out_dir(gen)
    main = od / name
    if not main.is_file():
        return jsonify(ok=False, error="Схемы нет"), 404
    for d in od.iterdir():
        if d.is_dir() and d.name.startswith(main.stem + "_cols") \
                and COLORS_DIR_RE.search(d.name):
            shutil.rmtree(d)
    main.unlink()
    return jsonify(ok=True)


def main():
    ap = argparse.ArgumentParser(description="Веб-интерфейс генераторов схем")
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("PORT", 8000)))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true",
                    help="не открывать браузер автоматически")
    args = ap.parse_args()
    url = f"http://{args.host}:{args.port}"
    print(f"Веб-интерфейс: {url}  (Ctrl+C — остановить)")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
