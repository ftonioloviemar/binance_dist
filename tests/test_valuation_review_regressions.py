from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

import app
from binance_client import Balance, SimpleEarnPosition
from config import EnvSettings
from portfolio import RebalanceDecision, compute_current_weights


def test_valuation_aggregates_spot_and_earn_quantities_for_same_asset():
    spot = [Balance(asset='USDQ', free=10, locked=0),
            Balance(asset='TEST', free=2, locked=0),
            Balance(asset='LDTEST', free=3, locked=0)]
    earn = [SimpleEarnPosition(product_id='synthetic', asset='TEST',
        total_amount=3, redeemable_amount=3, can_fast_redeem=True)]

    balances = app._balances_for_valuation(spot_balances=spot, earn_positions=earn)
    snapshot = compute_current_weights(balances, {'TEST': 2}, 'USDQ')

    assert snapshot.positions['TEST'].quantity == 5
    assert snapshot.positions['TEST'].value == 10
    assert snapshot.total_value == 20
    assert snapshot.positions['TEST'].weight == pytest.approx(0.5)
    assert 'LDTEST' not in snapshot.positions


def test_execution_availability_uses_only_refreshed_spot_free_balances():
    stale = compute_current_weights(
        [Balance(asset='USDQ', free=100, locked=0),
         Balance(asset='TEST', free=50, locked=0)], {'TEST': 2}, 'USDQ')
    refreshed = [Balance(asset='USDQ', free=4, locked=6),
                 Balance(asset='TEST', free=3, locked=7),
                 Balance(asset='NEW', free=2, locked=8)]

    available = app._init_available_balances(stale, stale, refreshed)

    assert available == {'USDQ': 4, 'TEST': 3, 'NEW': 2}
    assert [(b.asset, b.free, b.locked) for b in refreshed] == [
        ('USDQ', 4, 6), ('TEST', 3, 7), ('NEW', 2, 8)]


@pytest.mark.parametrize('base_price', [1.0, None], ids=['complete', 'missing-price'])
def test_after_summary_uses_unrounded_values_and_rejects_incomplete(monkeypatch, base_price):
    spot = [Balance(asset='USDQ', free=0.003, locked=0),
            Balance(asset='TEST', free=0.001, locked=0)]
    earn = [SimpleEarnPosition(product_id='synthetic', asset='TEST',
        total_amount=0.002, redeemable_amount=0.002, can_fast_redeem=True)]
    prices = {} if base_price is None else {'TEST': base_price}

    class Client:
        def get_account_balances(self):
            return spot

        def get_simple_earn_flexible_positions(self):
            return earn

    monkeypatch.setattr(app, '_fetch_asset_prices', lambda *_args: prices)
    result = app._build_post_trade_performance_snapshot_payload(
        client=Client(), auditor=SimpleNamespace(log_step=lambda **kwargs: None),
        run_id='synthetic', quote='USDQ', spot_balances=spot, earn_positions=earn,
        prices=prices, targets={}, timestamp='2026-01-01T00:00:00Z',
        products_by_asset={}, simple_earn_enabled=True, dry_run=False,
        spot_balances_fresh=True, pendings=[])

    if base_price is None:
        assert result.payload['data_quality'] == 'incomplete'
        assert 'TEST' in result.payload['missing_prices']
        assert result.summary_weights is None
    else:
        assert result.payload['data_quality'] == 'complete'
        assert result.payload['asset_values']['spot:TEST'] == '0.00'
        assert result.payload['asset_values']['earn:TEST'] == '0.00'
        assert result.summary_weights == pytest.approx({'USDQ': 0.5, 'TEST': 0.5})


