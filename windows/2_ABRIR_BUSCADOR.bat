@echo off
cd /d "%~dp0.."
call "%~dp0_python.bat" || (echo Falta Python: ejecuta primero 1_INSTALAR.bat & pause & exit /b)
rem Abre la ventana con pythonw (sin consola). Si no existe, con python comun.
"%PY%" -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" > "%TEMP%\remitos_pyw.txt"
set /p PYW=<"%TEMP%\remitos_pyw.txt"
if not exist "%PYW%" set "PYW=%PY%"
start "" "%PYW%" buscar_remitos.py gui
