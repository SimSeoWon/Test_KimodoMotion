@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run-webui.ps1" %*
if errorlevel 1 pause
exit /b %errorlevel%
