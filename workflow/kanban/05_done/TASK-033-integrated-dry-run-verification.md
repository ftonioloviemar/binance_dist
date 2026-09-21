# TASK-033: Verificação integrada da análise financeira

## Evidência

- Comando: `uv run python app.py rebalance --dry-run=true --adaptive --cost-gate-mode observe`.
- Run: `7c6e041dc5f04b1a8bb706085dd33ff7`.
- Resultado: `completed`, cinco trades simulados, nenhum trade real.
- Audit confirmou `portfolio_snapshot` before/after e `cost_gate=uncalibrated`
  com `allowed=true` em observe.
- `performance --days 30 --json` retornou os três horizontes, com mudança
  observada, hold e `attribution_status=not_attributed`.
- A qualidade ficou `incomplete` para posições Simple Earn `LD*` sem preço;
  isso é limitação de dados explicitamente registrada, não ganho inventado.

## Verificação

- `uv run pytest -q` -> 74 passed.
- `git diff --check` passou.
