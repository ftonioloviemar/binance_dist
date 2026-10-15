# TASK-048: Select the account-return methodology

## Decision needed

Choose the canonical return measures and flow-accounting contract before
implementing a claim of actual net portfolio performance.

## Context

TASK-047 (`workflow/kanban/05_done/TASK-047-preserve-commission-conversion-provenance.md`)
now preserves commission assets, conversion evidence, known subtotals, and
unknown causes. It intentionally does not claim that commission subtotals are
the portfolio's net profit.

The existing performance report has no certified complete external-flow
history, so return attribution must stay incomplete when deposits/withdrawals
cannot be reconciled. Snapshot value changes already reflect fees deducted
from holdings; subtracting those fees again would double-count them. Spot/Earn
transfers are internal movements, not external cash flows. Simple Earn yield
can be reflected in total portfolio value, but separate yield attribution
requires a trusted reward history. Slippage cannot be separately measured
without a defined execution benchmark and its timestamped price.

GIPS guidance describes flow-boundary valuations with geometrically linked
subperiod returns as the most accurate time-weighted approach, and Modified
Dietz as an approximation using time-weighted external cash flows when daily
returns are unavailable. These are reference methods, not a claim that this
personal app complies with GIPS:

- [GIPS Standards Handbook for Firms](https://www.gipsstandards.org/standards/gips-standards-for-firms/gips-standards-handbook-for-firms/)
- [GIPS Standards Handbook for Asset Owners](https://www.gipsstandards.org/standards/gips-standards-for-asset-owners/gips-standards-handbook-for-asset-owners/)

## Options

1. **Recommended: dual reporting.** Report quote-currency net P&L from start/end
   total portfolio values less certified net external flows; also report
   Modified Dietz return as an explicitly labeled approximation when flow
   timestamps and period-boundary values are complete. Keep status incomplete
   if flow coverage is not certified. Later, chain subperiod returns where
   reliable valuations at each flow become available.
2. **Flow-boundary time-weighted return only.** Value the portfolio at every
   external flow, calculate each subperiod return, and geometrically link them.
   This is preferable for isolating strategy performance but requires reliable
   flow-time portfolio valuations and may leave more historical horizons
   incomplete.
3. **Net P&L only; no return percentage.** Subtract certified external flows
   from change in total portfolio value and omit a return rate until the app
   has sufficient flow-time valuation data. This is the most conservative and
   simplest initial report.

## Recommendation

Choose option 1, with strict completeness gates. Clearly label Modified Dietz
as approximate; do not silently assume zero flows. Keep incomplete horizons
without a profit/return claim. Optionally add a separate money-weighted IRR only
if the user wants a measure reflecting the timing and size of their own
contributions and withdrawals.

For every option, fees already reflected in portfolio values must not be
subtracted twice. Treat internal Spot/Earn transfers as neutral. Include Earn
assets/yield in total value only when the corresponding snapshots are complete.
Keep slippage and separately attributed Earn yield unreported until their
reference-price and reward-history contracts are defined.

## Human decision

- Selected option: **pending**
- Include a separate money-weighted IRR: **pending**
- Flow completeness source (user-certified ledger/import/API): **pending**

## Resume criteria

- User selects one option and decides whether to add money-weighted IRR.
- Define how complete external-flow coverage is established and represented.
- Define accepted timestamps, valuation boundary, fees treatment, and the
  behavior for missing/ambiguous flows; only then move implementation work to
  `workflow/kanban/02_ready/`.

## Dependency impact

Blocks flow-adjusted performance percentages and any claim that the strategy
is profitable after contributions/withdrawals. It does not block ongoing
commission-conversion provenance, shadow-policy comparisons, or reporting of
clearly labeled observed portfolio value changes.

## Risks and forbidden shortcuts

- Never equate observed value change with profit when external flows are
  unreconciled.
- Never count internal Spot/Earn transfers as external contributions.
- Never subtract an already-realized fee again from snapshot-based P&L.
- Never describe fixed-trajectory fee overlays as realized Binance fees or as
  a full slippage re-simulation.
- Do not query or mutate live exchange data as part of this decision card.
