@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 (
  echo.
  echo LongBook could not start. See the error above and README.md.
  pause
  exit /b 1
)
