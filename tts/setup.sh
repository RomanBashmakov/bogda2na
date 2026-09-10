#!/usr/bin/env bash
# Окружение для озвучки книг (Silero TTS): tts/.venv + PyTorch (+CUDA).
# Повторный запуск безвреден. Интернет нужен только здесь и при первом
# синтезе (Silero докачает веса ~60 МБ в ~/.cache/torch).
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || { echo "Нет python3 — sudo apt install python3"; exit 1; }

if [ ! -x .venv/bin/python ]; then
  echo "Создаю tts/.venv ..."
  if ! "$PY" -m venv .venv 2>/dev/null; then
    echo "python3 -m venv не вышел — пробую virtualenv (pip install --user) ..."
    "$PY" -m pip install --user -q virtualenv \
      || { echo "Не вышло. Поставьте: sudo apt install python3-venv python3-pip"; exit 1; }
    VENV_BIN="$HOME/.local/bin/virtualenv"
    [ -x "$VENV_BIN" ] || VENV_BIN="$(command -v virtualenv || true)"
    [ -n "${VENV_BIN:-}" ] || { echo "virtualenv не найден после установки"; exit 1; }
    "$VENV_BIN" -p "$PY" .venv
  fi
fi

echo "Ставлю зависимости (torch качается ~1 ГБ, это разово) ..."
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt

echo
echo "Проверка окружения:"
.venv/bin/python - <<'EOF'
import torch
print("torch", torch.__version__)
print("CUDA:", "есть — синтез будет на GPU" if torch.cuda.is_available()
      else "нет — будет CPU (медленнее, но работает)")
EOF

if command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg: системный найден"
else
  echo "ffmpeg: системного нет — будет запасной из pip (imageio-ffmpeg)"
  echo "        (для системного: sudo apt install ffmpeg)"
fi

echo
echo "Готово. Шпаргалка: tts/.venv/bin/python tts/book2audio.py help"
echo "Демо голосов: tts/.venv/bin/python tts/book2audio.py --demo"
