@echo off
rem OtoClip launcher for Windows. Double-click to start.
cd /d "%~dp0"
title OtoClip

set "PY="
for %%P in ("py -3" "python" "python3") do (
  if not defined PY (
    %%~P -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=%%~P"
  )
)
if not defined PY goto :nopython

%PY% start.py
if errorlevel 1 pause
exit /b

:nopython
echo Python 3.10 or newer was not found.
echo Please install it from https://www.python.org/downloads/
echo and check "Add python.exe to PATH" in the installer, then run this file again.
pause
exit /b 1
