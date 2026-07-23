@echo off
setlocal
REM Windows launcher: use a real Python 3.10+ interpreter; never install software automatically.
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"
set "CONSILIUM_PYTHON="
set "CONSILIUM_EXIT=1"

py -3 -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>nul
if not errorlevel 1 set "CONSILIUM_PYTHON=py -3"

if not defined CONSILIUM_PYTHON (
  python -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>nul
  if not errorlevel 1 set "CONSILIUM_PYTHON=python"
)

if not defined CONSILIUM_PYTHON (
  echo Python 3.10+ was not found. Install it from https://www.python.org/downloads/ and run this launcher again.
  goto :done
)

echo Installing personal-board (Consilium)...
%CONSILIUM_PYTHON% install.py %*
set "CONSILIUM_EXIT=%ERRORLEVEL%"

:done
echo.
if not "%CONSILIUM_NO_PAUSE%"=="1" pause
exit /b %CONSILIUM_EXIT%
