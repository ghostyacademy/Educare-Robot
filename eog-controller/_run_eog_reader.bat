@echo off
REM Usage : _run_eog_reader.bat [PORT_ARDUINO]   (defaut COM16)
cd /d "%~dp0"
set PORT=%1
if "%PORT%"=="" set PORT=COM16
python serial-read-eog.py %PORT%
pause
