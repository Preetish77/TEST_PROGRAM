@echo off
title Publish to GitHub - Campaign Export Analyzer
cd /d "%~dp0"

echo.
echo  ====================================================
echo   Publish to GitHub (GitHub Desktop)
echo  ====================================================
echo.
echo  Your project is ready with a git commit.
echo.
echo  STEP 1 - Add to GitHub Desktop
echo  --------------------------------
echo  1. Open GitHub Desktop
echo  2. File - Add local repository
echo  3. Choose this folder:
echo     %~dp0
echo  4. Click Add repository
echo.
echo  STEP 2 - Publish to GitHub
echo  --------------------------------
echo  1. Click "Publish repository"
echo  2. Name: campaign-analyzer  (or any name you like)
echo  3. Uncheck "Keep this code private" if you want a free
echo     Streamlit link (public repo = free hosting)
echo  4. Click Publish repository
echo.
echo  STEP 3 - Get your shareable link
echo  --------------------------------
echo  1. Open: https://share.streamlit.io
echo  2. Sign in with GitHub
echo  3. New app - pick your repo
echo  4. Main file: streamlit_app.py
echo  5. Deploy
echo.
echo  Your link will look like:
echo  https://campaign-analyzer.streamlit.app
echo.
echo  ====================================================
echo.
echo  Opening GitHub Desktop and Streamlit Cloud...
echo.

start "" "github-windows://openLocalRepo/%~dp0"
timeout /t 2 /nobreak >nul
start "" "https://share.streamlit.io"

pause
