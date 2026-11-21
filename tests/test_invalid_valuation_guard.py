from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

import app
from binance_client import Balance, SimpleEarnPosition, SymbolFilters
from config import EnvSettings
from performance_store import build_portfolio_snapshot
from portfolio import (
    PortfolioError,
    RebalanceDecision,
    build_trades,
    compute_current_weights,
)


INVALID = [None, 0.0, -1.0, float('nan'), float('inf'), float('-inf')]


def snapshot(source, price, quantity=2, override='complete'):
    balances = [{'asset': 'TEST', 'quantity': quantity}]
    return build_portfolio_snapshot(
        run_id='synthetic', phase='before', quote_asset='USDQ',
        spot_balances=balances if source == 'spot' else [],
        earn_positions=balances if source == 'earn' else [],
        prices={} if price is None else {'TEST': price},
        timestamp='2026-01-01T00:00:00Z', data_quality=override,
    )


@pytest.mark.parametrize('source', ['spot', 'earn'])
@pytest.mark.parametrize('price', INVALID, ids=['missing', 'zero', 'negative', 'nan', 'posinf', 'neginf'])
def test_invalid_held_price_forces_incomplete_snapshot(source, price):
    result = snapshot(source, price)
    assert result['data_quality'] == 'incomplete'
    assert result['missing_prices'] == ['TEST']
    assert f'{source}:TEST' not in result['asset_values']


@pytest.mark.parametrize('source', ['spot', 'earn'])
@pytest.mark.parametrize('price', INVALID)
def test_zero_balance_does_not_require_price(source, price):
    assert snapshot(source, price, quantity=0)['data_quality'] == 'complete'


@pytest.mark.parametrize('source', ['spot', 'earn'])
def test_positive_price_valued_in_snapshot(source):
    result = snapshot(source, 3.0)
    assert result['data_quality'] == 'complete'
    assert result['asset_values'][f'{source}:TEST'] == '6.00'


def test_quote_holding_uses_unit_price_without_market_price():
    result = build_portfolio_snapshot(
        run_id='synthetic', phase='before', quote_asset='USDQ',
        spot_balances=[{'asset': 'USDQ', 'quantity': 2}],
        earn_positions=[{'asset': 'USDQ', 'quantity': 3}], prices={},
        timestamp='2026-01-01T00:00:00Z',
    )
    assert result['data_quality'] == 'complete'
    assert result['total_value'] == '5.00'
    weights = compute_current_weights([Balance(asset='USDQ', free=2, locked=0)], {}, 'USDQ')
    assert weights.total_value == 2
    assert weights.positions['USDQ'].price == 1


@pytest.mark.parametrize('price', INVALID, ids=['missing', 'zero', 'negative', 'nan', 'posinf', 'neginf'])
def test_weights_reject_unpriced_positive_holding_even_with_quote_balance(price):
    balances = [Balance(asset='USDQ', free=10, locked=0), Balance(asset='TEST', free=2, locked=0)]
    prices = {} if price is None else {'TEST': price}
    with pytest.raises(PortfolioError):
        compute_current_weights(balances, prices, 'USDQ')


def test_weights_preserve_valid_value_and_ignore_zero_balance():
    balances = [Balance(asset='USDQ', free=4, locked=0), Balance(asset='TEST', free=2, locked=0), Balance(asset='ZERO', free=0, locked=0)]
    result = compute_current_weights(balances, {'TEST': 3}, 'USDQ')
    assert result.total_value == 10
    assert result.positions['TEST'].weight == pytest.approx(0.6)
    assert 'ZERO' not in result.positions


@pytest.mark.parametrize('price', INVALID)
def test_invalid_target_price_never_builds_an_order(price):
    snapshot_ = compute_current_weights([Balance(asset='USDQ', free=100, locked=0)], {}, 'USDQ')
    prices = {} if price is None else {'TEST': price}
    filters = {'TESTUSDQ': SymbolFilters(symbol='TESTUSDQ', lot_step=0.01, min_qty=0.01, max_qty=1000, min_notional=1, price_tick=0.01)}
    try:
        trades = build_trades(snapshot=snapshot_, decision=RebalanceDecision(True, {'TEST': 0.5}), prices=prices, filters=filters, min_notional=1, max_slippage=0.01)
    except PortfolioError:
        return
    assert trades == []


