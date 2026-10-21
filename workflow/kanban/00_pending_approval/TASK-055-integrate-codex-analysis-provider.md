# TASK-055: Integrar provedor Codex e launcher candidato

Status: pending approval. Classificação: TDD. Dependência: TASK-054.

## Objetivo e escopo

Integrar `AI_PROVIDER`, despacho e auditoria em `config.py`/`app.py`; criar `run_codex_candidate.bat`, atualizar `.env.example`, `README.md` e `docs/codex-cli-analysis.md`. Design: `docs/superpowers/specs/2026-10-21-codex-cli-analysis-design.md`. Interfaces: seção TASK-055 de `docs/superpowers/plans/2026-10-21-codex-cli-analysis.md`.

## Contrato RED/GREEN

RED esperado: seletor/validação, despacho Codex e launcher ausentes. Comando: `uv run pytest tests/test_config.py tests/test_app_ai_provider.py tests/test_codex_candidate_launcher.py tests/test_portfolio.py tests/test_openrouter_model_curator.py -q`. Asserts: sem chave OpenRouter ainda usa Codex; zero inferência/curadoria OpenRouter em Codex/off, inclusive falha; maintain e guardrails preservados; fallback determinístico; audit sanitizado; launcher candidato não aceita ativação live por argumentos.

## Aceitação e riscos

Ausência do seletor preserva legado; candidata seleciona Codex explicitamente. `run_prod.bat`, `.env` real e Agendador ficam intactos. Full suite `uv run pytest` e `git diff --check`; especialistas de contrato e auditoria distintos; commit ao concluir. Disco/backup antes de mudanças.
