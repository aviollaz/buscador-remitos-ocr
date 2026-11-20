@echo off
chcp 65001 >nul
cd /d "%~dp0.."
call "%~dp0_python.bat" || (echo Falta Python: ejecuta primero 1_INSTALAR.bat & pause & exit /b)
"%PY%" -c "import openpyxl" >nul 2>&1 || (echo Instalando soporte para Excel... & "%PY%" -m pip install --quiet openpyxl)
echo Generando Excel con todos los remitos indexados hasta ahora...
"%PY%" buscar_remitos.py excel --abrir
echo.
pause
