@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo جاري تشغيل البوتات...
python bot.py
pause