@echo off
title Pack Campaign Export Analyzer for teammate
cd /d "%~dp0"

set OUT=Campaign_Export_Analyzer_Package
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%"
mkdir "%OUT%\templates"

copy /Y START_APP.bat "%OUT%\"
copy /Y SHARE_APP.bat "%OUT%\" 2>nul
copy /Y app.py "%OUT%\"
copy /Y ko_parser.py "%OUT%\"
copy /Y analyzer.py "%OUT%\"
copy /Y requirements-app.txt "%OUT%\requirements.txt"
copy /Y templates\index.html "%OUT%\templates\"
copy /Y README.txt "%OUT%\" 2>nul
copy /Y READ_ME_FIRST.txt "%OUT%\"

powershell -Command "Compress-Archive -Path '%OUT%' -DestinationPath '%OUT%.zip' -Force"
echo.
echo  Created: %OUT%.zip
echo  Send this ZIP to your teammate. She unzips and double-clicks START_APP.bat
echo.
pause
