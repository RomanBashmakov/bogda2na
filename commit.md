chore(окружение): универсальная подготовка — setup.sh / setup.cmd + requirements.txt

Одна команда на новой машине (Linux/macOS/Windows) готовит всё
для генераторов схем, ручная установка зависимостей больше не нужна:

- requirements.txt — единственная внешняя зависимость Pillow
  (нужна только img_generator/img_belt.py; glitch.py и belt_rus.py — stdlib);
- setup.sh (Linux/macOS) и setup.cmd (Windows): поиск Python 3.8+
  (на Windows — py -3 / python / python3), затем цепочка вариантов:
  готовый .venv → Pillow уже есть в найденном Python → создать .venv
  и поставить зависимости → pip install --user (+ --break-system-packages
  на новых Ubuntu/Debian) → точная инструкция, чего не хватает;
  в конце — самопроверка import PIL и готовые команды запуска;
- README.md в корне — установка и запуск всех трёх генераторов;
- .gitignore: .venv/, __pycache__/;
- докстринг img_belt.py и раздел «Что понадобится» в patterns/README.md
  теперь ведут на setup вместо ручного pip install.

Проверено: на машине без pip и python3-venv, но с системным Pillow 9.0.1
setup.sh корректно выбирает вариант «ничего не ставить»; повторный запуск
идемпотентен; все генераторы запускаются напечатанными командами;
полный прогон img_belt из найденного окружения — OK. setup.cmd на
реальной Windows не проверялся.

