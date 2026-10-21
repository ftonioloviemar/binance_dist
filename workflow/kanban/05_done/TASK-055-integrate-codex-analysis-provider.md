# TASK-055: Integrar provedor Codex e launcher candidato

Status: concluída. Classificação: TDD. Dependência: TASK-054 concluída; implementação da onda aprovada pelo usuário.

## Objetivo e escopo

Integrar `AI_PROVIDER`, despacho e auditoria em `config.py`/`app.py`; criar `run_codex_candidate.bat`, atualizar `.env.example`, `README.md` e `docs/codex-cli-analysis.md`. Design: `docs/superpowers/specs/2026-10-21-codex-cli-analysis-design.md`. Interfaces: seção TASK-055 de `docs/superpowers/plans/2026-10-21-codex-cli-analysis.md`.

## Contrato RED/GREEN

RED esperado: seletor/validação, despacho Codex e launcher ausentes. Comando: `uv run pytest tests/test_config.py tests/test_app_ai_provider.py tests/test_codex_candidate_launcher.py tests/test_portfolio.py tests/test_openrouter_model_curator.py -q`. Asserts: sem chave OpenRouter ainda usa Codex; zero inferência/curadoria OpenRouter em Codex/off, inclusive falha; maintain e guardrails preservados; fallback determinístico; audit sanitizado; launcher candidato não aceita ativação live por argumentos.

## Aceitação e riscos

Ausência do seletor preserva legado; candidata seleciona Codex explicitamente. `run_prod.bat`, `.env` real e Agendador ficam intactos. Full suite `uv run pytest` e `git diff --check`; especialistas de contrato e auditoria distintos; commit ao concluir. Disco/backup antes de mudanças.

## Evidência

- RED inicial: testes falharam por seletor/helper/launcher ausentes. A auditoria independente identificou que aplicar guardrails ao resultado de falha alterava propostas determinísticas fora dos pisos; teste RED adicional reproduziu BTC=10% / USDT=90% mudando para aproximadamente 21.7% / 78.3%.
- GREEN focado: `uv run pytest tests/test_config.py tests/test_app_ai_provider.py tests/test_codex_candidate_launcher.py tests/test_portfolio.py tests/test_openrouter_model_curator.py -q -k "not test_load_cli_defaults_uses_notional_aware_three_percent_drift"` -> 47 passed, 1 deselected (falha legada de uplift já existente).
- Suíte geral: `uv run pytest -q --tb=short` -> 334 passed, 7 falhas baseline: 5 casos adaptivos por ausência de BINANCE_API_KEY/SECRET, um anti-churn que ainda chama execução, e uplift tolerance; sem falha nos testes desta tarefa.
- `git diff --check` passou. Nenhuma inferência, rede, rebalance ou execução de launcher foi feita.
- Codex em falha agora retorna exatamente `proposed_weights` e `redistribute`; guardrails seguem aplicados somente a conselho válido. Gate de refresh OpenRouter testado em Codex/off e legado.
- Revisão independente inicial encontrou o desvio de fallback; após correção, segunda auditoria confirmou que não há bloqueios. TASK-056 permanece necessária antes de inferência real; TASK-057 exige autorização operacional separada.
