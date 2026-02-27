@echo off
REM =============================================================================
REM Adaptive Crypto Bot - Script de Automação Diária (Versão Avançada)
REM =============================================================================
REM Este script executa o bot de rebalanceamento adaptativo com monitoramento completo
REM Inclui: logging detalhado, notificações, backup de logs, estatísticas
REM =============================================================================

setlocal enabledelayedexpansion

REM Configurações
set "SCRIPT_DIR=%~dp0"
set "LOG_DIR=%SCRIPT_DIR%logs"
set "BACKUP_DIR=%LOG_DIR%\backup"
set "DATE_STAMP=%date:~-4,4%-%date:~-10,2%-%date:~-7,2%"
set "TIME_STAMP=%time:~0,2%-%time:~3,2%-%time:~6,2%"
set "TIME_STAMP=%TIME_STAMP: =0%"
set "LOG_FILE=%LOG_DIR%\adaptive_bot_%DATE_STAMP%.log"
set "DETAILED_LOG=%LOG_DIR%\adaptive_bot_detailed_%DATE_STAMP%_%TIME_STAMP%.log"
set "PYTHON_CMD=uv run python"
set "ADAPTIVE_SCRIPT=adaptive_bot.py"
set "MAX_LOG_SIZE=10485760"  REM 10MB em bytes
set "MAX_LOG_AGE=30"         REM dias

REM Criar diretórios necessários
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

echo ============================================================================= >> "%LOG_FILE%" 2>nul
echo [ADAPTIVE BOT AVANÇADO] Iniciado em %date% %time% >> "%LOG_FILE%" 2>nul
echo ============================================================================= >> "%LOG_FILE%" 2>nul

REM Função para verificar espaço em disco
for /f "tokens=3" %%a in ('dir /-c "%SCRIPT_DIR%" ^| findstr /c:"bytes free"') do set "DISK_SPACE=%%a"
if %DISK_SPACE% LSS 1073741824 (
    echo [AVISO] Espaço em disco baixo: %DISK_SPACE% bytes livres >> "%LOG_FILE%" 2>nul
    echo [AVISO] Considerar limpeza de logs antigos >> "%LOG_FILE%" 2>nul
)

REM Limpeza de logs antigos
echo [INFO] Limpando logs antigos (>%MAX_LOG_AGE% dias)... >> "%LOG_FILE%" 2>nul
forfiles /p "%LOG_DIR%" /m "*.log" /d -%MAX_LOG_AGE% /c "cmd /c del @path" 2>nul

REM Backup de log anterior se existir e for grande
if exist "%LOG_FILE%" (
    for %%A in ("%LOG_FILE%") do set "LOG_SIZE=%%~zA"
    if !LOG_SIZE! GTR %MAX_LOG_SIZE% (
        echo [INFO] Fazendo backup do log anterior (tamanho: !LOG_SIZE! bytes) >> "%LOG_FILE%" 2>nul
        copy "%LOG_FILE%" "%BACKUP_DIR%\adaptive_bot_%DATE_STAMP%_backup.log" >nul 2>&1
    )
)

REM Mudar para o diretório do script
cd /d "%SCRIPT_DIR%"

echo [INFO] === CONFIGURAÇÕES DA EXECUÇÃO === >> "%LOG_FILE%" 2>nul
echo [INFO] Diretório: %SCRIPT_DIR% >> "%LOG_FILE%" 2>nul
echo [INFO] Log principal: %LOG_FILE% >> "%LOG_FILE%" 2>nul
echo [INFO] Log detalhado: %DETAILED_LOG% >> "%LOG_FILE%" 2>nul
echo [INFO] Espaço em disco: %DISK_SPACE% bytes livres >> "%LOG_FILE%" 2>nul

REM Verificações de pré-execução
echo [INFO] Verificando dependências... >> "%LOG_FILE%" 2>nul

REM Verificar Python/UV
%PYTHON_CMD% --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO CRÍTICO] Python/UV não encontrado! >> "%LOG_FILE%" 2>nul
    echo [ERRO] Certifique-se de que UV está instalado >> "%LOG_FILE%" 2>nul
    goto :error_handler
)

REM Verificar script
if not exist "%ADAPTIVE_SCRIPT%" (
    echo [ERRO CRÍTICO] Script não encontrado: %ADAPTIVE_SCRIPT% >> "%LOG_FILE%" 2>nul
    goto :error_handler
)

REM Verificar arquivos de configuração
if not exist "adaptive_strategy.py" (
    echo [ERRO] Módulo adaptive_strategy.py não encontrado >> "%LOG_FILE%" 2>nul
    goto :error_handler
)

if not exist "sentiment_history.py" (
    echo [AVISO] Módulo sentiment_history.py não encontrado >> "%LOG_FILE%" 2>nul
    echo [INFO] Histórico de sentimentos será limitado >> "%LOG_FILE%" 2>nul
)

echo [INFO] Todas as dependências verificadas com sucesso >> "%LOG_FILE%" 2>nul

REM Coletar informações do sistema
echo [INFO] === INFORMAÇÕES DO SISTEMA === >> "%LOG_FILE%" 2>nul
echo [INFO] Data: %date% >> "%LOG_FILE%" 2>nul
echo [INFO] Hora: %time% >> "%LOG_FILE%" 2>nul

REM Obter versão do Python
for /f "tokens=*" %%i in ('%PYTHON_CMD% --version 2^>^&1') do set "PYTHON_VERSION=%%i"
echo [INFO] Python: %PYTHON_VERSION% >> "%LOG_FILE%" 2>nul

