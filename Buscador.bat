@echo off
cd /d "%~dp0programa"
call "%~dp0programa\_python.bat" || (echo Falta Python: ejecuta primero Instalar & pause & exit /b)
rem Abre la ventana con pythonw (sin consola). Si no existe, con python comun.
"%PY%" -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" > "%TEMP%\remitos_pyw.txt"
set /p PYW=<"%TEMP%\remitos_pyw.txt"
if not exist "%PYW%" set "PYW=%PY%"
start "" "%PYW%" buscador.py gui
