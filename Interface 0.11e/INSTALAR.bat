@echo off
setlocal
cd /d "%~dp0"
title Higienizador 2.0 - Instalar previa Etapa 3
if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>&1
if not errorlevel 1 (
    py -3 -m venv ".venv"
) else (
    python -m venv ".venv"
)
if errorlevel 1 goto falha
:install
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto falha
".venv\Scripts\python.exe" -c "from PySide6.QtWebEngineWidgets import QWebEngineView; print('Qt WebEngine instalado.')"
if errorlevel 1 goto falha
echo INSTALACAO CONCLUIDA.
pause
exit /b 0
:falha
echo INSTALACAO FALHOU. Confira o Python e a conexao com a internet.
pause
exit /b 1
