@echo off
rem ======================================================================
rem  Claude work Max - MULTI instance launcher (3ds Max 2014)
rem  MaxBridge ports 9878-9899 = Claude Max.  9877 = user's Max (never used here).
rem  The existing Max_Claude_9878.bat is left as it is.
rem
rem    Max_Claude_multi.bat              (double-click) asks how many windows to open, then starts that many
rem                                      Enter with no number = 1
rem    Max_Claude_multi.bat 3            start 3 Claude Max (next free ports, 1-20)
rem    Max_Claude_multi.bat 9880         start 1 on port 9880 (9878-9899 only)
rem    drop a .max file on this bat      start 1 Claude Max with that file
rem    Max_Claude_multi.bat 4 tile       start 4 and arrange them in a grid (2x2). Needs Max_Claude_tile.ps1 next to this bat
rem    Max_Claude_multi.bat tile         arrange the Claude Max windows that are already running
rem    Max_Claude_multi.bat list         show which ports are in use
rem
rem  Wait until the previous Max has finished starting before running this
rem  again: a Max that is still loading has not opened its port yet.
rem ======================================================================
setlocal EnableDelayedExpansion
set "MAXEXE=C:\Program Files\Autodesk\3ds Max 2014\3dsmax.exe"
rem Claude Max uses its OWN settings (UI, hotkeys, window size) so it never overwrites the user's Max settings on exit
set "CLAUDEINI=C:\claude\max_claude_profile\3dsmax_claude.ini"
rem If Max is installed elsewhere, Claude_Max_setup writes the path to maxexe.txt next to the ini
if exist "C:\claude\max_claude_profile\maxexe.txt" set /p MAXEXE=<"C:\claude\max_claude_profile\maxexe.txt"
set "BASE=9878"
set "LAST=9899"
set "COUNT=1"
set "WANT="
set "FILE="
set "TILE=0"
set "INTER=0"
set "ASSIGNED="

if not exist "%CLAUDEINI%" (
  echo [ERROR] Claude Max settings file not found: %CLAUDEINI%
  echo Without it Claude Max would share and overwrite the user's hotkeys/UI. Not starting.
  pause
  exit /b 1
)
if not exist "%MAXEXE%" (
  echo [ERROR] 3dsmax.exe not found: %MAXEXE%
  pause
  exit /b 1
)

set "ARG=%~1"
if not defined ARG (
  echo.
  echo Claude Max windows - ports in use now:
  set "ANY=0"
  for /l %%P in (9877,1,%LAST%) do (
    call :isbusy %%P
    if "!BUSY!"=="1" ( echo   %%P  in use & set "ANY=1" )
  )
  if "!ANY!"=="0" echo   none
  echo.
  set "INTER=1"
  set /p "ARG=How many Claude Max windows to open? (1-20, Enter = 1, list = show ports only): "
)
if not defined ARG set "ARG=1"
if /i "%ARG%"=="list" goto list
if /i "%ARG%"=="tile" goto tileonly
if /i "%~2"=="tile" set "TILE=1"
if exist "%ARG%" (
  set "FILE=%ARG%"
  goto go
)
set /a NUM=0
set /a NUM=%ARG% >nul 2>&1
if !NUM! GEQ %BASE% goto setwant
if !NUM! GEQ 1 if !NUM! LEQ 20 (
  set "COUNT=!NUM!"
  goto go
)
goto usage

:setwant
set "WANT=!NUM!"
if !WANT! GTR %LAST% goto badport

:go
if "!INTER!"=="1" if !COUNT! GTR 1 (
  set "T="
  set /p "T=Arrange the windows in a grid (2x2 etc.)? (Y/N, Enter = Y): "
  if /i not "!T!"=="N" set "TILE=1"
)
if defined WANT (
  call :isbusy !WANT!
  if "!BUSY!"=="1" (
    echo [SKIP] port !WANT! is already in use.
    pause
    exit /b 1
  )
  call :launch !WANT!
  goto done
)
if defined FILE set "COUNT=1"
set /a STARTED=0
for /l %%P in (%BASE%,1,%LAST%) do (
  if !STARTED! LSS %COUNT% (
    call :isbusy %%P
    if "!BUSY!"=="0" (
      call :launch %%P
      set /a STARTED+=1
      if %COUNT% GTR 1 timeout /t 3 >nul
    )
  )
)
if !STARTED! LSS %COUNT% echo [WARN] only !STARTED! of %COUNT% started - no free port left in %BASE%-%LAST%.

:done
if defined ASSIGNED (
  if exist "%~dp0Max_Claude_tile.ps1" (
    set "NT=-NoTile"
    if "!TILE!"=="1" set "NT="
    echo Waiting for the windows to finish starting ^(up to 4 min^), then closing the Welcome Screen...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Max_Claude_tile.ps1" -Ports "!ASSIGNED!" !NT!
  ) else echo [WARN] Max_Claude_tile.ps1 not found next to this bat - Welcome Screen not closed, not arranged.
)
echo.
echo Port 9877 is the user's Max and is never touched. "Max_Claude_multi.bat list" shows used ports.
timeout /t 5 >nul
exit /b 0

:tileonly
if not exist "%~dp0Max_Claude_tile.ps1" (
  echo [ERROR] Max_Claude_tile.ps1 not found next to this bat.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Max_Claude_tile.ps1"
timeout /t 5 >nul
exit /b 0

:list
echo MaxBridge ports in use (9877 = user's Max, 9878-%LAST% = Claude Max):
for /l %%P in (9877,1,%LAST%) do (
  call :isbusy %%P
  if "!BUSY!"=="1" echo   %%P  in use
)
pause
exit /b 0

:isbusy
set "BUSY=0"
netstat -ano -p tcp | findstr /r /c:":%~1 .*LISTENING" >nul && set "BUSY=1"
exit /b 0

:launch
echo [START] Claude Max on port %~1
set "MAXBRIDGE_PORT=%~1"
set "ASSIGNED=!ASSIGNED!%~1,"
if defined FILE (
  start "" /min "%MAXEXE%" /Language=ENU -i "%CLAUDEINI%" "%FILE%"
) else (
  start "" /min "%MAXEXE%" /Language=ENU -i "%CLAUDEINI%"
)
set "MAXBRIDGE_PORT="
exit /b 0

:usage
echo Usage: Max_Claude_multi.bat [count 1-20 [tile] ^| port 9878-9899 ^| file.max ^| tile ^| list]
pause
exit /b 1

:badport
echo [ERROR] port must be %BASE%-%LAST% (9877 is the user's Max).
pause
exit /b 1
