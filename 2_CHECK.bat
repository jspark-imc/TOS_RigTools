@echo off
REM TOS_RigTools CHECK - open 3ds Max first to also test the connection
title TOS_RigTools CHECK - open 3ds Max first to also test the connection
echo TOS_RigTools CHECK - open 3ds Max first to also test the connection
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_setup\tos_setup.ps1" -Mode Check
echo.
pause
