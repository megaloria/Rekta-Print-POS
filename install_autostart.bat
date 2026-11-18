@echo off
rem Adds RektaPrint to Windows Startup for the current user
cd /d "%~dp0"
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup')+'\RektaPrint.lnk'); $s.TargetPath='%~dp0start_hidden.vbs'; $s.WorkingDirectory='%~dp0'; $s.Save()"
echo.
echo Done! RektaPrint will now start automatically when you log in to Windows.
echo.
pause
