from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class MarketSentiment(Enum):
    EXTREME_FEAR = "Extreme Fear"
    FEAR = "Fear"
    NEUTRAL = "Neutral"
    GREED = "Greed"
    EXTREME_GREED = "Extreme Greed"


class RiskProfile(Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass
class AdaptiveConfig:
    profile: RiskProfile
    drift_threshold: float
    max_slippage: float
    targets: Dict[str, float]
    rationale: str


class AdaptiveStrategyManager:
    """
    Gerencia estratégias adaptativas baseadas no sentimento do mercado e indicadores técnicos.
    """

    def __init__(self):
        self.sentiment_thresholds = {
            MarketSentiment.EXTREME_FEAR: (0, 20),
            MarketSentiment.FEAR: (20, 40),
            MarketSentiment.NEUTRAL: (40, 60),
            MarketSentiment.GREED: (60, 80),
            MarketSentiment.EXTREME_GREED: (80, 100),
        }

        # Configurações baseadas no sentimento de mercado
        self.sentiment_configs = {
            MarketSentiment.EXTREME_FEAR: {
                "profile": RiskProfile.CONSERVATIVE,
                "drift_multiplier": 3.0,  # Mais tolerância para ações em mercado extremo
                "slippage_multiplier": 2.0,
                "stable_increase": 0.25,  # Aumentar stablecoins em 25%
                "btc_reduction": 0.15,  # Reduzir BTC em 15%
                "rationale": "Mercado em pânico - proteger capital com alocação conservadora",
            },
            MarketSentiment.FEAR: {
                "profile": RiskProfile.CONSERVATIVE,
                "drift_multiplier": 2.0,
                "slippage_multiplier": 1.5,
                "stable_increase": 0.15,
                "btc_reduction": 0.10,
                "rationale": "Medo no mercado - posição defensiva mas preparada para oportunidades",
            },
            MarketSentiment.NEUTRAL: {
                "profile": RiskProfile.MODERATE,
                "drift_multiplier": 1.0,
                "slippage_multiplier": 1.0,
                "stable_increase": 0.0,
                "btc_reduction": 0.0,
                "rationale": "Mercado equilibrado - manter estratégia moderada padrão",
            },
            MarketSentiment.GREED: {
                "profile": RiskProfile.MODERATE,
                "drift_multiplier": 0.8,
                "slippage_multiplier": 0.8,
                "stable_increase": -0.05,  # Reduzir ligeiramente stablecoins
                "btc_reduction": -0.05,  # Aumentar ligeiramente BTC
                "rationale": "Otimismo no mercado - leve aumento em ativos de risco",
            },
            MarketSentiment.EXTREME_GREED: {
                "profile": RiskProfile.AGGRESSIVE,
                "drift_multiplier": 0.5,
                "slippage_multiplier": 0.6,
                "stable_increase": -0.15,  # Reduzir stablecoins significativamente
                "btc_reduction": -0.10,  # Aumentar BTC
                "rationale": "Euphoria no mercado - aproveitar momentum mas com cuidado",
            },
        }

        # Configurações base por perfil
        self.base_profiles = {
            RiskProfile.CONSERVATIVE: {
                "BTC": 0.25,
                "ETH": 0.15,
                "SOL": 0.05,
                "USDT": 0.40,
                "BNB": 0.05,
                "AVAX": 0.05,
                "ADA": 0.05,
            },
            RiskProfile.MODERATE: {
                "BTC": 0.40,
                "ETH": 0.20,
                "SOL": 0.15,
                "USDT": 0.15,
                "BNB": 0.033,
                "AVAX": 0.033,
                "ADA": 0.033,
            },
            RiskProfile.AGGRESSIVE: {
                "BTC": 0.30,
                "ETH": 0.25,
                "SOL": 0.20,
                "USDT": 0.10,
                "BNB": 0.05,
                "AVAX": 0.05,
                "ADA": 0.05,
            },
        }

        # Parâmetros base (valores padrão do sistema)
        self.base_drift = 0.01
        self.base_slippage = 0.003

    def get_market_sentiment(
        self, fear_greed_value: int, fear_greed_classification: str
    ) -> MarketSentiment:
        """Determina o sentimento de mercado baseado no índice Fear & Greed."""
        try:
            # Primeiro tenta usar o valor numérico
            for sentiment, (min_val, max_val) in self.sentiment_thresholds.items():
                if min_val <= fear_greed_value < max_val:
                    return sentiment

            # Fallback para classificação textual
            classification_map = {
                "Extreme Fear": MarketSentiment.EXTREME_FEAR,
                "Fear": MarketSentiment.FEAR,
                "Neutral": MarketSentiment.NEUTRAL,
                "Greed": MarketSentiment.GREED,
                "Extreme Greed": MarketSentiment.EXTREME_GREED,
            }

            return classification_map.get(
                fear_greed_classification, MarketSentiment.NEUTRAL
            )

        except Exception as e:
            logger.warning(
                f"Erro ao determinar sentimento de mercado: {e}. Usando Neutral como padrão."
            )
            return MarketSentiment.NEUTRAL

    def calculate_adaptive_config(
        self,
        current_sentiment: MarketSentiment,
        btc_change_24h: float,
        market_cap_change_24h: float,
        current_profile: Optional[str] = None,
    ) -> AdaptiveConfig:
        """Calcula a configuração adaptativa baseada no sentimento de mercado e indicadores."""

        sentiment_config = self.sentiment_configs[current_sentiment]
        base_profile = sentiment_config["profile"]

        # Ajustar perfil baseado em tendências adicionais
        if abs(btc_change_24h) > 10 or abs(market_cap_change_24h) > 5:
            # Em movimentos extremos, ser mais conservador
            if btc_change_24h < -10 or market_cap_change_24h < -5:
                if base_profile != RiskProfile.CONSERVATIVE:
                    logger.info(
                        f"Ajustando perfil de {base_profile.value} para {RiskProfile.CONSERVATIVE.value} devido a queda severa"
                    )
                    base_profile = RiskProfile.CONSERVATIVE

        # Calcular targets adaptativos
        base_targets = self.base_profiles[base_profile].copy()

        # Aplicar ajustes baseados no sentimento
        stable_increase = sentiment_config["stable_increase"]
        btc_reduction = sentiment_config["btc_reduction"]

        if stable_increase != 0:
            base_targets["USDT"] += stable_increase
            # Reduzir proporcionalmente outros ativos
            non_stable_assets = [k for k in base_targets.keys() if k != "USDT"]
            total_reduction = stable_increase / len(non_stable_assets)
            for asset in non_stable_assets:
                base_targets[asset] -= total_reduction

        if btc_reduction != 0:
            base_targets["BTC"] -= btc_reduction
            # Adicionar a stablecoins ou distribuir entre outros
            if btc_reduction > 0:  # Reduzindo BTC
                base_targets["USDT"] += btc_reduction * 0.6
                # Distribuir o restante entre ETH e SOL
                remaining = btc_reduction * 0.4
                base_targets["ETH"] += remaining * 0.6
                base_targets["SOL"] += remaining * 0.4
            else:  # Aumentando BTC
                # Reduzir de stablecoins principalmente
                reduction_from_stable = min(
                    abs(btc_reduction) * 0.7, base_targets["USDT"] - 0.05
                )
                base_targets["USDT"] -= reduction_from_stable
                remaining = abs(btc_reduction) - reduction_from_stable
                if remaining > 0:
                    # Reduzir proporcionalmente de outros ativos
                    other_assets = [
                        k for k in base_targets.keys() if k not in ["BTC", "USDT"]
                    ]
                    for asset in other_assets:
                        reduction = remaining * (
                            base_targets[asset]
                            / sum(base_targets[k] for k in other_assets)
                        )
                        base_targets[asset] -= reduction

        # Normalizar para garantir que soma = 1.0
        total = sum(base_targets.values())
        if total > 0:
            for asset in base_targets:
                base_targets[asset] = round(base_targets[asset] / total, 4)
            residual = round(1.0 - sum(base_targets.values()), 4)
            if residual:
                largest_asset = max(base_targets, key=base_targets.get)
                base_targets[largest_asset] = round(
                    base_targets[largest_asset] + residual, 4
                )

        # Calcular parâmetros dinâmicos
        drift_threshold = self.base_drift * sentiment_config["drift_multiplier"]
        max_slippage = self.base_slippage * sentiment_config["slippage_multiplier"]

        return AdaptiveConfig(
            profile=base_profile,
            drift_threshold=drift_threshold,
            max_slippage=max_slippage,
            targets=base_targets,
            rationale=sentiment_config["rationale"],
        )

    def should_transition_profile(
        self,
        current_sentiment: MarketSentiment,
        previous_sentiment: MarketSentiment,
        current_profile: str,
        btc_change_24h: float,
    ) -> bool:
        """Determina se deve haver transição de perfil baseado em mudanças de sentimento."""

        # Sempre transicionar em caso de sentimento extremo
        if current_sentiment in [
            MarketSentiment.EXTREME_FEAR,
            MarketSentiment.EXTREME_GREED,
        ]:
            return True

        # Transicionar se houver mudança significativa de sentimento
        sentiment_order = [
            MarketSentiment.EXTREME_FEAR,
            MarketSentiment.FEAR,
            MarketSentiment.NEUTRAL,
            MarketSentiment.GREED,
            MarketSentiment.EXTREME_GREED,
        ]

        current_idx = sentiment_order.index(current_sentiment)
        previous_idx = sentiment_order.index(previous_sentiment)

        # Mudança de 2 ou mais níveis de sentimento
        if abs(current_idx - previous_idx) >= 2:
            return True

        # Mudança de 1 nível + movimento de BTC significativo
        if abs(current_idx - previous_idx) >= 1 and abs(btc_change_24h) > 8:
            return True

        return False

    def get_recommendation_summary(
        self,
        adaptive_config: AdaptiveConfig,
        current_sentiment: MarketSentiment,
        fear_greed_value: int,
        btc_change_24h: float,
    ) -> str:
        """Gera um resumo da recomendação adaptativa."""

        summary = f"""
📊 **ANÁLISE ADAPTATIVA DO MERCADO**

🎯 **Sentimento Atual**: {current_sentiment.value} ({fear_greed_value}/100)
📈 **Mudança BTC 24h**: {btc_change_24h:+.2f}%
🎭 **Perfil Recomendado**: {adaptive_config.profile.value.upper()}

⚙️ **Parâmetros Ajustados**:
   • Drift Threshold: {adaptive_config.drift_threshold:.2%}
   • Max Slippage: {adaptive_config.max_slippage:.2%}

📋 **Alocação Recomendada**:
"""

        for asset, weight in adaptive_config.targets.items():
            if weight >= 0.01:  # Mostrar apenas alocações significativas
                summary += f"   • {asset}: {weight:.1%}\n"

        summary += f"\n💡 **Racional**: {adaptive_config.rationale}"

        return summary


# Singleton instance
_adaptive_manager: Optional[AdaptiveStrategyManager] = None


def get_adaptive_manager() -> AdaptiveStrategyManager:
    """Retorna a instância singleton do gerenciador adaptativo."""
    global _adaptive_manager
    if _adaptive_manager is None:
        _adaptive_manager = AdaptiveStrategyManager()
    return _adaptive_manager