@pytest.mark.parametrize('dry_run,earn_failure', [
    (False, False), (True, False), (True, True),
], ids=['live-fake', 'dry-run', 'dry-run-earn-unknown'])
def test_run_uses_spot_free_and_only_simulated_earn_for_execution(monkeypatch, tmp_path, dry_run, earn_failure):
    monkeypatch.chdir(tmp_path)
    state = {'redeemed': False}
    captured = {'available': [], 'summaries': [], 'snapshots': [], 'steps': []}
    initial = [Balance(asset='USDQ', free=10, locked=0),
               Balance(asset='TEST', free=1, locked=2)]
    refreshed = [Balance(asset='USDQ', free=4, locked=6),
                 Balance(asset='LDTEST', free=2, locked=1)]
    earn = [SimpleEarnPosition(product_id='synthetic', asset='TEST',
        total_amount=5, redeemable_amount=2, can_fast_redeem=True),
        SimpleEarnPosition(product_id='fallback', asset='OTHER',
        total_amount=4, redeemable_amount=0, can_fast_redeem=True),
        SimpleEarnPosition(product_id='skipped', asset='SKIP',
        total_amount=3, redeemable_amount=-1, can_fast_redeem=True)]

    class Auditor:
        run_id = 'synthetic-run'

        def start_run(self, **kwargs):
            pass

        def log_step(self, **kwargs):
            captured['steps'].append(kwargs)

        def log_exception(self, **kwargs):
            pass

        def finalize_run(self, status):
            pass

        def close(self):
            pass

    class Client:
        def __init__(self, **kwargs):
            pass

        def get_account_balances(self):
            return refreshed if state['redeemed'] else initial

        def get_simple_earn_flexible_positions(self):
            if earn_failure:
                raise RuntimeError('synthetic Earn snapshot failure')
            return [] if state['redeemed'] else earn

        def get_simple_earn_flexible_products(self):
            return {}

        def get_exchange_info(self):
            return {}

        def close(self):
            pass

    real_redeem = app._redeem_simple_earn_positions

    def redeem(**kwargs):
        if kwargs['dry_run']:
            real_redeem(**kwargs)
        else:
            state['redeemed'] = True

    monkeypatch.setattr(app, 'BinanceClient', Client)
    monkeypatch.setattr(app, 'AuditLogger', Auditor)
    monkeypatch.setattr(app, 'load_env_settings', lambda recv_window: EnvSettings(
        api_key='fake', api_secret='fake', testnet=True,
        base_url='https://invalid.example', recv_window=recv_window,
        simple_earn_enabled=True, ai_provider='off'))
    monkeypatch.setattr(app, 'fetch_macro_snapshot', lambda: SimpleNamespace(data={}, errors=[], sources={}))
    monkeypatch.setattr(app, '_fetch_asset_prices', lambda *_args: {'TEST': 2, 'LDTEST': 2, 'OTHER': 1, 'SKIP': 1})
    monkeypatch.setattr(app, '_ensure_target_prices', lambda _client, values, *_args: values)
    monkeypatch.setattr(app, 'record_portfolio_snapshot', lambda _path, payload: captured['snapshots'].append(payload))
    monkeypatch.setattr(app, '_build_shadow_run', lambda **kwargs: None)
    monkeypatch.setattr(app, 'filter_dust_positions', lambda snapshot, *_args: (snapshot, {}))
    monkeypatch.setattr(app, 'decide_rebalance', lambda *_args: RebalanceDecision(True, {'TEST': 0.5}))
    monkeypatch.setattr(app, 'rebalance_has_tradable_orders', lambda **kwargs: True)
    monkeypatch.setattr(app, 'build_trades', lambda **kwargs: [object()])
    monkeypatch.setattr(app, 'filter_anti_churn_trades', lambda **kwargs: kwargs['trades'])
    monkeypatch.setattr(app, '_redeem_simple_earn_positions', redeem)
    monkeypatch.setattr(app, '_fetch_fee_reference_prices', lambda *_args: {})
    monkeypatch.setattr(app, 'execute_trades', lambda **kwargs: captured['available'].append(dict(kwargs['available_balances'])))
    monkeypatch.setattr(app, '_print_summary', lambda before, after: captured['summaries'].append(after))
    args = argparse.Namespace(command='rebalance', dry_run=dry_run, profile='moderate',
        drift=0.01, max_slippage=0.003, min_notional=0.0, targets='USDQ=1',
        quote='USDQ', recv_window=5000, config_path=Path('missing.toml'), adaptive=False)

    assert app.run_rebalance(args) == 0
    if earn_failure:
        [after] = [item for item in captured['snapshots'] if item['phase'] == 'after']
        assert after['data_quality'] == 'incomplete'
        assert after['missing_prices'] == []
        assert captured['summaries'] == [None]
        return
    if dry_run:
        assert captured['available'] == [{'USDQ': 10, 'TEST': 3, 'OTHER': 4}]
        simulated = [s for s in captured['steps'] if s.get('name') == 'earn_redeem'
                     and s.get('status') == 'simulated']
        assert {s['detail'] for s in simulated} == {
            'TEST amount=2.00000000 product=synthetic',
            'OTHER amount=4.00000000 product=fallback',
        }
        assert [(b.asset, b.free, b.locked) for b in initial] == [
            ('USDQ', 10, 0), ('TEST', 1, 2)]
        return
    assert captured['available'] == [{'USDQ': 4, 'LDTEST': 2}]
    [after] = [item for item in captured['snapshots'] if item['phase'] == 'after']
    assert after['asset_values'] == {'spot:USDQ': '10.00', 'spot:LDTEST': '6.00'}
    [summary] = captured['summaries']
    weights = (summary if isinstance(summary, dict) else
               {asset: position.weight for asset, position in summary.positions.items()})
    assert weights == pytest.approx({'USDQ': 0.625, 'LDTEST': 0.375})


@pytest.mark.parametrize('dry_run', [True, False], ids=['dry-run', 'live-refresh'])
def test_after_snapshot_initial_earn_failure_only_recovers_after_live_refresh(monkeypatch, dry_run):
    spot = [Balance(asset='USDQ', free=10, locked=0),
            Balance(asset='TEST', free=2, locked=0)]
    refreshed_earn = [SimpleEarnPosition(product_id='synthetic', asset='TEST',
        total_amount=3, redeemable_amount=3, can_fast_redeem=True)]
    calls = []

    class Client:
        def get_account_balances(self):
            calls.append('spot')
            return spot

        def get_simple_earn_flexible_positions(self):
            calls.append('earn')
            return refreshed_earn

    monkeypatch.setattr(app, '_fetch_asset_prices', lambda *_args: {'TEST': 2})
    result = app._build_post_trade_performance_snapshot_payload(
        client=Client(), auditor=SimpleNamespace(log_step=lambda **kwargs: None),
        run_id='synthetic', quote='USDQ', spot_balances=spot, earn_positions=[],
        prices={'TEST': 2}, targets={}, timestamp='2026-01-01T00:00:00Z',
        products_by_asset={}, simple_earn_enabled=True, dry_run=dry_run,
        spot_balances_fresh=True, pendings=[], initial_data_quality='incomplete')

    assert result.payload['missing_prices'] == []
    if dry_run:
        assert calls == []
        assert result.payload['data_quality'] == 'incomplete'
        assert result.summary_weights is None
    else:
        assert calls == ['spot', 'earn']
        assert result.payload['data_quality'] == 'complete'
        assert result.payload['asset_values']['earn:TEST'] == '6.00'
        assert result.summary_weights == pytest.approx({'USDQ': 0.5, 'TEST': 0.5})
