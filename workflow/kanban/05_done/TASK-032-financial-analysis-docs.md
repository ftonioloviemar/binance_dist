# TASK-032: Documentar análise financeira e operação segura

## Objetivo

Documentar o novo contrato financeiro, configuração e lições aprendidas para
que a próxima análise use evidência comparável e não trate saldo como lucro.

## Entregáveis

- Guia `docs/financial-performance.md`.
- README e `.env.example` atualizados.
- Glossário e lessons learned atualizados.
- Schema SQLite versionado coerentemente.

## Verificação

- `uv run pytest -q`
- `git diff --check`
- `uv run python app.py performance --days 30 --json`.

## Evidência de conclusão

- Documentação financeira, configuração de exemplo, glossário e lessons learned
  atualizados.
- Schema SQLite elevado para versão 2, cobrindo snapshots, fluxos e custos.
- `uv run pytest -q` -> 74 passed.
- `git diff --check` passou.
- CLI JSON read-only retornou os três horizontes como `no_data` no banco atual,
  sem inventar resultado.
