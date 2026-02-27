from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class SentimentHistory:
    """Gerencia o histórico de sentimentos de mercado para transições inteligentes."""

    def __init__(self, history_file: str = "sentiment_history.json"):
        self.history_file = Path(history_file)
        self.history: Dict[str, Any] = {}
        self.load_history()

    def load_history(self) -> None:
        """Carrega o histórico de sentimentos do arquivo."""
        try:
            if self.history_file.exists():
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
                logger.info(
                    f"📚 Histórico de sentimentos carregado: {len(self.history)} registros"
                )
            else:
                logger.info(
                    "📄 Nenhum histórico de sentimentos encontrado - criando novo"
                )
                self.history = {}
        except Exception as e:
            logger.warning(f"⚠️  Erro ao carregar histórico: {e}. Criando novo.")
            self.history = {}

    def save_history(self) -> None:
        """Salva o histórico de sentimentos no arquivo."""
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
            logger.debug("💾 Histórico de sentimentos salvo")
        except Exception as e:
            logger.error(f"❌ Erro ao salvar histórico: {e}")

    def record_sentiment(
        self,
        sentiment: str,
        fear_greed_value: int,
        btc_change_24h: float,
        profile_used: str,
        rebalance_performed: bool,
    ) -> None:
        """Registra um novo sentimento de mercado."""
        timestamp = datetime.now().isoformat()

        entry = {
            "timestamp": timestamp,
            "sentiment": sentiment,
            "fear_greed_value": fear_greed_value,
            "btc_change_24h": btc_change_24h,
            "profile_used": profile_used,
            "rebalance_performed": rebalance_performed,
        }

        # Manter apenas os últimos 30 dias
        if "entries" not in self.history:
            self.history["entries"] = []

        self.history["entries"].append(entry)

        # Limpar entradas antigas (manter últimas 100)
        if len(self.history["entries"]) > 100:
            self.history["entries"] = self.history["entries"][-100:]

        # Atualizar último sentimento
        self.history["last_sentiment"] = {
            "sentiment": sentiment,
            "fear_greed_value": fear_greed_value,
            "timestamp": timestamp,
        }

        self.save_history()
        logger.info(f"📝 Sentimento registrado: {sentiment} ({fear_greed_value}/100)")

    def get_last_sentiment(self) -> Optional[Dict[str, Any]]:
        """Retorna o último sentimento registrado."""
        return self.history.get("last_sentiment")

    def get_sentiment_trend(self, days: int = 7) -> Dict[str, Any]:
        """Analisa a tendência de sentimento dos últimos dias."""
        if "entries" not in self.history or not self.history["entries"]:
            return {"trend": "unknown", "confidence": 0}

        # Filtrar entradas dos últimos dias
        cutoff_date = datetime.now().timestamp() - (days * 24 * 3600)
        recent_entries = [
            entry
            for entry in self.history["entries"]
            if datetime.fromisoformat(entry["timestamp"]).timestamp() > cutoff_date
        ]

        if not recent_entries:
            return {"trend": "insufficient_data", "confidence": 0}

        # Análise simples de tendência
        fear_greed_values = [entry["fear_greed_value"] for entry in recent_entries]
        sentiments = [entry["sentiment"] for entry in recent_entries]

        avg_fear_greed = sum(fear_greed_values) / len(fear_greed_values)
        current_fear_greed = fear_greed_values[-1]

        # Determinar tendência
        if current_fear_greed > avg_fear_greed + 10:
            trend = "improving"
            confidence = min(100, abs(current_fear_greed - avg_fear_greed) * 2)
        elif current_fear_greed < avg_fear_greed - 10:
            trend = "worsening"
            confidence = min(100, abs(current_fear_greed - avg_fear_greed) * 2)
        else:
            trend = "stable"
            confidence = 50

        return {
            "trend": trend,
            "confidence": confidence,
            "avg_fear_greed": avg_fear_greed,
            "current_fear_greed": current_fear_greed,
            "sentiment_distribution": {
                sentiment: sentiments.count(sentiment) / len(sentiments)
                for sentiment in set(sentiments)
            },
        }

    def should_force_transition(
        self, current_sentiment: str, current_fear_greed: int
    ) -> bool:
        """Determina se deve forçar transição baseado em mudanças extremas."""
        last = self.get_last_sentiment()
        if not last:
            return False

        last_sentiment = last["sentiment"]
        last_fear_greed = last["fear_greed_value"]

        # Forçar transição se houver mudança extrema no índice Fear & Greed
        if abs(current_fear_greed - last_fear_greed) > 30:
            logger.warning(
                f"🚨 Mudança extrema detectada: {last_fear_greed} -> {current_fear_greed}"
            )
            return True

        # Forçar transição se mudar de extremo para neutro ou vice-versa
        extreme_sentiments = ["Extreme Fear", "Extreme Greed"]
        if (
            last_sentiment in extreme_sentiments
            and current_sentiment not in extreme_sentiments
        ) or (
            last_sentiment not in extreme_sentiments
            and current_sentiment in extreme_sentiments
        ):
            logger.warning(
                f"🚨 Transição extrema detectada: {last_sentiment} -> {current_sentiment}"
            )
            return True

        return False

    def get_statistics(self) -> Dict[str, Any]:
        """Retorna estatísticas do histórico."""
        if "entries" not in self.history or not self.history["entries"]:
            return {"total_entries": 0}

        entries = self.history["entries"]
        fear_greed_values = [entry["fear_greed_value"] for entry in entries]

        return {
            "total_entries": len(entries),
            "date_range": {
                "first": entries[0]["timestamp"],
                "last": entries[-1]["timestamp"],
            },
            "fear_greed_stats": {
                "min": min(fear_greed_values),
                "max": max(fear_greed_values),
                "avg": sum(fear_greed_values) / len(fear_greed_values),
            },
            "profile_usage": {
                profile: sum(1 for entry in entries if entry["profile_used"] == profile)
                for profile in set(entry["profile_used"] for entry in entries)
            },
            "rebalance_frequency": {
                "total": sum(1 for entry in entries if entry["rebalance_performed"]),
                "percentage": sum(
                    1 for entry in entries if entry["rebalance_performed"]
                )
                / len(entries)
                * 100,
            },
        }


# Singleton instance
_sentiment_history: Optional[SentimentHistory] = None


def get_sentiment_history() -> SentimentHistory:
    """Retorna a instância singleton do histórico de sentimentos."""
    global _sentiment_history
    if _sentiment_history is None:
        _sentiment_history = SentimentHistory()
    return _sentiment_history
