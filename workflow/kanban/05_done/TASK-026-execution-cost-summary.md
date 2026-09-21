# TASK-026: Calcular custo efetivo dos fills

## Objetivo

Transformar a resposta FULL da Binance em um resumo auditável de execução,
sem confundir comissão conhecida com custo total quando a conversão da moeda
da comissão não estiver disponível.

## Contrato TDD

- Somar quantidade e notional preenchidos a partir dos fills.
- Calcular preço médio preenchido.
- Somar comissão por `commissionAsset`.
- Converter comissão para a moeda de cotação somente com preço de referência
  conhecido; do contrário, marcar `conversion_status=unknown`.
- Calcular `commission_bps` somente quando o valor convertido e o notional
  forem conhecidos.
- Manter o resumo serializável e adequado para o detalhe do log de auditoria.
- Aceitar moeda de cotação e preços de referência pelo executor, sem assumir
  `USDT` internamente.

## Verificação

- RED: `uv run pytest -q tests/test_execution_costs.py`
- GREEN: mesmo comando, depois `uv run pytest -q`

## Segurança

Não altera sizing, alocação, ordens ou modo live. O cartão somente mede e
registra o que a exchange devolveu.

## Evidência de conclusão

- RED confirmado: resumo ainda não existia.
- GREEN: `uv run pytest -q tests/test_execution_costs.py tests/test_execution.py` -> 5 passed.
- Regressão: `uv run pytest -q` -> 61 passed.
- A conversão de comissão recebe preços de referência pelo executor; sem eles
  permanece `unknown`.
