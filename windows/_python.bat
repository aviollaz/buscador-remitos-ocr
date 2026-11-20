@echo off
rem Busca una instalacion real de Python y la deja en la variable PY
set "PY="
python -c "import sys" >nul 2>&1 && (set "PY=python" & exit /b 0)
py -c "import sys" >nul 2>&1 && (set "PY=py" & exit /b 0)
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%D\python.exe" set "PY=%%D\python.exe"
if not defined PY for /d %%D in ("%ProgramFiles%\Python3*") do if exist "%%D\python.exe" set "PY=%%D\python.exe"
if defined PY exit /b 0
exit /b 1
