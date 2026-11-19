@echo off
REM TOS_RigTools INSTALL / UPDATE - close 3ds Max and Blender first
title TOS_RigTools INSTALL / UPDATE - close 3ds Max and Blender first
echo TOS_RigTools INSTALL / UPDATE - close 3ds Max and Blender first
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_setup\tos_setup.ps1" -Mode Install
echo.
pause
