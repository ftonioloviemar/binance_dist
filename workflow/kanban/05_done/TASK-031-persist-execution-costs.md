# TASK-031: Persistir custos e agregá-los no relatório

## Objetivo

Tornar comissão, notional preenchido e custo em bps consultáveis junto aos
snapshots, permitindo avaliar se o rebalanceamento gerou benefício observável
maior que seu custo conhecido.

## Contrato TDD

- Persistir um registro por ordem real processada.
- Não persistir custo de dry-run como custo efetivo.
- Agregar comissão convertida e notional por horizonte.
- Manter contagem de conversões desconhecidas.
- Não rotular diferença como lucro sem fluxo reconciliado.

## Verificação

- `uv run pytest -q tests/test_execution_cost_store.py`
- `uv run pytest -q`
- CLI JSON continua read-only.

## Evidência de conclusão

- RED confirmado: não havia persistência de custos de execução.
- GREEN: `uv run pytest -q tests/test_execution_cost_store.py` -> 1 passed.
- Regressão: `uv run pytest -q` -> 74 passed.
- Smoke JSON do relatório passou e continua reportando `no_data` quando não há
  snapshots no banco atual.
