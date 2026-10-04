# TASK-038: Enable Adaptive With Valid Required Sources

## Objective

Allow the existing adaptive strategy when required macro sources are valid even if optional CoinGecko is unavailable; otherwise retain base profile and CLI settings with an auditable reason.

## Context

See `docs/market-insights.md`, `app.py`, and `adaptive_strategy.py`. This changes live adaptive availability, so preserve healthy-run behavior and all target precedence.

## Test Contract

- Tests: `tests/test_app_adaptive.py` and `tests/test_adaptive_strategy.py`.
- RED: CoinGecko-only error currently suppresses adaptive; a legacy `MacroSnapshot` with no source metadata can still apply default/assumed values.
- Adaptive requires `fear_greed` and `btc_24h` source status `fresh`, correctly typed/ranged values, and decision-time age in inclusive bounds: provider FNG timestamp 0..36h old; local BTC collection time 0..15min old. Reject missing/future timestamps, unknown metadata, booleans/nonfinite values, and invalid data.
- CoinGecko `fresh` plus finite `market_cap_change_24h` supplies the optional guard signal. `cached`, `missing`, `invalid`, or malformed cap yields `None`, marks applied adaptive as degraded, and does not disable it.
- Cover clean legacy `sources={}` failing closed with base profile/CLI settings, full healthy parity, CoinGecko degraded behavior, required-source fallback and explicit audit reason, inclusive/exceeded age boundaries, explicit targets preserved while adaptive drift/slippage/profile still apply, and manager behavior with cap `None` and BTC below -10%.
- Audit has distinct applied `source_quality=full`, applied `source_quality=degraded`, source-quality fallback warning, and adaptive calculation failure.
- Command: `uv run pytest tests/test_app_adaptive.py tests/test_adaptive_strategy.py`.

## Acceptance And Constraints

- Healthy valid inputs produce current targets and profile.
- Only a fresh valid CoinGecko value participates in its existing severe-drop guard; BTC guard remains effective without it.
- No new indicator changes allocations. No live run for validation.
- Clean-context test-contract review completed with Luna medium before implementation; no material policy ambiguity remained.

## Implementation And Verification

- Added fail-closed source assessment at decision time; required Fear & Greed and BTC must be fresh and valid, while unavailable CoinGecko degrades and passes `None`.
- Adaptive calculation remains enabled for full/degraded required-source quality. Explicit targets retain precedence; source-quality fallback preserves base profile, targets, drift, and slippage and is audited as `warning`; actual calculation exceptions remain `failed`.
- Updated the adaptive manager so an absent market-cap signal does not disable the BTC severe-drop guard or alter sentiment-based selection.
- Added overflow handling so unrepresentably large numeric inputs are rejected and optional CoinGecko overflow degrades instead of aborting the run.
- Updated `docs/market-insights.md` to describe the implemented adaptive source-quality behavior rather than the pre-TASK-038 behavior.
- RED evidence: before implementation, manager `None` raised `TypeError`, adaptive integration retained the base profile despite valid required feeds, stale-source integration applied the adaptive profile, and oversized integer conversion raised `OverflowError`.
- Focused verification: `uv run pytest tests/test_app_adaptive.py tests/test_adaptive_strategy.py -q` -> 29 passed.
- Full isolated verification from a temporary working directory: `uv run --project C:\python\binance_dist python -m pytest C:\python\binance_dist\tests -q --basetemp <temp>` -> 127 passed. No live exchange operation; operational SQLite state was not used as test output.
- `git diff --check` and `uv run python -m compileall -q app.py adaptive_strategy.py` passed.
- Independent result audit found one P2 numeric-overflow risk, now fixed with isolated and integrated regression tests. Legacy-snapshot integration and manager-level `None` coverage were added; stale documentation was corrected. Follow-up reviewer confirmed no findings remain.
