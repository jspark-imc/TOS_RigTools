@echo off
REM TOS_RigTools INSTALL_ALL - one double-click: install/update + check. Close 3ds Max and Blender first.
REM TOS_RigTools 1.0 (based on GE Rig Tools installer v5.5, same install steps). Every changed file is backed up first
REM      (C:\Users\<name>\tos_rig_backup\<date_time>\), copied, then compared by hash. Undo = 3_RESTORE.bat.
REM TOS_RigTools uses its own names, so MTOS_RigTools and GE Rig Tools can stay in the same Max: this installer leaves their files alone.
REM Parts: the same as last time (asks only on the first install). 1~3 bat files still work the same.
REM TOS_TEST_ARGS is only for testing (for example: -Root C:\test -Yes). Leave it empty.
title TOS_RigTools INSTALL_ALL - close 3ds Max and Blender first
echo TOS_RigTools INSTALL_ALL - install/update and check
echo Close 3ds Max and Blender first.
echo.
echo [0] checking the bundle files against _setup\manifest.txt ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_setup\make_manifest.ps1" -Check
if errorlevel 1 (
  echo [bat] the bundle is damaged or changed - nothing was installed. Unzip TOS_RigTools_v1.0.zip again.
  if not defined TOS_NOPAUSE pause
  exit /b 3
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_setup\tos_setup.ps1" -Mode Install -Parts AUTO %TOS_TEST_ARGS%
set TOS_RC=%ERRORLEVEL%
echo.
if "%TOS_RC%"=="0" (echo [bat] finished: OK) else (echo [bat] finished with code %TOS_RC% - see the red lines above)
if not defined TOS_NOPAUSE pause
exit /b %TOS_RC%
