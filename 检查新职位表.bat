@echo off
REM ============================================================
REM  Check whether the official NEW-cycle position tables are out.
REM  ASCII-only on purpose: cmd.exe mis-parses UTF-8 batch files
REM  containing Chinese text. Chinese messages come from the .py.
REM
REM  Usage:
REM     double-click            -> check only
REM     (this file) --auto-update -> check, and if found, update+push
REM ============================================================
cd /d "%~dp0"
title Check for new position tables

set "PY="
python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY (
  py -c "import sys" >nul 2>nul && set "PY=py"
)
if not defined PY (
  for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%~fD\python.exe" set "PY=%%~fD\python.exe"
)
if not defined PY (
  for /d %%D in ("%ProgramFiles%\Python3*") do if exist "%%~fD\python.exe" set "PY=%%~fD\python.exe"
)
if not defined PY (
  echo [x] Python not found. Install Python 3.9+ first.
  echo     https://www.python.org/downloads/
  pause
  exit /b 1
)

"%PY%" "tools\probe_new_cycle.py" %*
echo.
pause >nul
