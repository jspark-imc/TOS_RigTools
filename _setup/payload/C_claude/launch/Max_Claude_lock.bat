@echo off
rem Claude Max window reservation. Same arguments as Max_Claude_lock.ps1 (see the top of that file).
rem   Max_Claude_lock.bat                        (double-click) show who holds which Claude Max window
rem   Max_Claude_lock.bat claim -Owner eye       reserve a window (starts a new Claude Max if all are held)
rem   Max_Claude_lock.bat release -Owner eye -Port 9879 [-Close]
rem The user's Max (9877) is never touched.
setlocal
if "%~1"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Max_Claude_lock.ps1" status
  pause
  exit /b 0
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Max_Claude_lock.ps1" %*
exit /b %errorlevel%
