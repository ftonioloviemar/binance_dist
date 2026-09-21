# TASK-027: Integrar observabilidade financeira ao rebalanceamento

## Objetivo

Persistir o estado financeiro antes/depois da decisão e entregar preços de
referência ao resumo de comissão, sem mudar a estratégia nem habilitar bloqueio.

## Contrato TDD

- Registrar `before` depois da carteira e preços finais de planejamento estarem
  disponíveis.
- Registrar `after` em skip/noop e após execução.
- Marcar pós-execução dry-run como `simulation`.
- Nunca interromper o rebalanceamento por falha do SQLite ou preço de taxa.
- Não inventar conversão quando BNB ou outra moeda de comissão não tiver preço.

## Verificação

- Testes unitários do helper de snapshot/auditoria.
- `uv run pytest -q`.
- Dry-run somente se o ambiente estiver configurado; nenhuma ordem real.

## Evidência de conclusão

- RED confirmado: helper de integração ainda não existia.
- GREEN: `uv run pytest -q tests/test_performance_integration.py tests/test_app_adaptive.py` -> 11 passed.
- Regressão: `uv run pytest -q` -> 63 passed.
- O executor recebe preços de referência sem tornar a ausência de BNB
  conversível um erro de execução.
