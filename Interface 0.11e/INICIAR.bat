@echo off
setlocal
cd /d "%~dp0"
title Higienizador 2.0 - ETAPA 3 INTERFACE 0.11b
if not exist ".venv\Scripts\python.exe" (
    echo Execute INSTALAR.bat primeiro.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" higienizador_interface_0_11b.py
if errorlevel 1 (
    echo O programa apresentou erro. Copie a mensagem acima.
    pause
)
