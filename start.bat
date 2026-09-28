@echo off
chcp 65001 >nul
rem Запуск утилиты обезличивания на Windows.
rem Сам ставит зависимости в локальное окружение .venv и запускает GUI.
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Не найден Python. Установите Python 3.10+ с https://python.org и отметьте "Add Python to PATH".
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Первый запуск: создаю виртуальное окружение .venv ...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

if not exist ".venv\.deps_installed" (
    echo Устанавливаю зависимости ...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    type nul > .venv\.deps_installed
)

python main.py
