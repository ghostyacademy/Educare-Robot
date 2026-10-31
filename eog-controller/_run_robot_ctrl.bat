@echo off
REM Usage : _run_robot_ctrl.bat [PORT_MBOT]   (defaut COM17)
cd /d "%~dp0"
set PORT=%1
if "%PORT%"=="" set PORT=COM17
python mbot-motor-control.py %PORT%
pause
