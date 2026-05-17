# Strategy Improvement Options

This document is for choosing the next strategy experiment. It is not financial advice and should not be implemented live without a backtest and explicit approval.

## Current Baseline

Observed behavior from recent logs:

- AI directive returned `redistribute` in the last 30 analyzed runs.
- The drift gate skipped 9 runs and adjusted 20.
- Several adjusted runs still produced many Binance `NOTIONAL` rejections.
- No recent run showed an `adaptive_strategy` audit step, so the adaptive layer is not yet producing observable practical effect.

The first priority is execution quality: fix audit, notional planning, and adaptive observability before tuning for gains.

## Evidence From Research

- Binance Spot filters define `LOT_SIZE`, `MIN_NOTIONAL`, `NOTIONAL`, and `MARKET_LOT_SIZE`; orders must satisfy quantity and notional rules before submission. Source: https://developers.binance.com/docs/binance-spot-api-docs/filters
- Binance Simple Earn flexible redeem has an account rate limit of `1/3s` and requires Spot/Margin trading permission for the API key. Source: https://developers.binance.com/docs/simple_earn/flexible-locked/earn/Redeem-Flexible-Product
- Recent crypto rebalancing research emphasizes transaction costs, downside risk, and allocation stability rather than naive frequent trading. Source: https://www.mdpi.com/2071-1050/17/13/5886
- Crypto momentum evidence is mixed; recent work reports that unmanaged crypto momentum can have severe tail risk, while volatility management may improve payoffs but still leaves heavy-tail uncertainty. Source: https://link.springer.com/article/10.1007/s11408-025-00474-9
- Comparative crypto rebalancing studies commonly test time-based and threshold-based rebalancing with thresholds such as 5%, 10%, and 15%. Source: https://econpapers.repec.org/paper/gtrgatrjs/jfbr220.htm

## Scenarios

| Scenario | Idea | Expected upside | Main risk | Implementation cost | Best use |
| --- | --- | --- | --- | --- | --- |
| A. Execution baseline | Only make current strategy execute cleanly: no audit crash, no invalid orders, adaptive visible. | Low to medium: captures intended allocation instead of losing effect to rejected orders. | Does not add alpha by itself. | Low | First milestone |
| B. Threshold + volatility guard | Rebalance only when drift exceeds a volatility/cost-aware threshold. Raise threshold when volatility/cost is high; lower it when drift is large and tradable. | Medium: fewer wasteful trades, better realized allocation. | Can under-react during fast regime shifts. | Medium | Best next experiment |
| C. Regime allocation | Defensive targets in Fear/Extreme Fear; offensive tilt in Greed, with caps and cooldowns. | Medium to high if regime signal is useful. | Whipsaw and overfitting to Fear & Greed. | Medium | After adaptive observability is fixed |
| D. Momentum overlay | Tilt toward assets with positive trend/momentum, scaled down during high volatility. | High theoretical upside. | Mixed evidence and large tail risk in crypto momentum. | Medium to high | Backtest only before live |
| E. Risk parity / HRP | Allocate by realized volatility/correlation instead of fixed weights. | Medium risk-adjusted improvement, lower drawdown. | May miss upside in concentrated bull markets. | High | If drawdown control matters more than max gain |
| F. Yield-first stable allocation | Keep stable allocation earning yield when not needed for trades. | Low to medium steady carry. | Liquidity, redemption delay, product limits, platform risk. | Medium | Useful complement, not core alpha |

## Recommendation

Choose Scenario B after TASK-001 through TASK-003.

Reasoning:

- It directly addresses the current practical problem: churn, rejected small orders, and too-frequent small reallocations.
- It can be tested with existing logs and portfolio math before live use.
- It does not depend on a fragile claim that sentiment or momentum will predict returns.
- It creates a cleaner base for later Scenario C or D experiments.

Scenario B was selected on 2026-05-17. The first non-live replay harness is documented in `docs/strategy-scenario-b.md`.

## Suggested Backtest Matrix

Test at least these variants before changing live strategy:

- Current fixed drift baseline.
- Thresholds: 1%, 3%, 5%, 10%.
- Volatility-adjusted thresholds: base threshold multiplied by 7-day or 30-day realized volatility regime.
- Cost-aware threshold: skip if expected trade value is below Binance notional plus estimated fees/slippage.
- Regime overlay: Fear/Neutral/Greed target sets with 24h or 7d cooldown.
- Momentum overlay: 30/90-day trend tilt with volatility cap.

Metrics:

- Total return.
- Max drawdown.
- Sharpe or Sortino.
- Turnover.
- Number of orders.
- Number of skipped/rejected orders.
- Time in USDT/stables.
- Earn idle yield estimate when stable allocation is parked.

## Decision Needed

Pick one:

1. Scenario B first: threshold plus volatility/cost-aware guard.
2. Scenario C first: make sentiment/regime allocation the main alpha lever.
3. Scenario D first: momentum overlay, but backtest-only until proven.
4. Backtest A/B/C/D together before selecting.
