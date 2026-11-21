from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

import app
from binance_client import Balance, SimpleEarnPosition
from config import EnvSettings
from portfolio import RebalanceDecision


@pytest.mark.parametrize('alias_price', [None, 0.0, float('nan'), 99.0],
                         ids=['missing', 'zero', 'nan', 'positive'])
def test_after_snapshot_matched_ld_alias_is_ignored_without_double_counting(
    monkeypatch, alias_price
):
    spot = [Balance(asset='USDQ', free=10, locked=0),
            Balance(asset='LDTEST', free=2, locked=0)]
    earn = [SimpleEarnPosition(product_id='synthetic', asset='TEST',
        total_amount=2, redeemable_amount=2, can_fast_redeem=True)]
    steps = [{'name': 'earn_redeem', 'status': 'completed', 'detail': 'synthetic'}]
    seen_balances = []

    class Auditor:
        def log_step(self, **kwargs):
            steps.append(kwargs)

    class Client:
        def get_account_balances(self):
            return spot

        def get_simple_earn_flexible_positions(self):
            return earn

    def fetch_prices(client, balances, targets, quote):
        seen_balances.extend((balance.asset, balance.total) for balance in balances)
        prices = {'TEST': 3}
        if alias_price is not None:
            prices['LDTEST'] = alias_price
        return prices

    monkeypatch.setattr(app, '_fetch_asset_prices', fetch_prices)
    result = app._build_post_trade_performance_snapshot_payload(
        client=Client(), auditor=Auditor(), run_id='synthetic', quote='USDQ',
        spot_balances=spot, earn_positions=earn, prices={'TEST': 3}, targets={},
        timestamp='2026-01-01T00:00:00Z', products_by_asset={},
        simple_earn_enabled=True, dry_run=False, spot_balances_fresh=True,
        pendings=[],
    )

    result = result.payload
    assert [(balance.asset, balance.total) for balance in spot] == [
        ('USDQ', 10), ('LDTEST', 2)]
    assert result['phase'] == 'after'
    assert result['spot_value'] == '10.00'
    assert result['earn_value'] == '6.00'
    assert result['total_value'] == '16.00'
    assert 'spot:LDTEST' not in result['asset_values']
    assert steps[0] == {'name': 'earn_redeem', 'status': 'completed', 'detail': 'synthetic'}
    assert not any('revert' in str(step).lower() or 'rollback' in str(step).lower()
                   for step in steps)
    assert result['asset_values']['earn:TEST'] == '6.00'
    assert result['data_quality'] == 'complete'
    assert result['missing_prices'] == []


