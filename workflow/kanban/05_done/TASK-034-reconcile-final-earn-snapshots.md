# TASK-034: Reconciliar snapshots finais de Simple Earn

## Objetivo

Evitar dupla contagem de posições Simple Earn resgatadas no snapshot `after` e
impedir que o relatório apresente variação observada quando os snapshots usados
não têm qualidade completa.

## Contexto

`app.py` captura `simple_earn_positions` antes das operações, grava o snapshot
final com esses dados antigos e só depois tenta subscrever saldos Spot ao Earn.
Em duas execuções locais de 2026-09-23/24, audits registram resgates e
subscrições concluídos, enquanto os snapshots `after` mantêm Earn e acrescentam
um valor semelhante em Spot. O relatório de 24h mostrou `observed_change` de
`+710.72 USDT` apesar de `profit=null`.

## Contrato TDD

- RED: integração do fluxo final deve mostrar que `after` é salvo depois das
  subscrições e usa as posições Spot e Earn atualizadas, sem reutilizar a lista
  Earn anterior ao resgate.
- Cobrir resgate total, saldo parcialmente subscrito, falha ao atualizar Earn e
  dry-run sem chamadas mutantes.
- Se a consulta pós-operação de Spot ou Earn falhar, não usar posições Earn
  antigas como atuais; persistir qualidade `incomplete` ou omitir snapshot,
  registrando a falha no audit.
- Se o saldo Spot pré-subscrição não puder ser atualizado após trades, pular a
  subscrição live em vez de reutilizar saldos antigos.
- Relatórios não devem expor `observed_change`/`hold_change` calculados de
  snapshots com qualidade diferente de `complete`.
- Manter intactos o planejamento de trades, estratégia e operações live fora
  do fluxo já existente. Nenhuma chamada live para validar a alteração.

## Verificação

- RED/GREEN: `uv run pytest -q tests/test_performance_integration.py tests/test_performance_report.py`
- Regressão: `uv run pytest` com chaves fictícias de teste, `DEFAULT_MIN_NOTIONAL_UPLIFT_TOLERANCE=0.10` e `LOG_RETENTION_DAYS=0` -> 82 passed.
- Revisar ordem das chamadas fake, qualidade em falha, dry-run e ausência de
  dependência de rede.

## Estado

- Investigação somente leitura confirmou a causa no caminho final e nos audits.
- RED reproduzido: snapshots incompletos ainda geravam deltas numéricos e uma
  qualidade explicitamente `complete` ignorava preços ausentes.
- GREEN: regressões do snapshot, persistência e relatório -> 19 passed.
- Audits confirmam `dry_run=false` e resgate/subscrição concluídos nos runs
  `9dfc5785` e `1f811296`. Os `after` foram marcados `incomplete`, preservando
  valores, quantidades e demais campos. Backup anterior:
  `C:\python\binance_dist\state\performance.db.TASK-034-20260924T1520Z.bak`.
- Relatório no SQLite atual: horizontes 24h/7d/30d com status `incomplete`,
  `observed_change=null` e `hold_change=null`.
- Revisão independente aprovada; sem chamadas live. `git diff --check` limpo.
