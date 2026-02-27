#!/usr/bin/env python3
"""
Script wrapper para executar o bot de rebalanceamento com estratégia adaptativa.
Este script automatiza a execução com base no sentimento de mercado atual.
"""

import subprocess
import sys
import logging
from datetime import datetime

# Configurar encoding UTF-8 para Windows
import os

os.environ["PYTHONIOENCODING"] = "utf-8"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    encoding="utf-8",
)
logger = logging.getLogger(__name__)


# Função para garantir compatibilidade com Windows
def safe_print(text):
    """Imprime texto com tratamento de encoding para Windows"""
    try:
        print(text)
    except UnicodeEncodeError:
        # Fallback para caracteres ASCII
        print(text.encode("ascii", "replace").decode("ascii"))


def run_adaptive_rebalance(dry_run: bool = False) -> int:
    """
    Executa o rebalanceamento com estratégia adaptativa baseada no sentimento de mercado.

    Args:
        dry_run: Se True, executa em modo simulação sem trades reais

    Returns:
        Código de saída (0 = sucesso, 1 = erro)
    """
    logger.info("🤖 Iniciando Adaptive Rebalance Bot")
    logger.info(f"📅 Data/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    cmd = [
        sys.executable,
        "app.py",
        "rebalance",
        "--adaptive",  # Habilita estratégia adaptativa
        "--dry-run" if dry_run else "--dry-run=false",
        "--recv-window",
        "10000",  # Timeout maior para estabilidade
    ]

    logger.info(f"🚀 Executando comando: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        # Log da saída
        if result.stdout:
            logger.info("📊 Saída do comando:")
            for line in result.stdout.split("\n"):
                if line.strip():
                    logger.info(f"   {line}")

        if result.stderr:
            logger.warning("⚠️  Avisos/Logs:")
            for line in result.stderr.split("\n"):
                if line.strip():
                    logger.warning(f"   {line}")

        logger.info("✅ Rebalanceamento adaptativo concluído com sucesso!")
        return 0

    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Erro na execução do rebalanceamento: {e}")
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
        logger.error(f"❌ Erro inesperado: {e}")
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
        logger.info("🔬 MODO SIMULAÇÃO ATIVADO - Nenhum trade real será executado")

    # Executar rebalanceamento
    exit_code = run_adaptive_rebalance(dry_run=dry_run)

    # Mensagem final baseada no resultado
    if exit_code == 0:
        logger.info("🎉 Bot adaptativo finalizado com sucesso!")
        logger.info(
            "📈 O sistema se ajustou automaticamente ao sentimento de mercado atual"
        )
        logger.info("🔄 Próxima execução automática recomendada: 6-12 horas")
    else:
        logger.error("😞 Bot adaptativo falhou - verifique os logs acima")
        logger.info(
            "💡 Dica: Verifique conexão com Binance, chaves API e configurações"
        )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
