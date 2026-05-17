from __future__ import annotations

import pytest

from adaptive_strategy import MarketSentiment, RiskProfile, get_adaptive_manager


def test_extreme_fear_config_is_conservative_and_normalized() -> None:
    config = get_adaptive_manager().calculate_adaptive_config(
        current_sentiment=MarketSentiment.EXTREME_FEAR,
        btc_change_24h=-12.0,
        market_cap_change_24h=-6.0,
        current_profile="moderate",
    )

    assert config.profile is RiskProfile.CONSERVATIVE
    assert config.drift_threshold == 0.03
    assert config.max_slippage == 0.006
    assert sum(config.targets.values()) == pytest.approx(1.0)
    assert config.targets == pytest.approx(
        {
            "BTC": 0.0583,
            "ETH": 0.1443,
            "SOL": 0.0323,
            "USDT": 0.7402,
            "BNB": 0.0083,
            "AVAX": 0.0083,
            "ADA": 0.0083,
        }
    )
