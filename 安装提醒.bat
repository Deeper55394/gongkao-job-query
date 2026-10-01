@echo off
REM ============================================================
REM  Install the daily "new position table" reminder task.
REM  ASCII-only on purpose: cmd.exe mis-parses UTF-8 batch files
REM  containing Chinese text. All Chinese messages come from
REM  tools\manage_reminder.ps1 (saved as UTF-8 with BOM).
REM ============================================================
cd /d "%~dp0"
title Install reminder

set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" set "PS=powershell"

"%PS%" -NoProfile -ExecutionPolicy Bypass -File "tools\manage_reminder.ps1" -Action install %*
echo.
echo Press any key to close...
pause >nul
