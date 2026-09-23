@echo off
chcp 65001 >nul
echo ======================================================
echo   Отключение автоматического расписания Kaspi
echo ======================================================
echo.

schtasks /delete /tn "Kaspi_Daily_Morning" /f
schtasks /delete /tn "Kaspi_Daily_Evening" /f

echo.
echo Задачи Kaspi_Daily_Morning и Kaspi_Daily_Evening успешно удалены.
pause
