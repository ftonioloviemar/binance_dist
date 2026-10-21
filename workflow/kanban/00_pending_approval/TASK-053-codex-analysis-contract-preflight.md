# TASK-053: Contrato de análise e preflight Codex

Status: pending approval. Classificação: TDD e investigação offline. Dependência: aceite do plano TASK-052.

## Objetivo e escopo

Compartilhar contexto/prompt e definir schema estrito para a candidata. Provar controles disponíveis de isolamento de ferramentas, MCP, hooks e instruções sem inferência. Design: `docs/superpowers/specs/2026-10-21-codex-cli-analysis-design.md`. Executar seção TASK-053 de `docs/superpowers/plans/2026-10-21-codex-cli-analysis.md`.

## Contrato RED/GREEN

Arquivos: `ai_contract.py`, `portfolio.py`, `tests/test_ai_contract.py`, `tests/test_portfolio.py`. RED esperado: helpers ausentes e contrato não definido. Comando: `uv run pytest tests/test_ai_contract.py tests/test_portfolio.py tests/test_openrouter_model_curator.py -q`. Casos: action, símbolos, pesos finitos/não negativos, bool, soma zero, campos extras, texto inválido e tamanho da rationale.

## Aceitação e riscos

Preservar rota legada e matemática dos guardrails; documentar mecanismo real de isolamento. Se não comprovado, bloquear integração antes do smoke. Não basta sandbox read-only. Sem modelo real, credenciais impressas ou mudança global. Especialista limpo valida contrato antes; especialista distinto audita depois; commit ao concluir. Disco/backup antes de mudanças.