@pytest.mark.parametrize('alias_price', [None, 0.0], ids=['missing', 'zero'])
def test_run_persists_complete_after_snapshot_for_matched_ld_alias(
    monkeypatch, tmp_path, alias_price
):
    monkeypatch.chdir(tmp_path)
    persisted = []
    steps = []
    final_status = []
    actions = []
    initial = [Balance(asset='USDQ', free=10, locked=0)]
    after = [*initial, Balance(asset='LDTEST', free=2, locked=0)]
    earn = [SimpleEarnPosition(product_id='synthetic', asset='TEST',
        total_amount=2, redeemable_amount=2, can_fast_redeem=True)]

    class Auditor:
        run_id = 'synthetic-run'

        def start_run(self, **kwargs):
            pass

        def log_step(self, **kwargs):
            steps.append(kwargs)

        def log_exception(self, **kwargs):
            steps.append({'name': 'exception', **kwargs})

        def finalize_run(self, status):
            final_status.append(status)

        def close(self):
            pass

    class Client:
        def __init__(self, **kwargs):
            self.spot_calls = 0

        def get_account_balances(self):
            self.spot_calls += 1
            return initial if self.spot_calls <= 2 else after

        def get_simple_earn_flexible_positions(self):
            return earn

        def get_simple_earn_flexible_products(self):
            return {}

        def get_exchange_info(self):
            return {}

        def close(self):
            pass

    def prices(_client, balances, _targets, _quote):
        result = {'TEST': 3}
        if any(balance.asset == 'LDTEST' for balance in balances) and alias_price is not None:
            result['LDTEST'] = alias_price
        return result

    def redeem(**kwargs):
        actions.append('redeem')
        kwargs['auditor'].log_step(name='earn_redeem', status='completed', detail='completed')

    def execute(**kwargs):
        actions.append('execute')

    monkeypatch.setattr(app, 'BinanceClient', Client)
    monkeypatch.setattr(app, 'AuditLogger', Auditor)
    monkeypatch.setattr(app, 'load_env_settings', lambda recv_window: EnvSettings(
        api_key='fake', api_secret='fake', testnet=True,
        base_url='https://invalid.example', recv_window=recv_window,
        simple_earn_enabled=True, ai_provider='off'))
    monkeypatch.setattr(app, 'fetch_macro_snapshot', lambda: SimpleNamespace(data={}, errors=[], sources={}))
    monkeypatch.setattr(app, '_fetch_asset_prices', prices)
    monkeypatch.setattr(app, '_ensure_target_prices', lambda _client, values, *_args: values)
    monkeypatch.setattr(app, 'record_portfolio_snapshot', lambda _path, payload: persisted.append(payload))
    monkeypatch.setattr(app, '_build_shadow_run', lambda **kwargs: None)
    monkeypatch.setattr(app, 'filter_dust_positions', lambda snapshot, *_args: (snapshot, {}))
    monkeypatch.setattr(app, 'decide_rebalance', lambda *_args: RebalanceDecision(True, {'TEST': 0.5}))
    monkeypatch.setattr(app, 'rebalance_has_tradable_orders', lambda **kwargs: True)
    monkeypatch.setattr(app, 'build_trades', lambda **kwargs: [object()])
    monkeypatch.setattr(app, 'filter_anti_churn_trades', lambda **kwargs: kwargs['trades'])
    monkeypatch.setattr(app, '_redeem_simple_earn_positions', redeem)
    monkeypatch.setattr(app, '_init_available_balances', lambda *_args, **_kwargs: {})
    monkeypatch.setattr(app, '_fetch_fee_reference_prices', lambda *_args: {})
    monkeypatch.setattr(app, 'execute_trades', execute)
    monkeypatch.setattr(app, '_print_summary', lambda *_args: None)
    args = argparse.Namespace(command='rebalance', dry_run=False, profile='moderate',
        drift=0.01, max_slippage=0.003, min_notional=0.0, targets='USDQ=1',
        quote='USDQ', recv_window=5000, config_path=Path('missing.toml'), adaptive=False)

    assert app.run_rebalance(args) == 0
    assert actions == ['redeem', 'execute']
    assert final_status == ['completed']
    assert any(step.get('name') == 'execution' and step.get('status') == 'completed' for step in steps)
    assert any(step.get('name') == 'earn_redeem' and step.get('status') == 'completed' for step in steps)
    assert not any(step.get('name') == 'exception' for step in steps)
    [snapshot] = [item for item in persisted if item['phase'] == 'after']
    assert snapshot['data_quality'] == 'complete'
    assert snapshot['missing_prices'] == []
    assert snapshot['spot_value'] == '10.00'
    assert snapshot['earn_value'] == '6.00'
    assert snapshot['total_value'] == '16.00'
    assert 'spot:LDTEST' not in snapshot['asset_values']
    assert snapshot['asset_values']['earn:TEST'] == '6.00'
    assert not any(step.get('name') == 'prices_snapshot_after' and step.get('status') == 'warning' for step in steps)
    assert any(step.get('name') == 'portfolio_snapshot' and '"phase":"after"' in step.get('detail', '') and '"data_quality":"complete"' in step.get('detail', '') for step in steps)


def test_preplanning_guard_accepts_matched_alias_without_mutating_spot():
    spot = [Balance(asset='USDQ', free=10, locked=0),
            Balance(asset='LDTEST', free=2, locked=0)]
    earn = [SimpleEarnPosition(product_id='synthetic', asset='TEST',
        total_amount=2, redeemable_amount=2, can_fast_redeem=True)]
    auditor = SimpleNamespace(log_step=lambda **kwargs: None)

    app._fail_closed_on_unpriced_holdings(
        auditor=auditor, run_id='synthetic', quote='USDQ',
        spot_balances=spot, earn_positions=earn, prices={'TEST': 3})

    assert [(balance.asset, balance.total) for balance in spot] == [
        ('USDQ', 10), ('LDTEST', 2)]


