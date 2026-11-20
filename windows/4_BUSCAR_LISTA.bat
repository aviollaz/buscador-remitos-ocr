@echo off
chcp 65001 >nul
cd /d "%~dp0.."
call "%~dp0_python.bat" || (echo Falta Python: ejecuta primero 1_INSTALAR.bat & pause & exit /b)
"%PY%" -c "import openpyxl" >nul 2>&1 || (echo Instalando soporte para Excel... & "%PY%" -m pip install --quiet openpyxl)
echo ================================================
echo   Busqueda de una lista de remitos
echo ================================================
echo.
echo Arrastra aca el Excel con los numeros y apreta Enter.
echo (Los numeros tienen que estar en la primera columna, con o sin titulo.)
echo.
echo O apreta Enter sin nada para pegar la lista en el Bloc de notas.
echo.
set "ENTRADA="
set /p ENTRADA=
if defined ENTRADA set ENTRADA=%ENTRADA:"=%
if not defined ENTRADA goto pegar
goto preguntar

:pegar
type nul > "%~dp0lista.txt"
echo Pega los numeros ^(uno por renglon^), guarda con Ctrl+G y cerra el Bloc de notas.
notepad "%~dp0lista.txt"
set "ENTRADA=%~dp0lista.txt"

:preguntar
echo.
choice /c SN /m "Copiar los remitos encontrados a una carpeta nueva"
if errorlevel 2 (
  "%PY%" buscar_remitos.py lista "%ENTRADA%" auto --abrir
) else (
  "%PY%" buscar_remitos.py lista "%ENTRADA%" auto --copiar auto --abrir
)
echo.
pause
