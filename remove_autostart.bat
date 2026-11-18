@echo off
rem Removes RektaPrint from Windows Startup
powershell -NoProfile -Command "Remove-Item ([Environment]::GetFolderPath('Startup')+'\RektaPrint.lnk') -ErrorAction SilentlyContinue"
echo.
echo RektaPrint auto-start removed.
echo.
pause
