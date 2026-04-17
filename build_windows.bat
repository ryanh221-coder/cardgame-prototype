@echo off
setlocal

if not exist .venv (
    python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name CardGamePrototype src\main.py

echo.
echo Build complete. Your exe should be at:
echo dist\CardGamePrototype.exe
