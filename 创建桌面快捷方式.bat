@echo off
REM ============================================================
REM  Create a desktop shortcut for this tool.
REM  ASCII-only on purpose: cmd.exe mis-parses UTF-8 batch files
REM  containing Chinese text. All Chinese messages come from
REM  tools\make_shortcut.ps1 (saved as UTF-8 with BOM).
REM
REM  Usage:
REM     double-click                 -> shortcut for the launcher
REM     (this file) update    -> shortcut for the data updater
REM     (this file) both      -> both shortcuts
REM ============================================================
cd /d "%~dp0"
title Create desktop shortcut

set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" set "PS=powershell"

"%PS%" -NoProfile -ExecutionPolicy Bypass -File "tools\make_shortcut.ps1" %*
if errorlevel 1 (
  echo.
  echo [x] Failed. Please read the message above.
  echo.
  pause
)
