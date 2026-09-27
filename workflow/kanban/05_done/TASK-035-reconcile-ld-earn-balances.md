# TASK-035: Reconciliar aliases LD de Simple Earn nos snapshots

## Objetivo

Evitar que representações `LD<ativo>` devolvidas junto aos saldos da conta Spot
sejam avaliadas como ativos Spot independentes quando o endpoint Simple Earn já
fornece a posição subjacente, mantendo incompletos aliases sem correspondência.

## Contrato TDD

- Ao construir snapshot, excluir do componente Spot um saldo `LD<ativo>` somente
  se `<ativo>` existir nas posições Simple Earn positivas do mesmo snapshot.
- Manter saldos Spot normais do ativo-base e valorar a posição Earn uma única vez
  no componente Earn.
- Não normalizar nem descartar aliases `LD*` sem posição Earn correspondente;
  preço ausente continua marcando o snapshot `incomplete`.
- A regra afeta somente snapshots financeiros, nunca saldos usados para trades.
- Nenhuma operação live de Binance para validar.

## Verificação

- RED/GREEN: `uv run pytest -q tests/test_performance_integration.py`
- Regressão: `uv run pytest`
- Revisar `git diff --check`, snapshot local read-only e relatório.

## Estado

- Investigação: snapshots recentes listam ausências `LDADA`…`LDUSDT`, enquanto
  os valores Earn já são registrados pelos ativos-base. O parser mantém o nome
  retornado pela API; o builder soma Spot e Earn em fontes distintas.
- Documentação oficial da Binance consultada para diferenciar `LDUSDT` especial
  de simples regra de preço: não se deve presumir conversão genérica 1:1.
- Nenhuma chamada mutável/live será feita.

## Evidência de conclusão

- RED: `uv run pytest -q tests/test_performance_integration.py -k "ld_alias"`
  -> 1 falhou (qualidade `incomplete` para alias que já tinha posição Earn); 1
  passou para alias sem correspondência.
- GREEN focado: `uv run pytest -q tests/test_performance_integration.py`
  -> 10 passed.
- Regressão: `uv run pytest` -> 84 passed.
- Relatório histórico read-only (`uv run python app.py performance --days 30 --json`)
  segue incomplete para 24h/7d/30d; snapshots persistidos não contêm quantidades
  Spot cruas suficientes para reconstituí-los com segurança. A correção deve ser
  observada nos próximos snapshots.
- `git diff --check` limpo; nenhum trade, redeem ou subscribe live executado.
- Revisão independente por subagente não aplicada: correção localizada com teste
  direto e contrato facilmente verificável; custo de delegação não reduziria risco.
