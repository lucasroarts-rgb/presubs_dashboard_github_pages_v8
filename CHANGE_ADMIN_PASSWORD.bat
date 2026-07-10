@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\change_admin_password.ps1"
if errorlevel 1 pause
