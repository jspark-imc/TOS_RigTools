@echo off
REM Make a zip of this tool folder on the Desktop, to carry to another PC (home).
REM There: unzip anywhere (a new folder named with the version) -> INSTALL_ALL.bat. No renaming of old folders.
title MAKE_ZIP - TOS_RigTools
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_setup\make_zip.ps1"
set TOS_RC=%ERRORLEVEL%
echo.
if "%TOS_RC%"=="0" (echo [bat] finished: OK) else (echo [bat] finished with code %TOS_RC% - see the red lines above)
pause
exit /b %TOS_RC%
