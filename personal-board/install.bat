@echo off
REM Windows — двойной клик. Нужен Python 3.10+ с галочкой "Add Python to PATH".
cd /d "%~dp0"
echo Ставлю personal-board (Consilium)...
python install.py %*
echo.
pause
