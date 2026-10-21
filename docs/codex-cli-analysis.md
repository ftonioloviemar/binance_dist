# Codex CLI analysis candidate

The candidate selects the locally installed Codex CLI for portfolio advice, requesting exactly `gpt-6-luna` with `medium` reasoning effort. The executable is discovered as `codex` on `PATH`, or may be set with `CODEX_CLI_EXECUTABLE`. The timeout defaults to 120 seconds and accepts integers from 1 through 300.

## Provider selection

- `AI_PROVIDER=openrouter` preserves the legacy default and model chain.
- `AI_PROVIDER=codex_cli` invokes the isolated adapter once. An OpenRouter API key is not required, and neither OpenRouter inference nor model refresh is used.
- `AI_PROVIDER=off` uses the deterministic proposed allocation without either AI provider.

The candidate launcher sets `AI_PROVIDER=codex_cli` in a local batch environment and calls rebalance with `--dry-run=true`. It does not forward arguments. `run_prod.bat` and the scheduled task are unchanged. Do not interpret dry-run as an activation or as proof of model availability.

## Advice and audit

The CLI adapter receives the portfolio analysis request on stdin and returns validated structured advice. Existing AI guardrails are applied before the rebalance flow continues. A CLI failure returns the deterministic proposed allocation and `redistribute`, matching the existing failure policy; this does not itself disable trading in a live invocation. `maintain` remains respected.

Audit entries for this provider contain provider, requested model, reasoning effort, duration, outcome, failure code, and fallback status. They intentionally omit rationale, prompt, holdings, raw output, and stderr. Codex CLI diagnostics are suppressed by the adapter.

## Acceptance gates

This candidate is not a production cutover. Before any real inference, complete TASK-056's isolation, authentication, synthetic-call, identity, and independent review gates. Production activation requires separate explicit approval under TASK-057. Until then, use offline tests and fakes only. Never validate the implementation with a live rebalance, redemption, subscription, or scheduler change.
