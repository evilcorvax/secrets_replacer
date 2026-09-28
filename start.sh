#!/usr/bin/env bash
# Запуск утилиты обезличивания на macOS / Linux.
# Сам ставит зависимости в локальное окружение .venv и запускает GUI.
# Двойной клик по файлу в Finder тоже работает (chmod +x выполнен).

set -euo pipefail
cd "$(dirname "$0")"

# Выбираем самый подходящий Python: 3.10–3.13 (проверены на совместимость
# со всеми зависимостями). Если такого нет — берём системный python3.
PY=""
for cand in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        PY="$cand"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "Не найден Python. Установите Python 3.10+ (например, brew install python)."
    exit 1
fi

# Homebrew-питон поставляется без Tk: без него GUI не запустится.
if ! "$PY" -c "import tkinter" >/dev/null 2>&1; then
    echo "В вашем Python нет модуля tkinter (нужен для GUI)."
    echo "Установите привязки Tk:  brew install python-tk"
    echo "(для python3.13 — brew install python-tk@3.13, далее пересоздайте .venv)"
    exit 1
fi

echo "Используется интерпретатор: $PY ($("$PY" --version 2>&1))"

# Окружение создаём один раз; дальше запуск мгновенный.
if [ ! -d ".venv" ]; then
    echo "Первый запуск: создаю виртуальное окружение .venv ..."
    "$PY" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if [ ! -f ".venv/.deps_installed" ]; then
    echo "Устанавливаю зависимости ..."
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    touch .venv/.deps_installed
fi

exec python main.py
