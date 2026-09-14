@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.11 -m venv .venv 2>nul || py -3 -m venv .venv
  if errorlevel 1 goto :fail
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 goto :fail
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail
python -m puzzly.check_environment
if errorlevel 1 goto :fail
echo.
echo Puzzly kurulumu basariyla tamamlandi.
exit /b 0
:fail
echo.
echo HATA: Kurulum tamamlanamadi. Yukaridaki mesaji kontrol edin.
exit /b 1

