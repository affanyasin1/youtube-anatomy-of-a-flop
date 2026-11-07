@echo off
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" -m collector.rebuild
if errorlevel 1 pause
