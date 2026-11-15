@echo off
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 goto use_launcher

where python >nul 2>nul
if not errorlevel 1 goto use_python

echo Python 3.7 or newer is required. Install Python and enable "Add Python to PATH".
pause
exit /b 1

:use_launcher
py -3 app.py --serve
goto end

:use_python
python app.py --serve

:end
