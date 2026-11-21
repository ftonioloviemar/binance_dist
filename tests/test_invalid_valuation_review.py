from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

import app
from binance_client import Balance, SimpleEarnPosition
from config import EnvSettings
from logging_audit import AuditLogger, load_run_detail
from performance_store import load_portfolio_snapshots, record_portfolio_snapshot


@pytest.fixture
def isolated_run(monkeypatch, tmp_path):
    actions = []
    prices = []
    spot = [Balance(asset='USDQ', free=100, locked=0),
            Balance(asset='TEST', free=2, locked=0)]
    earn = []
    db = tmp_path / 'performance.sqlite'
    logs = tmp_path / 'logs'

    class Client:
        def __init__(self, **kwargs):
            pass

        def get_account_balances(self):
            return spot

        def get_simple_earn_flexible_positions(self):
            return earn

        def get_simple_earn_flexible_products(self):
            return {}

        def close(self):
            pass

    monkeypatch.setattr(app, 'BinanceClient', Client)
    monkeypatch.setattr(app, 'AuditLogger', lambda: AuditLogger(logs_dir=logs))
    monkeypatch.setattr(app, 'record_portfolio_snapshot',
                        lambda _path, payload: record_portfolio_snapshot(db, payload))
    monkeypatch.setattr(app, 'load_env_settings', lambda recv_window: EnvSettings(
        api_key='fake', api_secret='fake', testnet=True,
        base_url='https://invalid.example', recv_window=recv_window,
        simple_earn_enabled=True, ai_provider='off'))
    monkeypatch.setattr(app, '_fetch_asset_prices', lambda *args: prices.pop(0))
    monkeypatch.setattr(app, 'fetch_macro_snapshot',
                        lambda: SimpleNamespace(data={}, errors=[], sources={}))
    monkeypatch.setattr(app, '_resolve_ai_advice', lambda *args: SimpleNamespace(
        targets={'USDQ': 1}, rationale='', provider='off', model_failures=[],
        model_used=None, action='hold'))
    monkeypatch.setattr(app, '_refresh_openrouter_models_after_failure', lambda *args: None)
    for name in ('decide_rebalance', 'rebalance_has_tradable_orders', 'build_trades',
                 'execute_trades', '_redeem_simple_earn_positions',
                 '_subscribe_simple_earn_balances'):
        monkeypatch.setattr(app, name, lambda *args, _name=name, **kwargs: actions.append(_name))
    args = argparse.Namespace(command='rebalance', dry_run=True, profile='moderate',
        drift=0.01, max_slippage=0.003, min_notional=0.0, targets='USDQ=1',
        quote='USDQ', recv_window=5000, config_path=Path('nonexistent-test-config.toml'),
        adaptive=False)
    return SimpleNamespace(args=args, prices=prices, spot=spot, earn=earn,
                           actions=actions, db=db, logs=logs)


def test_early_rejections_have_distinct_real_audit_runs_and_snapshots(isolated_run):
    run = isolated_run
    run.prices.extend([{}, {}])
    assert app.run_rebalance(run.args) != 0
    assert app.run_rebalance(run.args) != 0
    snapshots = load_portfolio_snapshots(run.db)
    assert len(snapshots) == 2
    ids = {item['run_id'] for item in snapshots}
    assert len(ids) == 2 and 'unknown' not in ids and '' not in ids
    for item in snapshots:
        assert item['phase'] == 'before' and item['data_quality'] == 'incomplete'
        assert 'TEST' in item['missing_prices']
        detail = load_run_detail(item['run_id'], logs_dir=run.logs)
        assert detail is not None and detail['run']['status'] == 'failed'
        assert any(step['name'] == 'valuation_guard' for step in detail['steps'])
    assert run.actions == []


@pytest.mark.parametrize('source', ['spot', 'earn'])
def test_later_invalid_price_persists_incomplete_evidence_before_planning(isolated_run, source):
    run = isolated_run
    if source == 'earn':
        run.spot.pop()
        run.earn.append(SimpleEarnPosition(product_id='synthetic', asset='TEST',
            total_amount=2, redeemable_amount=2, can_fast_redeem=True))
    run.prices.extend([{'TEST': 3}, {'TEST': 0}])
    assert app.run_rebalance(run.args) != 0
    assert run.prices == []  # Both retrievals must have been reached.
    snapshots = load_portfolio_snapshots(run.db)
    assert any(item['phase'] == 'before' and item['data_quality'] == 'incomplete'
               and 'TEST' in item['missing_prices'] and item['run_id'] != 'unknown'
               for item in snapshots)
    assert run.actions == []


def test_ld_alias_with_matching_earn_and_no_own_price_fails_closed(isolated_run):
    run = isolated_run
    run.spot[:] = [Balance(asset='USDQ', free=100, locked=0),
                   Balance(asset='LDTEST', free=2, locked=0)]
    run.earn.append(SimpleEarnPosition(product_id='synthetic', asset='TEST',
        total_amount=2, redeemable_amount=2, can_fast_redeem=True))
    run.prices.append({'TEST': 3})
    assert app.run_rebalance(run.args) != 0
    assert run.prices == []
    assert run.actions == []
