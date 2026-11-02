@rem Discord Admin Bot — By @Zver1o7 (https://github.com/Zver1o7)
@echo off
cd /d "%~dp0"
py -3 bot.py 2>nul || python bot.py
pause
