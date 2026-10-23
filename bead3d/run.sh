#!/usr/bin/env bash
# d3Sc: запуск через http-сервер. Меню «Загрузить» (схемы из default/)
# работает только по http — при открытии index.html двойным кликом (file://)
# браузер запрещает странице читать папку, это ограничение безопасности.
# Использование: ./run.sh [порт]   (по умолчанию 8100)
cd "$(dirname "$0")"
port="${1:-8100}"
if ! curl -s -o /dev/null --max-time 1 "http://127.0.0.1:$port/"; then
  nohup python3 -m http.server "$port" >/dev/null 2>&1 &
  sleep 0.7
fi
exec xdg-open "http://127.0.0.1:$port/"
