# TASK-056: Aceitar candidata por replay e smoke sintético

Status: pending approval. Classificação: testes/aceitação. Dependência: TASK-055 e execução da onda aprovada.

## Objetivo e escopo

Provar contrato, limites operacionais e acesso ao modelo com contexto sintético. Design: `docs/superpowers/specs/2026-10-21-codex-cli-analysis-design.md`. Passos: seção TASK-056 de `docs/superpowers/plans/2026-10-21-codex-cli-analysis.md`.

## Verificação

TDD para `tests/test_codex_analysis_replay.py` e fixtures `tests/fixtures/codex_analysis/`; RED por fixtures/integração de replay ausentes. Comando focado: `uv run pytest tests/test_codex_analysis_replay.py -q`, depois `uv run pytest` e `git diff --check`. Replay usa conselhos fixos e preços/filtros congelados, sem rede. Validar semântica maintain/redistribute/fallback, macro ausente e BTC vencido.

## Aceitação e riscos

Antes da inferência: verificar a ACL da pasta efetiva sob a identidade de execução, confirmar CODEX_HOME/auth pelo mecanismo disponível e resolver explicitamente que o auth.json hard link compartilha o arquivo fonte (ou não executar). Não alterar tarefa nem credenciais. Só então, com execução aprovada, uma inferência sintética via adaptador com Luna/médio; registrar modelo, esforço, duração, schema e lacunas sem payload/segredos. Sem retries automáticos, Binance ou Earn. Não sei ainda se o usuário do Agendador tem acesso ao modelo: verificar contexto de execução sem alterar tarefa e registrar bloqueios. Falha impede corte, não troca modelo. Revisão independente, evidência sanitizada e commit. Não concluir melhora de retorno financeiro a partir do replay.
