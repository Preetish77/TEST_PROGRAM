@echo off
setlocal EnableDelayedExpansion
title Campaign Export Analyzer - Setup Check
cd /d "%~dp0"

echo.
echo  Campaign Export Analyzer - Setup Check
echo  ======================================
echo.
echo  Folder: %CD%
echo.

echo --- Required files ---
set OK=1
for %%F in (app.py analyzer.py ko_parser.py requirements.txt templates\index.html START_APP.bat) do (
    if exist "%%F" (
        echo  [OK]   %%F
    ) else (
        echo  [MISS] %%F
        set OK=0
    )
)
echo.

echo --- Python ---
set FOUND=0
where py >nul 2>&1
if !errorlevel!==0 (
    echo  [OK]   py launcher found
    py -3 --version 2>nul
    if !errorlevel!==0 set FOUND=1
)
where python >nul 2>&1
if !errorlevel!==0 (
    echo  [OK]   python found
    python --version 2>nul
    if !errorlevel!==0 set FOUND=1
)
if !FOUND!==0 (
    echo  [FAIL] Python 3 is NOT installed or not on PATH.
    echo.
    echo  FIX: Install from https://www.python.org/downloads/
    echo       Check "Add Python to PATH" during install.
    echo       Then close ALL windows and double-click START_APP.bat again.
    echo.
    echo  Do NOT double-click app.py — Windows will ask what app to use.
    set OK=0
) else (
    echo  [OK]   Python works
)
echo.

echo --- pip + Flask test ---
if !FOUND!==1 (
    where py >nul 2>&1 && py -3 -m pip --version >nul 2>&1 && set PIP=py -3 -m pip
    if not defined PIP where python >nul 2>&1 && python -m pip --version >nul 2>&1 && set PIP=python -m pip
    if defined PIP (
        echo  [OK]   pip found
        !PIP! install -r requirements.txt -q --no-warn-script-location
        if !errorlevel! neq 0 (
            echo  [FAIL] Could not install requirements.txt
            set OK=0
        ) else (
            echo  [OK]   dependencies installed
        )
    ) else (
        echo  [FAIL] pip not found
        set OK=0
    )
)
echo.

if !OK!==1 (
    echo  RESULT: Ready! Double-click START_APP.bat to run the app.
) else (
    echo  RESULT: Setup incomplete — fix the [FAIL] items above.
)
echo.
pause
