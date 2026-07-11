@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_history.ps1" -Year 2026
if errorlevel 1 pause
