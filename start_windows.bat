@echo off
rem ===================================================================
rem  StimmenClonewandler - Startskript fuer Windows
rem  Startet die App lokal auf http://127.0.0.1:8765
rem  Es wird nichts ins Internet hochgeladen.
rem ===================================================================
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ===========================================================
echo   StimmenClonewandler - lokaler Start
echo ===========================================================
echo.

rem --- Python finden -------------------------------------------------
set "PYEXE="
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 --version >nul 2>nul
    if !errorlevel!==0 set "PYEXE=py -3"
)
if not defined PYEXE (
    where python >nul 2>nul
    if !errorlevel!==0 set "PYEXE=python"
)
if not defined PYEXE (
    echo [FEHLER] Python wurde nicht gefunden.
    echo.
    echo Bitte Python 3.9 bis 3.12 von https://www.python.org/downloads/windows/
    echo installieren und dabei "Add python.exe to PATH" aktivieren.
    echo Danach dieses Fenster schliessen und das Skript erneut starten.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('%PYEXE% --version 2^>^&1') do set "PYVER=%%v"
echo [i] Gefunden: !PYVER!

rem --- Virtuelle Umgebung anlegen ------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo [i] Erste Einrichtung: virtuelle Umgebung wird erstellt ...
    %PYEXE% -m venv .venv
    if !errorlevel! neq 0 (
        echo [FEHLER] Die virtuelle Umgebung konnte nicht erstellt werden.
        pause
        exit /b 1
    )
)

set "VPY=.venv\Scripts\python.exe"

rem --- Abhaengigkeiten pruefen ---------------------------------------
"%VPY%" -c "import flask, piper" >nul 2>nul
if !errorlevel! neq 0 (
    echo [i] Benoetigte Pakete werden installiert - dies braucht einmalig Internet.
    echo     Danach arbeitet die App vollstaendig offline.
    "%VPY%" -m pip install --upgrade pip >nul 2>nul
    "%VPY%" -m pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo.
        echo [FEHLER] Installation fehlgeschlagen. Bitte die Meldung oben pruefen.
        echo Hinweis: Fuer die Installation wird einmalig eine Internetverbindung benoetigt.
        pause
        exit /b 1
    )
)

rem --- Arbeitsordner anlegen -----------------------------------------
if not exist "data\aufnahmen" mkdir "data\aufnahmen"
if not exist "data\ergebnisse" mkdir "data\ergebnisse"
if not exist "data\master" mkdir "data\master"
if not exist "data\tmp" mkdir "data\tmp"
if not exist "data\modelle\piper" mkdir "data\modelle\piper"
if not exist "data\modelle\xtts" mkdir "data\modelle\xtts"

rem --- Browser oeffnen (kurz verzoegert) -----------------------------
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8765"

echo.
echo [i] Server startet. Browser oeffnet sich gleich automatisch.
echo [i] Zum Beenden: Strg+C druecken oder dieses Fenster schliessen.
echo.
"%VPY%" -m app.server

echo.
echo [i] Server beendet.
pause
