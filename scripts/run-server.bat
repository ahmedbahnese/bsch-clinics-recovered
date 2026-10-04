@echo off
setlocal
cd /d "%~dp0.."
if "%BSCH_OPERATING_MODE%"=="" set BSCH_OPERATING_MODE=standalone_offline
if "%BSCH_HOST%"=="" set BSCH_HOST=0.0.0.0
if "%BSCH_PORT%"=="" set BSCH_PORT=4173
python app.py
pause
