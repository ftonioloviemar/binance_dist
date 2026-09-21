# TASK-028: Comparar hold e registrar fluxo externo

## Objetivo

Criar comparação financeira honesta para os snapshots: mudança observada,
benchmark hipotético de manter a carteira e estado de atribuição de fluxos.

## Contrato TDD

- Reconstituir o valor de hold usando quantidades implícitas do snapshot inicial
  e preços do snapshot final.
- Não chamar mudança de valor de lucro quando fluxos externos não estiverem
  reconciliados.
- Marcar benchmark como indisponível se faltar preço de ativo relevante.
- Persistir fluxos externos como registros explícitos, sem inventar integração
  com endpoint Binance que ainda não existe no cliente.

## Verificação

- `uv run pytest -q tests/test_performance.py`
- `uv run pytest -q`

## Evidência de conclusão

- RED confirmado: comparação e armazenamento de fluxo ainda não existiam.
- GREEN: `uv run pytest -q tests/test_performance.py` -> 3 passed.
- Regressão: `uv run pytest -q` -> 66 passed.
- Sem fluxo reconciliado, o resultado é `not_attributed` e `profit` permanece
  `null`.
