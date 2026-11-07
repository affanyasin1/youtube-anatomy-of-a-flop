@echo off
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" -m pytest -q -p no:cacheprovider --rootdir=. --confcutdir=. tests
pause
