@echo off
setlocal
cd /d "%~dp0"
title Higienizador 1.9.14.6.7 - TESTE SOMENTE LEITURA
if not exist ".venv\Scripts\python.exe" (
 echo Execute INSTALAR.bat primeiro.
 pause
 exit /b 1
)
".venv\Scripts\python.exe" higienizador_1_9_14_6_7.py
if errorlevel 1 (
 echo Erro ao iniciar. Copie a mensagem acima.
 pause
)
