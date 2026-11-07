@echo off
cd /d "%~dp0"
echo Open this address in your browser: http://127.0.0.1:8000/dashboard.html
echo Keep this window open. Press Ctrl+C to stop.
if not exist "results\demo\manifest.json" (
  "%~dp0.venv\Scripts\python.exe" -m collector.rebuild
  if errorlevel 1 exit /b 1
)
"%~dp0.venv\Scripts\python.exe" serve.py --data-dir results/demo
pause
