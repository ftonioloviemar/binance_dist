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

This candidate is not a production cutover. TASK-056's isolated synthetic-call acceptance is documented below. Production activation requires separate explicit approval under TASK-057. Until then, never validate the implementation with a live rebalance, redemption, subscription, or scheduler change.

### User authorization for TASK-056 synthetic inference

On 2026-10-24, the user authorized as many synthetic Codex CLI inferences as are needed to diagnose and complete TASK-056, without asking for authorization again for each call. This covers only the fixed synthetic/replay context, the isolated adapter using `gpt-6-luna` at medium reasoning effort, and sanitized diagnostics. It does not authorize production activation, scheduler changes, live Binance or Simple Earn calls, or changing the model/strategy. TASK-057 still requires its own concrete rollout review and approval. No inference payload, rationale, auth contents, or raw OS error text may be persisted in project evidence.

## TASK-056 evidence (history through 2026-10-24)

The historical entries below are superseded on 2026-10-24 by the user's continuous authorization for as many isolated synthetic TASK-056 inferences as needed. They do not authorize production, scheduler, Binance, or Simple Earn changes. The latest diagnosis found a `git.exe` descendant of the Codex invocation holding a temporary file; see the latest evidence entry below.

- The synthetic replay covers six fixed cases with frozen balances, prices, filters, adaptive-source timing, proposed/final targets, and dry-run order details. The fake client rejects real order and Earn calls; Codex analysis and macro retrieval are stubbed, and OpenRouter inference/refresh are forbidden.
- Focused replay: 6 passed. Offline analyzer/helper and candidate launcher: 13 passed. Full suite: 340 passed, 7 existing failures in adaptive/config tests. `git diff --check` passed. Independent review found and closed missing assertions for adaptive targets/trades and duplicate-order counts.
- Under `VIEMAR\ftoniolo`, a run-directory probe created with Python `tempfile.mkdtemp` under `C:\Windows\Temp` had a restricted DACL for the owner, SYSTEM, and Administrators; its `codex-home` child and a new file inherited that restriction. The probe contained no credentials and was removed.
- The default Codex home was present and its `auth.json` existed; its contents were not read. After explicit user approval, the runner now copies `auth.json` into the restricted temporary Codex home rather than sharing its file identity. The copy is removed with the temporary directory; the CLI may mutate only that temporary copy. This leaves transient local secret exposure as a known tradeoff.
- Read-only Task Scheduler inspection found the existing `binance_dist` task uses the current user's SID and `Interactive` logon, launching `C:\python\binance_dist\run_prod.bat` from that checkout. The current shell resolves `codex` on `PATH`; the task was not started, so its effective PATH and runtime authentication access remain unverified. No task settings or launcher were changed.
- Historical record (superseded by the latest acceptance evidence below): Real adapter call 1 returned `process_start_error` in 5.72 seconds. Call 2 returned `cleanup_error` in 5.813 seconds under old ambiguous stage handling. The next synthetic calls returned sanitized cleanup failures, and at that stage the exact cause and accepted response were unknown. Offline follow-up distinguished a workspace proven retained (`cleanup_workspace_retained`) from a state that could not be verified (`cleanup_state_unknown`). On 2026-10-24, a Python invocation exited 1 without a sanitized result; whether it reached `codex exec` was unknown. After the user requested another attempt following a Codex update/restart, local CLI version was `0.164.0-alpha.11.1`; the isolated adapter returned `cleanup_resource_busy` in 3.734 seconds. A Windows scratch probe reproduced `WinError 32`; the bounded cleanup retry and reaper were subsequently added. At the time, no further inference was authorized; the user later authorized unlimited synthetic TASK-056 calls in the scope above. The exact effective model identity remains unavailable from the CLI.
- Offline diagnostics classify Windows permission (`winerror=5`) and sharing/busy (`winerror=32/33`) failures separately, with static sanitized details; sharing/busy takes precedence over errno `EACCES` because Windows maps sharing violations that way. A non-inference `codex --version` run in the same isolated-temp pattern exited 0 and cleaned its workspace normally; it does not reproduce the inference cleanup failure.
- Focused adapter/replay/launcher tests: 36 passed. Full suite after these changes: 357 passed, with the same 7 known baseline failures (6 adaptive tests and 1 config test). `git diff --check` passes. Independent audit approved cleanup error classification and confirmed other stages remain unchanged.
- Production remains unchanged. `C:\python\binance_dist` is clean on `master` at `fe37b5d`; it contains only the planning commit, not the candidate implementation. Its `.env` has no `AI_PROVIDER` entry. The proposed deployment is to advance the production checkout with reviewed implementation commits, then add `AI_PROVIDER=codex_cli` while preserving `OPENROUTER_API_KEY` and the existing `run_prod.bat` / scheduled task. Rollback is restoring the prior production revision and removing the new provider selection. Do not apply until TASK-056 is accepted and the exact rollout is reviewed.
- Historical diagnosis before the fix (superseded): On 2026-10-24 the user authorized as many synthetic TASK-056 inferences as needed, without per-call confirmation. After adding bounded cleanup backoff, one inference was accepted, while five more returned `cleanup_sharing_violation`. Restart Manager identified `Git for Windows` holding a file in the temporary run directory on all five cleanup attempts; Toolhelp showed its process chain ending at the PID of that same `codex exec`, proving a Git descendant survived the CLI root. `taskkill /T` against an already exited root failed to reach an orphan child in a synthetic reproduction. At the time, the reaper was still the next change and stability remained unproven. Task Scheduler effective PATH/auth remain unverified. Production and its launcher are unchanged; TASK-057 still requires a separate concrete rollout approval.

### Latest acceptance evidence (2026-10-24; supersedes earlier pending/failed status)

The root cause was a `git.exe` descendant of the specific `codex exec` process retaining a file in the temporary run directory after the CLI root exited. The adapter now snapshots descendants after exit, pins process handles, revalidates ancestry, terminates verified descendants bottom-up, and performs bounded cleanup retries within the absolute deadline. This avoids acting on an unrelated process or a reused PID.

Three consecutive isolated synthetic inferences using the fixed context, requested model `gpt-6-luna`, and medium effort returned accepted structured responses. Sanitized run record:

| Run | Duration | Structured response accepted | Descendant handles terminated | Cleanup busy error |
|---|---:|---|---:|---|
| 1 | 4.219 s | Yes | 3 | No |
| 2 | 3.578 s | Yes | Included in combined 9 for runs 2–3 | No |
| 3 | 4.125 s | Yes | Included in combined 9 for runs 2–3 | No |

Across the three runs, 12/12 observed descendant handles were terminated and there were zero cleanup busy/sharing errors. The per-run split of the nine handles in runs 2–3 was not retained and is intentionally not inferred. No prompt, rationale, holdings, raw output, credentials, or raw OS error text was persisted. The CLI did not expose an independent effective-model identity; only the requested model is known. The existing scheduled task's effective PATH and authentication access remain unverified.

Verification after the reaper: focused adapter/replay/launcher suite, 46 passed. Full suite, 367 passed and 7 known baseline failures (6 in `tests/test_app_adaptive.py`, 1 in `tests/test_config.py`). `git diff --check` passed. Production checkout, scheduled task, and live Binance/Earn paths were not changed or invoked. TASK-056 synthetic inference authorization remains open-ended for this fixed synthetic context and sanitized diagnostics; TASK-057 still requires a separate concrete rollout approval.
