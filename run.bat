@echo off
rem Start Chartered Book on Windows. Double click this file.
rem To let a phone or tablet on the same wifi use it, add --lan to the lines below.
cd /d "%~dp0"
where python >nul 2>nul
if %errorlevel%==0 ( python start.py & goto end )
where py >nul 2>nul
if %errorlevel%==0 ( py -3 start.py & goto end )
echo Python 3 was not found on this computer.
echo Install it free from https://www.python.org/downloads/
echo During installation tick the box that says "Add Python to PATH".
pause
:end
