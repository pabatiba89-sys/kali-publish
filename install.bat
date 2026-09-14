@echo off
setlocal

python -m venv .venv || exit /b 1
call .venv\Scripts\activate.bat || exit /b 1
python -m pip install --upgrade pip || exit /b 1
python -m pip install -r requirements.txt || exit /b 1

echo Installed. Make sure Google Chrome is available, then run start.bat.
