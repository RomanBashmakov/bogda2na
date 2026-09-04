#!/usr/bin/env bash
# setup.sh — подготовка окружения для генераторов схем (Linux/macOS).
#
# Что делает (однократно на машине), подбирая первый подходящий вариант:
#   a) уже есть .venv в корне проекта — доустанавливает зависимости в него;
#   b) Pillow уже стоит в найденном Python — ничего не трогает;
#   c) создаёт .venv и ставит зависимости из requirements.txt туда;
#   d) venv невозможен (нет python3-venv) — pip install --user;
#   e) ничего не вышло — печатает точную команду установки недостающего.
# Затем проверяет import PIL и печатает команды запуска генераторов.
#
# Запуск из любой папки:  bash setup.sh   (или: ./setup.sh)
# Повторный запуск безвреден.

set -euo pipefail
cd "$(dirname "$0")"

echo "== Подготовка окружения bogda2na =="

# --- 1. Найти Python 3.8+ ---------------------------------------------
PY=""
for cand in python3 python python3.12 python3.11 python3.10 python3.9 python3.8; do
    if command -v "$cand" >/dev/null 2>&1; then
        if "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
            PY="$cand"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    echo "✗ Python 3.8+ не найден. Установи его и запусти setup.sh заново:"
    echo "    Ubuntu/Debian:  sudo apt install python3 python3-venv"
    echo "    Fedora:         sudo dnf install python3"
    echo "    macOS:          brew install python   (или установщик с python.org)"
    exit 1
fi
echo "✓ Python: $PY ($("$PY" --version 2>&1))"

REQ_OK() {  # интерпретатор $1 умеет всё, что нужно генераторам
    "$1" -c "import PIL" >/dev/null 2>&1
}

# --- 2. Способ запуска ---------------------------------------------------
RUN=""

# a) готовый .venv — использовать его, зависимости обновить
if [ -x ".venv/bin/python" ]; then
    RUN=".venv/bin/python"
    echo "✓ Найден .venv — обновляю зависимости …"
    "$RUN" -m pip install --quiet -r requirements.txt

# b) Pillow уже есть в этом Python — устанавливать ничего не нужно
elif REQ_OK "$PY"; then
    RUN="$PY"
    echo "✓ Pillow уже есть в этом Python — ничего устанавливать не нужно"

# c) создать .venv (лучший вариант: система не затрагивается)
elif "$PY" -m venv .venv >/dev/null 2>&1 && [ -x ".venv/bin/python" ]; then
    RUN=".venv/bin/python"
    echo "· Создал .venv, ставлю зависимости из requirements.txt …"
    "$RUN" -m pip install --quiet --upgrade pip
    "$RUN" -m pip install --quiet -r requirements.txt

# d) venv не создался (нет python3-venv) — поставить в профиль пользователя
elif "$PY" -m pip --version >/dev/null 2>&1; then
    RUN="$PY"
    echo "· venv недоступен, ставлю зависимости в профиль пользователя (pip --user) …"
    if ! "$PY" -m pip install --quiet --user -r requirements.txt; then
        # новые Debian/Ubuntu (PEP 668): pip требует явного разрешения
        "$PY" -m pip install --quiet --user --break-system-packages -r requirements.txt
    fi

# e) ничего не получилось — точная инструкция
else
    rm -rf .venv
    echo "✗ Не получилось ни .venv (нет python3-venv), ни pip. Установи одно из них и повтори:"
    echo "    Ubuntu/Debian:  sudo apt install python3-venv   (или python3-pip)"
    echo "    Fedora:         sudo dnf install python3-pip"
    echo "    macOS/прочее:   python3 с python.org или brew — там venv есть из коробки"
    exit 1
fi

# --- 3. Самопроверка ------------------------------------------------------
if REQ_OK "$RUN"; then
    echo "✓ $("$RUN" -c 'import PIL; print("Pillow", PIL.__version__)') — всё готово"
else
    echo "✗ Pillow всё равно не импортируется — смотри сообщения выше."
    exit 1
fi

# --- 4. Подсказки ----------------------------------------------------------
echo
echo "Запуск генераторов (из корня проекта):"
if [ "$RUN" = ".venv/bin/python" ]; then
    echo "  .venv/bin/python patterns/glitch.py -t belt_90 --text \"ГЛИТЧ\""
    echo "  .venv/bin/python belt_rus_generator/belt_rus.py"
    echo "  .venv/bin/python img_generator/img_belt.py картинка.png -n 8"
    echo
    echo "Короче — после активации окружения:"
    echo "  source .venv/bin/activate"
    echo "  python img_generator/img_belt.py картинка.png -n 8"
else
    echo "  $PY patterns/glitch.py -t belt_90 --text \"ГЛИТЧ\""
    echo "  $PY belt_rus_generator/belt_rus.py"
    echo "  $PY img_generator/img_belt.py картинка.png -n 8"
fi
echo
echo "Шпаргалка по любому генератору: <python> <скрипт> help"

