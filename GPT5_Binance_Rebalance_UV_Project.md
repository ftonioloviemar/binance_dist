# GPT-5 HIGH — Binance Portfolio Rebalancing App (uv project)

You are a **senior Python engineer and DevOps**. Build a **production-ready CLI app** that rebalances a Binance Spot portfolio **on demand** (manual run) or later by external scheduling (cron/systemd — do NOT implement the scheduler now).

---

## 🎯 GOAL
Connect to my Binance account via API, fetch current asset status, analyze portfolio (moderate growth profile), optionally refine targets through an **AI call using OpenRouter**, decide whether to keep or adjust allocation, and if necessary, execute a rebalance.  
Every step must be **logged** (CSV + SQLite).

---

## ⚙️ TECH STACK
- **Python 3.11+**
- **uv package manager only (no pip)**  
- Use `uv init`, `uv venv`, `uv add`, `uv run`, etc.  
- Dependencies: `requests`, `websockets`, `python-dotenv`, `pytest`, `pydantic` or `msgspec`, `tomli` / `tomllib`
- Standard library for everything else.
- Typed and `mypy`-clean.
- **No async required** — prefer simple, robust flow.

---

## 🔐 SECURITY & CONFIG
- Read secrets from environment:
  - `BINANCE_API_KEY`
  - `BINANCE_API_SECRET`
  - `TESTNET=true|false` → use `https://testnet.binance.vision` if true
  - optional: `OPENROUTER_API_KEY`, `MODEL_NAME`
- Never print secrets.  
- Fail fast if missing any key.  
- Restrict keys by IP in Binance whenever possible.

---

## 🧰 CLI INTERFACE
Example:
```bash
uv run app.py --dry-run --profile moderate --drift 0.10 --max-slippage 0.003   --min-notional 10 --targets btc=0.40,eth=0.20,sol=0.15,stable=0.15,alt=0.10   --quote USDT --recv-window 5000
```
Arguments:
- `--dry-run` (default true) simulate only  
- `--profile {moderate,aggressive,conservative}` (default moderate)  
- `--targets` manual weights (sum≈1)  
- `--drift` threshold (absolute 0.10 = 10 p.p.)  
- `--max-slippage` allowed fraction  
- `--min-notional` respect exchange rules  
- `--quote` (quote asset, default USDT)  
- `--recv-window` (5000 ms default)

---

## 🧩 MODULES
### `config.py`
- Load env and endpoint (prod/testnet)
- Parse target mapping from `config.toml`
- Provide utility for bucket to symbol mapping

### `binance_client.py`
- Signed REST helpers (HMAC-SHA256)  
- Handle timestamp, recvWindow, rate limits, retries  
- `get_exchange_info()`, `get_account_balances()`, `get_prices()`  
- `place_order()` with `newClientOrderId` for idempotency  
- Respect LOT_SIZE, MIN_NOTIONAL, PRICE_FILTER

### `portfolio.py`
- `compute_current_weights(balances, prices, quote)`  
- `propose_targets(profile|explicit)`  
- `ai_refine_targets(context, current, proposed)` → call OpenRouter (optional)  
- `decide_rebalance(current, target, drift)` → (bool, deltas)  
- `build_trades(deltas, prices, filters, min_notional, max_slippage)`

### `execution.py`
- Execute market or limit orders depending on slippage estimation  
- Fetch fills and store results  

### `logging_audit.py`
- SQLite tables: runs / steps / orders  
- Mirror logs to CSV (`logs/YYYYMMDD_run.csv`)  
- Log each action and exception with timestamp  

### `main(app.py)`
- Parse CLI args, load config, call modules in order  
- Pretty console summary: before vs after weights and total value  

---

## 📊 DEFAULT TARGETS – Moderate Growth
| Symbol | Weight | Notes |
|---------|---------|-------|
| BTC | 0.40 | Base store of value |  
| ETH | 0.20 | Core layer 1 |  
| SOL | 0.15 | Growth exposure |  
| STABLE (USDT) | 0.15 | Liquidity |  
| ALT bucket | 0.10 | BNB / AVAX / ADA |  

Config example (`config.toml`):
```toml
[buckets]
stable = ["USDT"]
alt = ["BNB", "AVAX"]
```

---

## 🤖 AI REFINEMENT (OpenRouter)
If `OPENROUTER_API_KEY` exists:
- Send compact context (current weights, PnL, volatility approx.)
- Ask: “Return JSON with adjusted target weights for moderate growth (±5 p.p.), sum=1, with rationale.”
- Validate JSON; fallback to defaults on error.
- Guardrails: `stable ≥ 10%`, `btc ≥ 25%`.

---

## 🔄 REBALANCE DECISION
- Compute |current − target| for each asset.  
- Trigger if any > `drift` or stable < 10%.  
- Recompute after rounding; skip tiny orders < min notional.  

---

## 💰 ORDER PLANNING
- Use quote pairs (e.g. BTCUSDT).  
- Estimate slippage (approx spread).  
- If slippage > `max-slippage`, use LIMIT order with protective price.  
- Apply exchange filters (LOT_SIZE, MIN_NOTIONAL, PRICE_FILTER).  

---

## 🧾 LOGGING
Every run must record: 
- Config snapshot  
- Balances and prices  
- Targets and AI rationale (if used)  
- Drift decision  
- Planned orders and final fills  
- Exception tracebacks  

---

## 🧪 TESTS
Create minimal pytest suite:
- Weight calculation  
- Drift decision  
- Quantity rounding vs filters  
- AI JSON schema validation  
- Mock Binance client (no real calls)

---

## 📦 DELIVERABLES
```
app.py
config.py
binance_client.py
portfolio.py
execution.py
logging_audit.py
requirements.txt
config.example.toml
.env.example
README.md
tests/
```
`README.md` → explain setup, dry-run usage, safety checklist, sample output.  

---

## ⚠️ IMPLEMENTATION NOTES
- Use `uv init` to create the project structure.  
- Create environment: `uv venv`  
- Add dependencies: `uv add requests python-dotenv pytest pydantic tomli`  
- Sign requests with HMAC-SHA256 over URL-encoded query.  
- Handle errors −1021 (timestamp), 429/418 (rate limit).  
- Use unique `newClientOrderId=f"rebalance_{int(time.time()*1000)}_{symbol}"`.  
- After execution, fetch balances again and print final weights.  
- Keep total under ≈ 500 LOC, typed, documented, clean.  
- Default `--dry-run` = true; require explicit `--dry-run=false` to trade.  

Deliver concise, well-commented, production-grade code ready to run.
