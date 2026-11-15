# TASK-066: Isolate Adaptive Tests from Real Credentials

## Objective

Make the five adaptive integration tests deterministic and runnable with Binance credentials absent, while preserving their existing audit/fallback assertions.

## Scope and safety

- Identify the single adaptive-failure test and four required-macro-source variants that fail before fake-client construction because `load_env_settings` reads credentials.
- Patch the settings loader with synthetic `EnvSettings` in those tests; retain fake clients and fake macro/advice providers.
- Do not read `.env`, expose or inject real credentials, call external providers, weaken assertions, or alter production behavior.

## TDD and verification

- Terra/medium authors or adjusts the tests before implementation.
- Luna/medium runs RED/GREEN and regression tests under socket/DNS fence with credential variables absent.
- Run the focused adaptive cases and full suite offline; verify failures are zero or explicitly classify unrelated baseline failures. Run `git diff --check`.
- Independent Terra/medium review, maximum three rounds; commit this card separately.

## Acceptance

- All five previously credential-blocked tests exercise their intended code paths with synthetic settings.
- No test accesses actual API keys or external endpoints; existing behavioral expectations remain intact.
- Card and verification evidence are committed independently.

## Evidence

- Terra updated only `tests/test_app_adaptive.py`, injecting synthetic `EnvSettings` in the five named cases without changing assertions.
- Offline focused run with socket/DNS blocked and credentials absent: 5 passed, 26 deselected.
- Full offline suite with socket/DNS blocked: 512 passed, 1 failed. The only failure is the known anti-churn fixture issue tracked separately; it is not attributed to this test-only card.
- Independent review pending; no credentials or external calls used.

- Independent Terra review approved with no findings. Full suite failure is isolated to TASK-067 anti-churn fixture. Tests use no real keys/network.
