
@echo off
title Sistema de Monitoramento de Pausas e Ligacoes

cd /d "C:\Users\kaua.jesus\Projetos\monitoramento_pausas"

echo ==========================================
echo   MONITORAMENTO DE PAUSAS E LIGACOES
echo ==========================================
echo.

if not exist "venv\Scripts\python.exe" (
    echo ERRO: Ambiente virtual nao encontrado.
    pause
    exit /b 1
)

set "TEAMS_WEBHOOK_URL=https://default42cb5c2368ef405cb2d6e268013254.a8.environment.api.powerplatform.com:443/powerautomate/automations/direct/cu/03/workflows/b66220ebabca42da89548b23626297db/triggers/manual/paths/invoke?api-version=1&sp=%%2Ftriggers%%2Fmanual%%2Frun&sv=1.0&sig=_A2JAF_2UPcAGEiD5ZSgQdAXOBNRC76MeIXnCaxFqIg"

echo %TEAMS_WEBHOOK_URL%

echo Iniciando o monitoramento...
echo.



venv\Scripts\python.exe app.py

echo.
echo O sistema foi encerrado.
pause
