@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM Автоматический запуск сессии постинга Kaspi -> WhatsApp
C:\Users\NiTrOv15\AppData\Local\Programs\Python\Python313\python.exe daily_runner.py >> daily_run.log 2>&1
