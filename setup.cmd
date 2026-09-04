@echo off
chcp 65001 >nul
rem setup.cmd — подготовка окружения для генераторов схем (Windows).
rem
rem Что делает (однократно на машине), подбирая первый подходящий вариант:
rem   a) уже есть .venv в корне проекта — доустанавливает зависимости в него;
rem   b) Pillow уже стоит в найденном Python — ничего не трогает;
rem   c) создаёт .venv и ставит зависимости из requirements.txt туда;
rem   d) venv не создался — pip install --user в этот же Python.
rem Затем проверяет import PIL и печатает команды запуска генераторов.
rem
rem Запуск: двойной клик по setup.cmd или "setup.cmd" в терминале.
rem Повторный запуск безвреден.

setlocal
cd /d "%~dp0"

echo == Подготовка окружения bogda2na ==

rem --- 1. Найти Python 3.8+ --------------------------------------------
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1 && set "PY=python"
if not defined PY python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1 && set "PY=python3"

if not defined PY (
    echo [X] Python 3.8+ не найден.
    echo     Установи его с https://www.python.org/downloads/
    echo     ^(при установке отметь галочку "Add python.exe to PATH"^),
    echo     затем запусти setup.cmd заново.
    exit /b 1
)
echo [OK] Python: %PY%

rem --- 2. Способ запуска -------------------------------------------------
set "RUNPY="

rem a) готовый .venv
if exist ".venv\Scripts\python.exe" (
    set "RUNPY=.venv\Scripts\python.exe"
    echo [OK] Найден .venv — обновляю зависимости ...
    goto deps
)

rem b) Pillow уже есть в этом Python
%PY% -c "import PIL" >nul 2>&1
if not errorlevel 1 (
    set "RUNPY=%PY%"
    echo [OK] Pillow уже есть в этом Python — ничего устанавливать не нужно
    goto check
)

rem c) создать .venv
echo [..] Создаю .venv ...
%PY% -m venv .venv
if errorlevel 1 goto pipuser
set "RUNPY=.venv\Scripts\python.exe"

:deps
echo [..] Ставлю зависимости из requirements.txt ...
%RUNPY% -m pip install --quiet --upgrade pip
if errorlevel 1 ( echo [X] Не удалось обновить pip. & exit /b 1 )
%RUNPY% -m pip install --quiet -r requirements.txt
if errorlevel 1 ( echo [X] Ошибка установки зависимостей — смотри сообщения pip. & exit /b 1 )
goto check

:pipuser
echo [..] venv не создался — ставлю зависимости в профиль пользователя ...
%PY% -m pip install --quiet --user -r requirements.txt
if errorlevel 1 ( echo [X] Ошибка установки зависимостей — смотри сообщения pip. & exit /b 1 )
set "RUNPY=%PY%"

:check
rem --- 3. Самопроверка ----------------------------------------------------
%RUNPY% -c "import PIL; print('[OK] Pillow', PIL.__version__, '- всё готово')"
if errorlevel 1 ( echo [X] Pillow не установился. & exit /b 1 )

rem --- 4. Подсказки --------------------------------------------------------
echo.
echo Запуск генераторов ^(из корня проекта^):
if "%RUNPY%"==".venv\Scripts\python.exe" (
    echo   .venv\Scripts\python patterns\glitch.py -t belt_90 --text "ГЛИТЧ"
    echo   .venv\Scripts\python belt_rus_generator\belt_rus.py
    echo   .venv\Scripts\python img_generator\img_belt.py картинка.png -n 8
    echo.
    echo Короче — после активации окружения:
    echo   .venv\Scripts\activate
    echo   python img_generator\img_belt.py картинка.png -n 8
) else (
    echo   %PY% patterns\glitch.py -t belt_90 --text "ГЛИТЧ"
    echo   %PY% belt_rus_generator\belt_rus.py
    echo   %PY% img_generator\img_belt.py картинка.png -n 8
)
echo.
echo Шпаргалка по любому генератору: python ^<скрипт^> help

endlocal

