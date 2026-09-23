@echo off
rem Сборка автономного исполняемого файла через PyInstaller
chcp 65001 > nul
echo Сборка приложения...
pyinstaller --noconfirm --onedir --windowed --name "GrantsManagement" ^
    --add-data "databases/grants.db;databases" ^
    --add-data "src/ui/main_window.ui;src/ui" ^
    src/main.py
echo Завершено. Исполняемый файл в dist\GrantsManagement\GrantsManagement.exe
