@echo off
chcp 65001 >nul
title Бот «Карманные деньги по оценкам»
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)

if not exist "config.json" (
    if exist "config.example.json" (
        echo Файла config.json нет — копирую из config.example.json
        copy /y "config.example.json" "config.json" >nul
        echo Впиши в него bot_token от @BotFather и запусти снова.
        pause
        exit /b
    )
)

:loop
echo.
echo === Запускаю бота... ===
"%PY%" main.py
echo.
echo Бот остановился. Перезапуск через 10 секунд (закрой окно, чтобы выйти).
timeout /t 10 >nul
goto loop
