@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_automation.ps1" -NoPublish
if errorlevel 1 pause
