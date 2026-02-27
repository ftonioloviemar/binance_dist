@echo off
REM =============================================================================
REM Adaptive Crypto Bot - Script de Automação Diária
REM =============================================================================
REM Define encoding UTF-8 para caracteres especiais
chcp 65001 >nul 2>&1
REM Este script executa o bot de rebalanceamento adaptativo diariamente
REM Autor: Sistema Automatizado
REM Versão: 1.0
REM =============================================================================

setlocal enabledelayedexpansion

REM Configurações
set "SCRIPT_DIR=%~dp0"
set "LOG_DIR=%SCRIPT_DIR%logs"
set "LOG_FILE=%LOG_DIR%\adaptive_bot_%date:~-4,4%%date:~-10,2%%date:~-7,2%.log"
set "PYTHON_CMD=uv run python"
set "ADAPTIVE_SCRIPT=adaptive_bot_windows.py"

REM Criar diretório de logs se não existir
if not exist "%LOG_DIR%" (
    mkdir "%LOG_DIR%"
    echo [INFO] Diretório de logs criado: %LOG_DIR% >> "%LOG_FILE%" 2>nul
)

REM Header do log
echo ============================================================================= >> "%LOG_FILE%" 2>nul
echo [ADAPTIVE BOT] Execução iniciada em %date% %time% >> "%LOG_FILE%" 2>nul
echo ============================================================================= >> "%LOG_FILE%" 2>nul

REM Mudar para o diretório do script
cd /d "%SCRIPT_DIR%"

echo [INFO] Diretório de trabalho: %SCRIPT_DIR% >> "%LOG_FILE%" 2>nul
echo [INFO] Python command: %PYTHON_CMD% >> "%LOG_FILE%" 2>nul
echo [INFO] Script adaptativo: %ADAPTIVE_SCRIPT% >> "%LOG_FILE%" 2>nul

REM Verificar se o script existe
if not exist "%ADAPTIVE_SCRIPT%" (
    echo [ERRO] Script adaptativo não encontrado: %ADAPTIVE_SCRIPT% >> "%LOG_FILE%" 2>nul
    echo [ERRO] Certifique-se de que o arquivo existe no diretório: %SCRIPT_DIR% >> "%LOG_FILE%" 2>nul
    exit /b 1
)

REM Verificar ambiente Python
echo [INFO] Verificando ambiente Python... >> "%LOG_FILE%" 2>nul
%PYTHON_CMD% --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Python/UV não encontrado ou não funcional >> "%LOG_FILE%" 2>nul
    echo [ERRO] Certifique-se de que UV está instalado e no PATH >> "%LOG_FILE%" 2>nul
    exit /b 1
)

echo [INFO] Ambiente Python verificado com sucesso >> "%LOG_FILE%" 2>nul

REM Executar o bot adaptativo
echo [INFO] Iniciando execução do Adaptive Bot... >> "%LOG_FILE%" 2>nul
echo [INFO] Horário de início: %time% >> "%LOG_FILE%" 2>nul

%PYTHON_CMD% %ADAPTIVE_SCRIPT% >> "%LOG_FILE%" 2>&1
set "EXIT_CODE=%errorlevel%"

echo [INFO] Horário de término: %time% >> "%LOG_FILE%" 2>nul
echo [INFO] Código de saída: %EXIT_CODE% >> "%LOG_FILE%" 2>nul

REM Análise do resultado
if %EXIT_CODE% equ 0 (
    echo [SUCESSO] Adaptive Bot executado com sucesso! >> "%LOG_FILE%" 2>nul
    echo [INFO] Verifique o arquivo de log principal para detalhes da execução >> "%LOG_FILE%" 2>nul
) else (
    echo [ERRO] Adaptive Bot falhou com código: %EXIT_CODE% >> "%LOG_FILE%" 2>nul
    echo [ERRO] Verifique os logs para diagnosticar o problema >> "%LOG_FILE%" 2>nul
)

REM Estatísticas finais
echo ============================================================================= >> "%LOG_FILE%" 2>nul
echo [ADAPTIVE BOT] Execução finalizada em %date% %time% >> "%LOG_FILE%" 2>nul
echo ============================================================================= >> "%LOG_FILE%" 2>nul

REM Mensagem final para o console (útil para agendador de tarefas)
if %EXIT_CODE% equ 0 (
    echo ✅ Adaptive Bot executado com sucesso! Verifique %LOG_FILE% para detalhes.
) else (
    echo ❌ Adaptive Bot falhou! Verifique %LOG_FILE% para diagnosticar.
)

exit /b %EXIT_CODE%