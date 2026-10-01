@echo off
REM ============================================================
REM  Deploy this project to your GitHub repository (for GitHub Pages).
REM  ASCII-only on purpose: cmd.exe mis-parses UTF-8 batch files
REM  containing Chinese text. All Chinese messages come from
REM  tools\deploy_github.ps1 (saved as UTF-8 with BOM).
REM
REM  Usage:
REM     double-click           -> interactive deploy
REM     (this file) -Check      -> only show status, change nothing
REM ============================================================
cd /d "%~dp0"
title Deploy to GitHub Pages

set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" set "PS=powershell"

"%PS%" -NoProfile -ExecutionPolicy Bypass -File "tools\deploy_github.ps1" %*

echo.
echo (Press any key to close this window)
pause >nul
