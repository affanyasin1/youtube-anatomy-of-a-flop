@echo off
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" -m collector.main
if errorlevel 1 pause