@pytest.mark.parametrize('price', [None, 0.0, float('nan')],
                         ids=['missing', 'zero', 'nan'])
def test_preplanning_guard_still_blocks_invalid_matched_base_price(monkeypatch, price):
    spot = [Balance(asset='LDTEST', free=2, locked=0)]
    earn = [SimpleEarnPosition(product_id='synthetic', asset='TEST',
        total_amount=2, redeemable_amount=2, can_fast_redeem=True)]
    snapshots = []
    auditor = SimpleNamespace(log_step=lambda **kwargs: None)
    monkeypatch.setattr(app, '_persist_performance_snapshot',
                        lambda _auditor, payload: snapshots.append(payload))

    with pytest.raises(app.PortfolioError):
        app._fail_closed_on_unpriced_holdings(
            auditor=auditor, run_id='synthetic', quote='USDQ',
            spot_balances=spot, earn_positions=earn,
            prices={} if price is None else {'TEST': price})

    assert snapshots[0]['data_quality'] == 'incomplete'
    assert 'TEST' in snapshots[0]['missing_prices']
    assert 'LDTEST' not in snapshots[0]['missing_prices']


@pytest.mark.parametrize('alias,base,amount', [
    ('LDTEST', 'TEST', 0), ('LDTEST', 'OTHER', 2), ('LDUSDT', 'USDT', 0),
])
def test_preplanning_guard_blocks_unmatched_ld_including_ldusdt(
    monkeypatch, alias, base, amount
):
    spot = [Balance(asset=alias, free=2, locked=0)]
    earn = [SimpleEarnPosition(product_id='synthetic', asset=base,
        total_amount=amount, redeemable_amount=amount, can_fast_redeem=True)]
    snapshots = []
    auditor = SimpleNamespace(log_step=lambda **kwargs: None)
    monkeypatch.setattr(app, '_persist_performance_snapshot',
                        lambda _auditor, payload: snapshots.append(payload))

    with pytest.raises(app.PortfolioError):
        app._fail_closed_on_unpriced_holdings(
            auditor=auditor, run_id='synthetic', quote='USDQ',
            spot_balances=spot, earn_positions=earn, prices={base: 3})

    assert snapshots[0]['data_quality'] == 'incomplete'
    assert alias in snapshots[0]['missing_prices']


@pytest.mark.parametrize('alias,base,amount,prices,missing', [
    ('LDTEST', 'TEST', 2, {}, 'TEST'),
    ('LDTEST', 'TEST', 2, {'TEST': 0}, 'TEST'),
    ('LDTEST', 'TEST', 0, {'TEST': 3}, 'LDTEST'),
    ('LDUSDT', 'USDT', 0, {'USDT': 1}, 'LDUSDT'),
])
def test_after_snapshot_fails_closed_for_invalid_base_or_unmatched_alias(
    monkeypatch, alias, base, amount, prices, missing
):
    spot = [Balance(asset='USDQ', free=10, locked=0),
            Balance(asset=alias, free=2, locked=0)]
    earn = [SimpleEarnPosition(product_id='synthetic', asset=base,
        total_amount=amount, redeemable_amount=amount, can_fast_redeem=True)]
    steps = []
    auditor = SimpleNamespace(log_step=lambda **kwargs: steps.append(kwargs))

    class Client:
        def get_account_balances(self):
            return spot

        def get_simple_earn_flexible_positions(self):
            return earn

    monkeypatch.setattr(app, '_fetch_asset_prices', lambda *_args: prices)
    result = app._build_post_trade_performance_snapshot_payload(
        client=Client(), auditor=auditor, run_id='synthetic', quote='USDQ',
        spot_balances=spot, earn_positions=earn, prices=prices, targets={},
        timestamp='2026-01-01T00:00:00Z', products_by_asset={},
        simple_earn_enabled=True, dry_run=False, spot_balances_fresh=True,
        pendings=[])

    assert result.summary_weights is None
    result = result.payload
    assert result['data_quality'] == 'incomplete'
    assert missing in result['missing_prices']
    if amount > 0:
        assert alias not in result['missing_prices']
    assert any(step.get('name') == 'prices_snapshot_after'
               and step.get('status') == 'warning' for step in steps)
    assert [(balance.asset, balance.total) for balance in spot] == [
        ('USDQ', 10), (alias, 2)]
