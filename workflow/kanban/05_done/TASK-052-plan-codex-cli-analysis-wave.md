# TASK-052: Planejar onda Codex CLI para análises

## Objetivo e classificação

Docs-only: planejar a nova versão solicitada em 2026-10-21, substituindo OpenRouter por Codex CLI local com `gpt-6-luna` e esforço médio.

## Entregas

- Design: `docs/superpowers/specs/2026-10-21-codex-cli-analysis-design.md`.
- Plano: `docs/superpowers/plans/2026-10-21-codex-cli-analysis.md`.
- TASK-053..057 em `00_pending_approval`: contrato/preflight, executor, integração, aceitação e corte.
- Continuidade atualizada em `docs/STATE.md`; observação anterior de frescor BTC permanece registrada.

## Evidência e rollback

- Baseline limpo `3ffe6a7f9cb93360b166a21868a110797561672b`; C: ~61,4 GiB livres.
- Backup de STATE em `state/backups/20261021-codex-cli-plan/STATE.md`; SHA-256 original/cópia: `7DE7A8AD9A1812AD325C86F31AC052A08F52BB691765C51731CE04B00E6F9506`.
- CLI `0.163.0-alpha.10.2`; somente versão/help/discovery, sem inferência.
- Fonte oficial confirma Luna/médio e contrato estruturado do CLI; disponibilidade da conta e identidade agendada ainda não verificadas.
- Verificação documental concluída: cinco cartões pendentes com IDs presentes no plano, design existente e hash do backup preservado; `git diff --check` sem erros. Nenhum teste de produto necessário para alteração exclusivamente documental.

## Aceitação e limites

Plano explicita TDD, especialistas de contrato/auditoria, isolamento, fallback, zero OpenRouter na candidata, deadline, smoke e rollback. Não houve alteração de código, `.env`, launcher, agenda ou operações de conta. Planejamento completo; execução pendente. Regra reutilizável proposta: provar isolamento do CLI antes de enviar contexto de carteira; registrar a lição somente após validação real.
