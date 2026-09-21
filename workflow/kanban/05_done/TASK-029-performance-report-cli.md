# TASK-029: Relatório de performance por horizonte

## Objetivo

Expor os snapshots persistidos em um comando leve para revisão operacional,
sem depender de logs textuais nem declarar lucro sem fluxo reconciliado.

## Contrato TDD

- Disponibilizar `performance --days 30`.
- Expor janelas de 24h, 7d e 30d quando houver snapshots suficientes.
- Suportar texto humano e `--json`.
- Mostrar valores observados, hold e `attribution_status`.
- Retornar ausência de dados de forma explícita, sem erro ou números inventados.

## Verificação

- `uv run pytest -q tests/test_performance_report.py`
- `uv run pytest -q`
- `uv run python app.py performance --days 30 --json` como smoke read-only.

## Evidência de conclusão

- RED confirmado no smoke: o roteador CLI ainda convertia `performance` em
  `rebalance`.
- GREEN: `uv run pytest -q tests/test_performance_report.py` -> 3 passed.
- Regressão: `uv run pytest -q` -> 69 passed.
- Smoke read-only: `uv run python app.py performance --days 30 --json` retornou
  os três horizontes como `no_data`, sem inventar resultados.
