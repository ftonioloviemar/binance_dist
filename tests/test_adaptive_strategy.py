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


def test_missing_market_cap_signal_keeps_sentiment_profile_and_btc_guard() -> None:
    manager = get_adaptive_manager()
    without_cap = manager.calculate_adaptive_config(
        current_sentiment=MarketSentiment.GREED,
        btc_change_24h=-2.0,
        market_cap_change_24h=None,
        current_profile="moderate",
    )
    neutral_cap = manager.calculate_adaptive_config(
        current_sentiment=MarketSentiment.GREED,
        btc_change_24h=-2.0,
        market_cap_change_24h=0.0,
        current_profile="moderate",
    )
    severe_btc_drop = manager.calculate_adaptive_config(
        current_sentiment=MarketSentiment.GREED,
        btc_change_24h=-11.0,
        market_cap_change_24h=None,
        current_profile="moderate",
    )

    assert without_cap.profile is neutral_cap.profile
    assert without_cap.targets == pytest.approx(neutral_cap.targets)
    assert severe_btc_drop.profile is RiskProfile.CONSERVATIVE
