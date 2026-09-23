@echo off
rem Компиляция формы Qt Designer в Python-код
chcp 65001 > nul
echo Компиляция main_window.ui -> main_window_ui.py...
pyuic6 src\ui\main_window.ui -o src\ui\main_window_ui.py
if %ERRORLEVEL% EQU 0 (
    echo Готово: src\ui\main_window_ui.py успешно сформирован.
) else (
    echo Ошибка при компиляции UI!
)
