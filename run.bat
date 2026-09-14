@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Once setup.bat dosyasini calistirin.
  exit /b 1
)
call ".venv\Scripts\activate.bat"
python -m streamlit run app.py

