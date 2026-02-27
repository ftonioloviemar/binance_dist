#!/usr/bin/env python3
"""
Script wrapper para executar o bot de rebalanceamento com estratégia adaptativa.
Este script automatiza a execução com base no sentimento de mercado atual.
Versão Windows com compatibilidade de encoding aprimorada.
"""

import subprocess
import sys
import logging
from datetime import datetime

# Configurar encoding UTF-8 para Windows
import os

os.environ["PYTHONIOENCODING"] = "utf-8"

# Configurar logging com encoding UTF-8 para Windows
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/adaptive_bot_execution.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# Emojis simplificados para Windows
EMOJIS = {
    "robot": "🤖" if sys.platform != "win32" else "[BOT]",
    "calendar": "📅" if sys.platform != "win32" else "[DATE]",
    "rocket": "🚀" if sys.platform != "win32" else "[START]",
    "warning": "⚠️" if sys.platform != "win32" else "[WARN]",
    "success": "✅" if sys.platform != "win32" else "[OK]",
    "party": "🎉" if sys.platform != "win32" else "[SUCCESS]",
    "chart": "📈" if sys.platform != "win32" else "[MARKET]",
    "refresh": "🔄" if sys.platform != "win32" else "[REPEAT]",
    "tip": "💡" if sys.platform != "win32" else "[TIP]",
    "sad": "😞" if sys.platform != "win32" else "[ERROR]",
}


def run_adaptive_rebalance(dry_run: bool = False) -> int:
    """
    Executa o rebalanceamento com estratégia adaptativa baseada no sentimento de mercado.

    Args:
        dry_run: Se True, executa em modo simulação sem trades reais

    Returns:
        Código de saída (0 = sucesso, 1 = erro)
    """
    logger.info(f"{EMOJIS['robot']} Iniciando Adaptive Rebalance Bot")
    logger.info(
        f"{EMOJIS['calendar']} Data/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    cmd = [
        sys.executable,
        "app.py",
        "rebalance",
        "--adaptive",  # Habilita estratégia adaptativa
        "--dry-run=false" if not dry_run else "--dry-run=true",
        "--recv-window",
        "10000",  # Timeout maior para estabilidade
    ]

    logger.info(f"{EMOJIS['rocket']} Executando comando: {' '.join(cmd)}")

    try:
        # Executar comando com encoding UTF-8
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
            errors="replace",  # Substituir caracteres problemáticos
        )

        # Processar saída
        if result.stdout:
            logger.info("📊 Saída do comando:")
            for line in result.stdout.split("\n"):
                if line.strip():
                    # Limpar caracteres de escape problemáticos
                    clean_line = line.replace("\u0001f4ca", "[ANALYSIS]")
                    clean_line = clean_line.replace("\u26a0\ufe0f", "[WARNING]")
                    clean_line = clean_line.replace("\u2699\ufe0f", "[SETTINGS]")
                    clean_line = clean_line.replace("\u0001f3af", "[TARGET]")
                    clean_line = clean_line.replace("\u0001f4c8", "[TREND]")
                    clean_line = clean_line.replace("\u0001f3ad", "[PROFILE]")
                    clean_line = clean_line.replace("\u0001f4cb", "[ALLOCATION]")
                    clean_line = clean_line.replace("\u0001f4a1", "[RATIONALE]")
                    clean_line = clean_line.replace("\u0001f389", "[SUCCESS]")
                    clean_line = clean_line.replace("\u0001f4c8", "[MARKET]")
                    clean_line = clean_line.replace("\u0001f504", "[REPEAT]")
                    logger.info(f"   {clean_line}")

        if result.stderr:
            logger.warning(f"{EMOJIS['warning']} Avisos/Logs:")
            for line in result.stderr.split("\n"):
                if line.strip():
                    clean_line = line.replace("\u0001f4ca", "[ANALYSIS]")
                    clean_line = clean_line.replace("\u26a0\ufe0f", "[WARNING]")
                    # etc...
                    logger.warning(f"   {clean_line}")

        logger.info(
            f"{EMOJIS['success']} Rebalanceamento adaptativo concluído com sucesso!"
        )
        return 0

    except subprocess.CalledProcessError as e:
        logger.error(f"{EMOJIS['sad']} Erro na execução do rebalanceamento: {e}")
        logger.error(f"   Código de saída: {e.returncode}")

        if e.stdout:
            logger.error("📊 Saída padrão:")
            for line in e.stdout.split("\n"):
                if line.strip():
                    logger.error(f"   {line}")

        if e.stderr:
            logger.error("📋 Erros:")
            for line in e.stderr.split("\n"):
                if line.strip():
                    logger.error(f"   {line}")

        return e.returncode

    except Exception as e:
        logger.error(f"{EMOJIS['sad']} Erro inesperado: {e}")
        return 1


def main():
    """Função principal do script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Adaptive Rebalance Bot - Estratégia baseada em sentimento de mercado"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Executar em modo simulação (sem trades reais)",
    )

    parser.add_argument(
        "--test", action="store_true", help="Executar modo teste (mesmo que --dry-run)"
    )

    args = parser.parse_args()

    # Se --test for especificado, ativa dry-run
    dry_run = args.dry_run or args.test

    if dry_run:
        logger.info(
            f"{EMOJIS['warning']} MODO SIMULAÇÃO ATIVADO - Nenhum trade real será executado"
        )

    # Executar rebalanceamento
    exit_code = run_adaptive_rebalance(dry_run=dry_run)

    # Mensagem final baseada no resultado
    if exit_code == 0:
        logger.info(f"{EMOJIS['party']} Bot adaptativo finalizado com sucesso!")
        logger.info(
            f"{EMOJIS['chart']} O sistema se ajustou automaticamente ao sentimento de mercado atual"
        )
        logger.info(
            f"{EMOJIS['refresh']} Próxima execução automática recomendada: 6-12 horas"
        )
    else:
        logger.error(f"{EMOJIS['sad']} Bot adaptativo falhou - verifique os logs acima")
        logger.info(
            f"{EMOJIS['tip']} Dica: Verifique conexão com Binance, chaves API e configurações"
        )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
