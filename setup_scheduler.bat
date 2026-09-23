@echo off
chcp 65001 >nul
echo ======================================================
echo   Установка автоматического расписания публикаций Kaspi
echo   (Утро: 10:00, Вечер: 19:00 — по 1 товару на нишу)
echo ======================================================
echo.

set SCRIPT_DIR=%~dp0
set VBS_TARGET=%SCRIPT_DIR%run_hidden.vbs

echo [1/2] Создание утренней задачи в Планировщике Windows (10:00)...
schtasks /create /tn "Kaspi_Daily_Morning" /tr "wscript.exe %VBS_TARGET%" /sc daily /st 10:00 /f
if %ERRORLEVEL% NEQ 0 (
    echo [ОШИБКА] Не удалось создать утреннюю задачу. Запустите файл от имени Администратора.
) else (
    echo   [OK] Утренняя задача успешно создана!
)

echo.
echo [2/2] Создание вечерней задачи в Планировщике Windows (19:00)...
schtasks /create /tn "Kaspi_Daily_Evening" /tr "wscript.exe %VBS_TARGET%" /sc daily /st 19:00 /f
if %ERRORLEVEL% NEQ 0 (
    echo [ОШИБКА] Не удалось создать вечернюю задачу. Запустите файл от имени Администратора.
) else (
    echo   [OK] Вечерняя задача успешно создана!
)

echo.
echo [3/3] Настройка работы от батареи и наверстывания пропущенных запусков...
powershell -NoProfile -Command "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -WakeToRun; Set-ScheduledTask -TaskName 'Kaspi_Daily_Morning' -Settings $s; Set-ScheduledTask -TaskName 'Kaspi_Daily_Evening' -Settings $s" >nul 2>&1
echo   [OK] Включена работа от батареи и автозапуск при пробуждении!

echo.
echo ======================================================
echo Готово! Теперь бот будет автоматически:
echo  1. В 10:00 и 19:00 проверять товары
echo  2. Пополнять банк с Kaspi, если товаров мало
echo  3. Синхронизировать в Google Таблицу
echo  4. Публиковать по 1 товару в каждую нишу WhatsApp
echo  5. Сразу стирать все временные файлы (кэш = 0 Мб)
echo ======================================================
pause
