@echo off
REM ============================================================
REM  Update data: drag an official .xlsx/.xls position table onto
REM  this file. It runs tools\update_data.py (Chinese prompts).
REM  ASCII-only on purpose: cmd.exe mis-parses UTF-8 batch files
REM  containing Chinese text.
REM ============================================================
cd /d "%~dp0"
title Gongkao Job Query - update data

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

"%PY%" "tools\update_data.py" %*
goto end

:nopython
echo.
echo [x] Python not found. Please install Python 3.9+ and tick
echo     "Add python.exe to PATH", then drag the Excel file again.
echo     Download: https://www.python.org/downloads/
echo.
pause

:end
