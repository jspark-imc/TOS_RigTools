@echo off
rem ======================================================================
rem  Claude work Blender launcher
rem  MCP for Blender port 9866 = Claude Blender.  9876 = user's Blender (never touched here).
rem  Max Bridge in this Blender sends to Claude Max 9878 (MAXBRIDGE_PORT), not the user's Max 9877.
rem
rem    Blender_Claude.bat               start the Claude Blender (empty scene)
rem    drop a .blend file on this bat   start the Claude Blender with that file
rem ======================================================================
setlocal
set "BLENDEREXE=C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
set "PORTPY=%~dp0blender_claude_port.py"
set "CLAUDE_BLENDER_PORT=9866"
set "MAXBRIDGE_PORT=9878"

if not exist "%BLENDEREXE%" (
  echo [ERROR] blender.exe not found: %BLENDEREXE%
  pause
  exit /b 1
)
if not exist "%PORTPY%" (
  echo [ERROR] blender_claude_port.py not found next to this bat.
  pause
  exit /b 1
)
netstat -ano -p tcp | findstr /r /c:":%CLAUDE_BLENDER_PORT% .*LISTENING" >nul && (
  echo [SKIP] Claude Blender is already running on port %CLAUDE_BLENDER_PORT%.
  timeout /t 5 >nul
  exit /b 0
)

echo [START] Claude Blender on port %CLAUDE_BLENDER_PORT%  (user's Blender 9876 is not touched)
if "%~1"=="" (
  start "Claude Blender" "%BLENDEREXE%" --python "%PORTPY%"
) else (
  start "Claude Blender" "%BLENDEREXE%" "%~1" --python "%PORTPY%"
)
timeout /t 3 >nul
exit /b 0
