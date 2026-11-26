@echo off
chcp 65001 >nul
cd /d "%~dp0programa"
echo ================================================
echo   Instalador del Buscador de Remitos
echo ================================================
echo.

where winget >nul 2>&1
if errorlevel 1 (
  echo ERROR: esta PC no tiene winget. Instala Python y Tesseract a mano
  echo siguiendo la seccion "INSTALACION MANUAL" de INSTRUCCIONES.txt
  pause
  exit /b
)

call "%~dp0programa\_python.bat"
if defined PY (
  echo [1/3] Python ya esta instalado.
) else (
  echo [1/3] Instalando Python... ^(puede tardar unos minutos^)
  winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
  call "%~dp0programa\_python.bat"
)
if not defined PY (
  echo ERROR: no se pudo instalar Python. Ver INSTRUCCIONES.txt
  pause
  exit /b
)

set "TESS="
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "TESS=1"
if exist "%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe" set "TESS=1"
if defined TESS (
  echo [2/3] Tesseract ya esta instalado.
) else (
  echo [2/3] Instalando Tesseract... ^(si Windows pide permiso, acepta^)
  winget install -e --id UB-Mannheim.TesseractOCR --silent --accept-package-agreements --accept-source-agreements
)

echo [3/3] Instalando librerias...
"%PY%" -m pip install --upgrade --quiet -r requirements.txt

echo.
"%PY%" buscador.py verificar
echo.
pause
