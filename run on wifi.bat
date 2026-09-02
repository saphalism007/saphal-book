@echo off
rem Start Chartered Book and let phones, tablets and other computers on the
rem same wifi use it as well. The addresses to open are printed in this window.
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 ( python start.py --lan & goto end )
where py >nul 2>nul
if %errorlevel%==0 ( py -3 start.py --lan & goto end )
echo Python 3 was not found. Install it free from https://www.python.org/downloads/
pause
:end
