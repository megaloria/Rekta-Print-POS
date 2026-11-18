@echo off
rem Starts the RektaPrint server. Works from whatever folder this file is in.
cd /d "%~dp0"

rem Wait a bit so Windows, the network and the printers are ready
timeout /t 20 /nobreak >nul

rem Run the server and keep a log in case something goes wrong
python app.py >> rektaprint.log 2>&1
