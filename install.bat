@echo off
rem ============================================
rem  Голосовой ввод — установщик.
rem  Ставит Python (если нет), библиотеки,
rem  модель распознавания, ярлыки. Запускает.
rem ============================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
pause
