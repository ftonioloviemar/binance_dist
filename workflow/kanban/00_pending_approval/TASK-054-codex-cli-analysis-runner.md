# TASK-054: Executor Codex CLI isolado

Status: pending approval. Classificação: TDD. Dependência: TASK-053 aceita com isolamento comprovado.

## Objetivo e escopo

Criar `codex_cli_analyzer.py` e `tests/test_codex_cli_analyzer.py`; adicionar metadados compatíveis em `AIAdvice`. Design: `docs/superpowers/specs/2026-10-21-codex-cli-analysis-design.md`. Interfaces e passos: seção TASK-054 de `docs/superpowers/plans/2026-10-21-codex-cli-analysis.md`.

## Contrato RED/GREEN

RED esperado: adaptador ausente. Comando: `uv run pytest tests/test_codex_cli_analyzer.py tests/test_ai_contract.py -q`. Provar Luna/médio, stdin, argumentos sem shell, isolamento do ambiente/cwd, arquivo final separado dos eventos, timeout total, encerramento de descendentes Windows, ausência de escrita tardia, limpeza e concorrência. Fakes e processo auxiliar inofensivo, sem inferência.

## Aceitação e riscos

Uma tentativa; timeout 120 s configurável até 300 s; saída até 64 KiB; erro sanitizado retorna proposta determinística/redistribute, sem provedor alternativo. Não herdar segredos Binance/OpenRouter nem contornar políticas. Especialistas distintos de contrato/auditoria e commit ao concluir; verificar disco/rollback antes.