REM Obter informações de memória (simplificado)
echo [INFO] Verificando recursos do sistema... >> "%LOG_FILE%" 2>nul

REM Executar o bot adaptativo
echo [INFO] === EXECUÇÃO DO ADAPTIVE BOT === >> "%LOG_FILE%" 2>nul
echo [INFO] Iniciando execução... >> "%LOG_FILE%" 2>nul
echo [INFO] Hora de início: %time% >> "%LOG_FILE%" 2>nul

REM Redirecionar saída completa para log detalhado
echo ===== DETALHES DA EXECUÇÃO ===== > "%DETAILED_LOG%" 2>nul
echo Iniciado em %date% %time% >> "%DETAILED_LOG%" 2>nul
echo ================================= >> "%DETAILED_LOG%" 2>nul

%PYTHON_CMD% %ADAPTIVE_SCRIPT% >> "%DETAILED_LOG%" 2>&1
set "EXIT_CODE=%errorlevel%"

echo [INFO] Hora de término: %time% >> "%LOG_FILE%" 2>nul
echo [INFO] Código de saída: %EXIT_CODE% >> "%LOG_FILE%" 2>nul

REM Análise detalhada do resultado
if %EXIT_CODE% equ 0 (
    echo [SUCESSO] Adaptive Bot executado com sucesso! >> "%LOG_FILE%" 2>nul
    
    REM Tentar extrair informações do log detalhado
    echo [INFO] Analisando resultados... >> "%LOG_FILE%" 2>nul
    
    REM Procurar por informações de sentimento no log
    findstr /i "sentimento\|fear\|greed\|BTC\|ETH" "%DETAILED_LOG%" >nul 2>&1
    if %errorlevel% equ 0 (
        echo [INFO] Informações de mercado detectadas no log >> "%LOG_FILE%" 2>nul
    )
    
    REM Procurar por trades executados
    findstr /i "trades\|sell\|buy\|order" "%DETAILED_LOG%" >nul 2>&1
    if %errorlevel% equ 0 (
        echo [INFO] Movimentação de ativos detectada >> "%LOG_FILE%" 2>nul
    )
    
    goto :success_handler
) else (
    echo [ERRO] Adaptive Bot falhou com código: %EXIT_CODE% >> "%LOG_FILE%" 2>nul
    goto :error_handler
)

:success_handler
echo [INFO] === ESTATÍSTICAS FINAIS === >> "%LOG_FILE%" 2>nul

REM Calcular tempo de execução (simplificado)
echo [INFO] Execução concluída com código %EXIT_CODE% >> "%LOG_FILE%" 2>nul
echo [INFO] Verifique %DETAILED_LOG% para detalhes completos >> "%LOG_FILE%" 2>nul

REM Verificar se há alertas importantes no log
echo [INFO] Verificando alertas... >> "%LOG_FILE%" 2>nul
findstr /i "aviso\|warning\|alerta\|cuidado" "%DETAILED_LOG%" >nul 2>&1
if %errorlevel% equ 0 (
    echo [AVISO] Foram detectados alertas durante a execução >> "%LOG_FILE%" 2>nul
    echo [INFO] Revise o log detalhado para mais informações >> "%LOG_FILE%" 2>nul
)

goto :finalize

:error_handler
echo [ERRO] === ANÁLISE DE ERRO === >> "%LOG_FILE%" 2>nul
echo [ERRO] Código de falha: %EXIT_CODE% >> "%LOG_FILE%" 2>nul

REM Tentar identificar o tipo de erro
if %EXIT_CODE% equ 1 (
    echo [ERRO] Erro genérico - verifique configurações e conectividade >> "%LOG_FILE%" 2>nul
) else if %EXIT_CODE% equ 2 (
    echo [ERRO] Erro de configuração ou parâmetros inválidos >> "%LOG_FILE%" 2>nul
) else (
    echo [ERRO] Código de erro não documentado: %EXIT_CODE% >> "%LOG_FILE%" 2>nul
)

echo [ERRO] Verifique os seguintes itens: >> "%LOG_FILE%" 2>nul
echo [ERRO] 1. Conexão com internet >> "%LOG_FILE%" 2>nul
echo [ERRO] 2. Chaves API da Binance >> "%LOG_FILE%" 2>nul
echo [ERRO] 3. Configurações do ambiente (.env) >> "%LOG_FILE%" 2>nul
echo [ERRO] 4. Logs detalhados em: %DETAILED_LOG% >> "%LOG_FILE%" 2>nul

goto :finalize

:finalize
echo ============================================================================= >> "%LOG_FILE%" 2>nul
echo [ADAPTIVE BOT AVANÇADO] Finalizado em %date% %time% >> "%LOG_FILE%" 2>nul
echo ============================================================================= >> "%LOG_FILE%" 2>nul

REM Mensagem final para o console e para o agendador de tarefas
if %EXIT_CODE% equ 0 (
    echo ✅ Adaptive Bot executado com sucesso! 
    echo 📊 Verifique %LOG_FILE% para resumo e %DETAILED_LOG% para detalhes
) else (
    echo ❌ Adaptive Bot falhou! 
    echo 📋 Verifique %LOG_FILE% e %DETAILED_LOG% para diagnosticar
)

REM Informações úteis para o próximo agendamento
echo. 
echo 📅 Próxima execução recomendada: 6-12 horas
echo 🔧 Para configurar tarefa agendada: Task Scheduler ^> Criar Tarefa Básica
echo 📁 Logs salvos em: %LOG_DIR%

exit /b %EXIT_CODE%