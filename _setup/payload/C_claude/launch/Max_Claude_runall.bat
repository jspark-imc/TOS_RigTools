@echo off
rem ======================================================================
rem  Run one MAXScript (.ms) in ALL running Claude Max windows at once.
rem  How to use (no typing needed):
rem    - drag a .ms file and drop it on this bat file, or
rem    - double-click this bat, drag the .ms file into the black window, press Enter
rem  Only Claude Max (ports 9878-9899) get it. The user's Max (9877) is never touched.
rem  Needs Max_Claude_runall.ps1 next to this bat.
rem ======================================================================
setlocal
set "MS=%~1"
if not defined MS (
  echo.
  echo Drag a .ms file into this window and press Enter.
  set /p "MS=Script: "
)
if not defined MS goto end
set MS=%MS:"=%
if not exist "%~dp0Max_Claude_runall.ps1" (
  echo [ERROR] Max_Claude_runall.ps1 not found next to this bat.
  goto end
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Max_Claude_runall.ps1" -Script "%MS%"
:end
echo.
pause
