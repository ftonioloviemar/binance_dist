# Análise Financeira

O rebalanceador mantém snapshots em `state/performance.db`, ignorado pelo Git.
Cada execução pode registrar fases `before` e `after`, valores separados de
Spot/Simple Earn, preços, qualidade do dado e estado de reconciliação de fluxo.

## Comando

```powershell
uv run python app.py performance --days 30
uv run python app.py performance --days 30 --json
```

O relatório mostra as janelas 24h, 7d e 30d. `observed_change` é apenas a
variação de valor entre snapshots. `hold_change` é o contrafactual de manter as
quantidades iniciais nos preços finais. Nenhum dos dois é chamado de lucro
quando `attribution_status` é `not_attributed` ou `incomplete`.

## Custos

Ordens live com resposta FULL persistem notional preenchido, preço médio,
comissão por ativo, conversão para a moeda de cotação quando disponível e
comissão em bps. `conversion_unknown_orders` indica que a comissão não pôde ser
convertida com segurança. Dry-run não é tratado como custo real.

## Política

- `COST_GATE_MODE=observe` é o padrão e registra a decisão sem bloquear.
- `COST_GATE_MODE=off` desabilita o registro decisório do gate.
- `COST_GATE_MODE=enforce` só bloqueia quando benefício esperado, custo e
  `COST_GATE_MIN_NET_BENEFIT_BPS` estiverem calibrados; dados incompletos nunca
  inventam um bloqueio.

Antes de ativar `enforce`, acumule histórico suficiente e valide conversão de
comissões, fluxo externo, turnover e retorno contra o benchmark hold.
