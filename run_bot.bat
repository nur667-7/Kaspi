@echo off
chcp 65001 >nul
title Kaspi Telegram Bot Controller
echo ====================================================
echo  Запуск Telegram-бота управления Kaspi...
echo ====================================================
cd /d "%~dp0"
python main.py bot
pause
