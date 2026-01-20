@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在运行调试脚本...
python debug_gravity_page.py
pause
