# Binance Portfolio Rebalancing CLI

Production-ready CLI that connects to Binance Spot, evaluates portfolio drift, optionally refines targets with OpenRouter, and executes or simulates rebalancing trades. Every action is logged to plain-text JSON lines (one file per day) and can be inspected via the built-in `audit` command.

## Features
- Deterministic CLI workflow with dry-run default and rich risk controls (drift, slippage, min-notional).
- Modular architecture: env/config parsing, Binance REST client, portfolio math, execution planner, and audit logger.
- Optional AI target refinement via OpenRouter with guardrails and safe fallbacks.
- Simple Earn automation (optional): consolidate Spot + Earn, consult AI for "maintain vs redistribute", redeem flexible positions, trade, and re-deposit idle balances respecting product limits.
- Macro context enrichment: every run captures crypto market cap/dominance, fear & greed index, and BTC 24h stats to feed the AI decision.
- Plain-text JSON log files (`logs/YYYYMMDD.log`) capture every run/step/order with automatic daily rotation.
- pytest suite covering core math, decision logic, quantity rounding, and client signing.

## Prerequisites
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- Binance API key/secret (spot account) with IP restrictions when possible

## Setup
```bash
uv venv
uv sync
cp .env.example .env  # populate secrets + default parameters
cp config.example.toml config.toml  # adjust bucket mappings if needed
```

## Running
Rebalance (dry-run by default, configurable via `.env`):
```bash
uv run app.py rebalance --profile moderate --drift 0.10 --max-slippage 0.003 \
  --min-notional 10 --targets btc=0.40,eth=0.20,sol=0.15,stable=0.15,alt=0.10 \
  --quote USDT --recv-window 5000
```
Set `--dry-run=false` to actually place orders. All CLI flags mirror Binance REST limits, so tune them to your own compliance needs.

Audit stored runs (summary or full detail):
```bash
uv run app.py audit --limit 10
uv run app.py audit --run-id <run_id_from_previous_command>
```

## Configuration & Security
- Secrets via env vars: `BINANCE_API_KEY`, `BINANCE_API_SECRET`, optional `OPENROUTER_API_KEY`, `MODEL_NAME`, `MODEL_FALLBACK`, `MODEL_SECOND_FALLBACK`, plus `TESTNET=true|false` to switch endpoints. Grant **Spot**, **Universal Transfer**, and **Simple Earn** (Earn API) permissions to the key before running live; Binance rejeita resgates caso essa flag esteja ausente.
- `.env` also controls operational defaults: dry-run flag, profile, drift/slippage/min-notional thresholds, target weights per profile, guardrails, bucket definitions (`BUCKETS_JSON`), and log retention (`LOG_RETENTION_DAYS`). Adjust it instead of editing Python files.
- `config.toml` remains available for bucket overrides (e.g. `stable`, `alt`) if you prefer TOML.
- Keys are never logged; failures are fatal if any mandatory variable is missing.

### Simple Earn automation
- Enable via `SIMPLE_EARN_ENABLED=true`. Use `SIMPLE_EARN_FAST_REDEEM` (default true) to request fast redeems when Binance quotas allow, and `SIMPLE_EARN_EXCLUDE_ASSETS=BTC,BNB,...` to keep specific symbols on Spot.
- Flow per run:
  1. Fetch Spot balances + Simple Earn flexible positions/products, merge snapshots, and send the consolidated view to the AI. If it replies `"maintain"`, the bot stops immediately without touching funds.
  2. When the AI replies `"redistribute"`, redeem all eligible flexible positions (dry-run friendly), refresh Spot balances, and execute the standard rebalance plan.
  3. After trades settle, push every eligible Spot balance back into Simple Earn flexible products, honoring Binance quotas/minimums; amounts that cannot be subscribed stay on Spot for the next cycle.
- Each Earn step is logged (`earn_snapshot`, `earn_redeem`, `earn_subscribe`) alongside the trading/audit entries so the full run remains traceable.

## Logging & Audit
Each run appends JSON lines to `logs/YYYYMMDD.log` (one file per day, rotated by retention window):
- `uv run app.py audit --limit 5` for a quick summary taken from the latest logs.
- `uv run app.py audit --run-id <id>` for detailed steps/orders reconstructed from the log file.
Both dry-run and live executions follow the same audit trail for parity.

## Testing
```bash
uv run pytest
```
Covers weight calculations, drift decisions, rounding rules, target normalization, and Binance signature helpers.

## Safety Checklist
- Use `--dry-run` first and review planned trades + audit log.
- Keep `min-notional`, `max-slippage`, and `drift` aligned with your risk management.
- Re-sync `config.toml` buckets whenever listing of tradable assets changes.
