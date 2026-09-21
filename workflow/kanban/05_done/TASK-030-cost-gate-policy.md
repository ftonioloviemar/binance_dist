# TASK-030: Política de custo observável e bloqueável

## Objetivo

Adicionar o mecanismo de decisão que compara benefício esperado e custo
estimado, inicialmente em `observe` e sem ativar bloqueio em produção.

## Contrato TDD

- Modos válidos: `off`, `observe`, `enforce`; padrão `observe`.
- Valores ausentes ou não calibrados produzem `uncalibrated` e nunca bloqueiam.
- Em `observe`, registrar decisão mas sempre permitir o plano.
- Em `enforce`, bloquear somente quando benefício/custo/threshold estiverem
  completos e o benefício líquido ficar abaixo do mínimo configurado.
- Configuração vem de CLI/env e entra no snapshot da rodada.

## Verificação

- `uv run pytest -q tests/test_cost_gate.py`
- `uv run pytest -q`
- Smoke dry-run sem `enforce`.

## Evidência de conclusão

- RED confirmou ausência do mecanismo e regressão de namespaces legados sem os
  novos campos.
- GREEN: `uv run pytest -q tests/test_cost_gate.py tests/test_config.py tests/test_app_adaptive.py` -> 19 passed.
- Regressão: `uv run pytest -q` -> 73 passed.
- O app registra `cost_gate=uncalibrated` por padrão e não bloqueia enquanto não
  houver benefício/custo calibrados.
