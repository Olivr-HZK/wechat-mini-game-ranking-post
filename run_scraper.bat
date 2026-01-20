@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在运行爬虫脚本...
if "%1"=="--debug" (
    python scrape_gravity.py --debug
) else if "%1"=="--headless" (
    python scrape_gravity.py --headless
) else (
    python scrape_gravity.py
)
pause
