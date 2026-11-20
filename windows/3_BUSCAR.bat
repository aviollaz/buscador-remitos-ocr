@echo off
chcp 65001 >nul
cd /d "%~dp0.."
call "%~dp0_python.bat" || (echo Falta Python: ejecuta primero 1_INSTALAR.bat & pause & exit /b)
:loop
echo.
echo ============================================
set "NUM="
set /p NUM=Numero de remito, o nombre de cliente (Enter vacio para salir): 
if not defined NUM exit /b
set NUM=%NUM:"=%
echo %NUM%| findstr /r "[0-9]" >nul
if errorlevel 1 (
  "%PY%" buscar_remitos.py texto "%NUM%"
) else (
  "%PY%" buscar_remitos.py buscar "%NUM%"
)
goto loop
