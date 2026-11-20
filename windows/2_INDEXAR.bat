@echo off
chcp 65001 >nul
cd /d "%~dp0.."
call "%~dp0_python.bat" || (echo Falta Python: ejecuta primero 1_INSTALAR.bat & pause & exit /b)
"%PY%" -c "import pymupdf" >nul 2>&1 || (echo Instalando soporte para PDF... & "%PY%" -m pip install --quiet pymupdf)
echo Arrastra aca la carpeta de los remitos y apreta Enter
echo (o escribi la ruta, por ejemplo D:\Remitos). Incluye subcarpetas.
set "CARPETA="
set /p CARPETA=
if not defined CARPETA exit /b
set CARPETA=%CARPETA:"=%
"%PY%" buscar_remitos.py indexar "%CARPETA%"
echo.
echo Exportando listado a remitos.csv ...
"%PY%" buscar_remitos.py exportar remitos.csv
pause
