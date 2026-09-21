# TASK-025: Persistir snapshots financeiros

## Objetivo

Criar a base persistente para comparar o estado da carteira antes e depois de
cada rebalanceamento, separando Spot e Simple Earn e sem chamar estimativa
incompleta de lucro.

## Contrato TDD

- Persistir snapshots em SQLite sob `state/` por padrão.
- Armazenar valores monetários como texto decimal para evitar arredondamento
  binário no registro financeiro.
- Agregar ativos por origem (`spot` e `earn`) e registrar o valor total.
- Marcar `incomplete` quando houver saldo positivo sem preço conhecido.
- Repetir `(run_id, phase)` deve ser idempotente.
- Não armazenar chaves, saldos de autenticação ou outros segredos.

## Verificação

- RED: `uv run pytest -q tests/test_performance_store.py`
- GREEN: mesmo comando, depois `uv run pytest -q`
- Critério: todos os testes passam e o arquivo SQLite é criado somente no
  caminho fornecido pelo chamador.

## Escopo fora deste cartão

- Conversão estruturada de comissões e taxas.
- Reconciliação de depósitos/saques.
- CLI `performance` e bloqueio por custo.

## Evidência de conclusão

- RED confirmado: módulo inexistente gerou `ModuleNotFoundError`.
- GREEN: `uv run pytest -q tests/test_performance_store.py` -> 3 passed.
- Regressão: `uv run pytest -q` -> 57 passed.
- Commit: registrado após revisão do diff.
