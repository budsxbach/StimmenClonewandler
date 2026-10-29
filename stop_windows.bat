@echo off
rem ===================================================================
rem  StimmenClonewandler - beendet alle laufenden Instanzen (Windows)
rem ===================================================================
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo === StimmenClonewandler beenden ===
echo.

set "FOUND=0"

for /f "tokens=1,2" %%a in ('wmic process where "name='python.exe'" get ProcessId^,CommandLine /format:csv 2^>nul ^| findstr /i "app.server"') do (
    set "FOUND=1"
    echo [i] Beende Prozess %%a
    taskkill /PID %%a /F >nul 2>nul
)

if "!FOUND!"=="0" (
    echo [i] Es lief keine Instanz der App.
)

rem Ports pruefen (falls netstat vorhanden)
echo.
echo [i] Pruefe Port 8765:
netstat -ano | findstr /r ":8765 .*LISTENING" || echo     Port 8765 ist frei.

if exist "data\.port" del /q "data\.port" >nul 2>nul

echo.
echo Fertig. Neustart mit: start_windows.bat
echo.
pause
