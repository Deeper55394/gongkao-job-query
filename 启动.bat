@echo off
REM ============================================================
REM  Launcher: start local server and open the tool in browser.
REM  This file is intentionally ASCII-only: cmd.exe mis-parses
REM  UTF-8 batch files containing Chinese text. All Chinese
REM  messages are printed by tools\serve.py instead.
REM
REM  Usage: double-click, or run with args:
REM     (launcher) --port 9000
REM     (launcher) --lan
REM ============================================================
cd /d "%~dp0"
title Gongkao Job Query - local server

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
  for /d %%D in ("C:\Python3*") do if exist "%%~fD\python.exe" set "PY=%%~fD\python.exe"
)

if not defined PY goto nopython

"%PY%" "tools\serve.py" %*
goto end

:nopython
echo.
echo [i] Python not found - opening index.html directly (offline mode).
echo     The page still works: it uses its built-in data and can export CSV.
echo     To auto-read the latest data.json, install Python 3.9+ :
echo     https://www.python.org/downloads/
echo.
start "" "index.html"
REM Keep this message visible for about 5 seconds, then close silently.
REM (ping is used instead of timeout because timeout fails when stdin is redirected.)
ping -n 6 127.0.0.1 >nul

:end
