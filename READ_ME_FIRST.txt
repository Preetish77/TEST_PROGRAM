READ THIS FIRST
===============

DO NOT double-click app.py.
DO NOT run START_APP.bat from inside the zip file.

STEPS:
1. Right-click "Campaign_Export_Analyzer_Package.zip"
2. Click "Extract All..."
3. Choose a folder (e.g. Desktop or Documents)
4. Click Extract
5. Open the new folder "Campaign_Export_Analyzer_Package"
6. Double-click START_APP.bat in that extracted folder

You should see these files in the same folder as START_APP.bat:
  - app.py
  - analyzer.py
  - ko_parser.py
  - requirements.txt
  - templates (folder)
  - CHECK_SETUP.bat  (run this first if START_APP fails)

REQUIREMENTS:
- Python 3 from https://www.python.org/downloads/
- During install, CHECK the box: "Add Python to PATH"
- After installing Python, close all windows and run START_APP.bat again

Browser opens at: http://127.0.0.1:5000
(If browser does not open automatically, type that address in Chrome or Edge.)

TROUBLESHOOTING
---------------

Problem: Double-clicking app.py asks "What app do you want to open this with?"
Answer: Python is not installed. Install Python 3 (see above). Do NOT open app.py
        directly — always use START_APP.bat.

Problem: START_APP.bat flashes and closes too fast
Answer: Double-click CHECK_SETUP.bat instead. It will stay open and show what is wrong.
        Most often: Python is not installed or "Add to PATH" was not checked.

Problem: Command window opens but no browser
Answer: Manually open http://127.0.0.1:5000 in Chrome or Edge.
        Keep the black command window open while using the app.

Problem: "Failed to install dependencies"
Answer: Run CHECK_SETUP.bat. If on a work laptop, you may need IT to allow pip installs.
