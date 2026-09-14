@echo off
setlocal

if not exist .venv\Scripts\python.exe (
  echo Missing .venv. Run install.bat first.
  exit /b 1
)

.venv\Scripts\python.exe app.py
