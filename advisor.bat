@echo off
REM Inicia o advisor e deixa rodando enquanto voce joga.
REM Ele observa o champ select, imprime a recomendacao a cada mudanca no draft
REM e aplica a pagina de runas + os feiticos no client.
REM
REM Todas as opcoes ficam no config.toml. Argumentos extras ainda
REM funcionam e vencem o arquivo: advisor.bat --tier platinum

chcp 65001 >nul
title LoL Draft Advisor
cd /d "%~dp0"

REM Prefere o ambiente isolado do projeto. Assim o advisor usa exatamente as
REM mesmas dependencias dos testes, sem depender do PATH global do Windows.
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    where py >nul 2>&1
    if not errorlevel 1 (
        set "PY=py"
    ) else (
        set "PY=python"
    )
)

%PY% --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo Python nao encontrado. Instale de python.org e marque
    echo "Add Python to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

echo.
echo  LoL Draft Advisor
echo  -----------------
echo  Observando o champ select. Deixe esta janela aberta.
echo  Opcoes: config.toml
echo  Ctrl+C para parar.
echo.

%PY% -m advisor --vigiar %*

REM Sem o pause a janela fecharia junto com o erro e voce nao leria a mensagem.
echo.
echo  O advisor parou.
pause >nul

