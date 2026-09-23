@echo off
chcp 65001 > nul
cd /d "%~dp0"
set PYTHONPATH=%cd%

echo ====================================================
echo  Запуск информационной системы СУБД (Вариант 7)
echo ====================================================
echo.

:: 1. Проверяем наличие Python в системе
where python >nul 2>nul
if errorlevel 1 (
    echo [ОШИБКА] Python не найден в системе!
    echo Установите Python 3.9+ с сайта python.org и поставьте галочку "Add to PATH".
    echo.
    pause
    exit /b 1
)

:: 2. Проверяем наличие необходимых библиотек
python -c "import PyQt6, pandas, openpyxl, xlrd" 2>nul
if errorlevel 1 (
    echo [ИНФО] Обнаружены неустановленные библиотеки.
    echo Запуск автоматической установки зависимостей...
    echo.
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [ОШИБКА] Не удалось установить библиотеки через pip.
        pause
        exit /b 1
    )
    echo.
    echo [УСПЕХ] Все библиотеки успешно установлены!
    echo.
)

:: 3. Запускаем главное окно программы
echo Запуск приложения...
python src\main.py

if errorlevel 1 (
    echo.
    echo [ОШИБКА] Приложение завершилось с ошибкой.
    pause
)
