@echo off
REM TOS_RigTools RESTORE - back to the state before the last install
title TOS_RigTools RESTORE - back to the state before the last install
echo TOS_RigTools RESTORE - back to the state before the last install
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_setup\tos_setup.ps1" -Mode Restore
echo.
pause