class MemoryAuditor:
    def __init__(self):
        self.run_id = 'synthetic'
        self.steps = []

    def log_step(self, **kwargs):
        self.steps.append(kwargs)

    def log_exception(self, **kwargs):
        pass

    def start_run(self, **kwargs):
        pass

    def finalize_run(self, *args, **kwargs):
        pass

    def close(self):
        pass


@pytest.mark.parametrize('dry_run', [False, True], ids=['scheduled', 'dry-run'])
@pytest.mark.parametrize('source', ['spot', 'earn'])
@pytest.mark.parametrize('price', INVALID, ids=['missing', 'zero', 'negative', 'nan', 'posinf', 'neginf'])
def test_run_stops_before_planning_or_fund_movement(monkeypatch, dry_run, source, price):
    actions = []
    snapshots = []

    class Client:
        def __init__(self, **kwargs):
            pass

        def get_account_balances(self):
            return [Balance(asset='USDQ', free=100, locked=0)] + ([Balance(asset='TEST', free=2, locked=0)] if source == 'spot' else [])

        def get_simple_earn_flexible_positions(self):
            return [SimpleEarnPosition(product_id='synthetic', asset='TEST', total_amount=2, redeemable_amount=2, can_fast_redeem=True)] if source == 'earn' else []

        def get_simple_earn_flexible_products(self):
            return {}

        def close(self):
            pass

    monkeypatch.setattr(app, 'BinanceClient', Client)
    monkeypatch.setattr(app, 'AuditLogger', MemoryAuditor)
    monkeypatch.setattr(app, 'load_env_settings', lambda recv_window: EnvSettings(api_key='fake', api_secret='fake', testnet=True, base_url='https://invalid.example', recv_window=recv_window, simple_earn_enabled=True))
    monkeypatch.setattr(app, '_fetch_asset_prices', lambda *args: {} if price is None else {'TEST': price})
    monkeypatch.setattr(app, '_persist_performance_snapshot', lambda auditor, payload: snapshots.append(payload))
    monkeypatch.setattr(app, 'fetch_macro_snapshot', lambda: SimpleNamespace(data={}, errors=[], sources={}))
    for name in ('decide_rebalance', 'rebalance_has_tradable_orders', 'build_trades', 'execute_trades', '_redeem_simple_earn_positions', '_subscribe_simple_earn_balances'):
        monkeypatch.setattr(app, name, lambda *args, _name=name, **kwargs: actions.append(_name))
    args = argparse.Namespace(command='rebalance', dry_run=dry_run, profile='moderate', drift=0.01, max_slippage=0.003, min_notional=0.0, targets='USDQ=1', quote='USDQ', recv_window=5000, config_path=Path('nonexistent-test-config.toml'), adaptive=False)
    assert app.run_rebalance(args) != 0
    assert actions == []
    assert any(item['phase'] == 'before' and item['data_quality'] == 'incomplete' for item in snapshots)


@pytest.mark.parametrize('price', INVALID)
def test_after_refresh_invalid_price_preserves_completed_operation(monkeypatch, price):
    auditor = MemoryAuditor()
    auditor.log_step(name='earn_redeem', status='completed', detail='synthetic operation')

    class Client:
        def get_account_balances(self):
            return [Balance(asset='TEST', free=2, locked=0)]

        def get_simple_earn_flexible_positions(self):
            return []

    monkeypatch.setattr(app, '_fetch_asset_prices', lambda *args: {} if price is None else {'TEST': price})
    result = app._build_post_trade_performance_snapshot_payload(
        client=Client(), auditor=auditor, run_id='synthetic', quote='USDQ',
        spot_balances=[], earn_positions=[], prices={'TEST': 3}, targets={},
        timestamp='2026-01-01T00:00:00Z', products_by_asset={},
        simple_earn_enabled=True, dry_run=False, spot_balances_fresh=True, pendings=[],
    )
    assert result.payload['phase'] == 'after'
    assert result.payload['data_quality'] == 'incomplete'
    assert any(step['name'] == 'earn_redeem' and step['status'] == 'completed' for step in auditor.steps)
    assert not any('revert' in str(step).lower() or 'rollback' in str(step).lower() for step in auditor.steps)
