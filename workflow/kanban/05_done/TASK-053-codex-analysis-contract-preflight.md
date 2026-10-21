# TASK-053: Contrato de análise e preflight Codex

Status: concluído. Classificação: TDD e investigação offline. Dependência: plano TASK-052 aprovado pelo usuário.

## Objetivo e escopo

Compartilhar contexto/prompt e definir schema estrito para a candidata. Provar controles disponíveis de isolamento de ferramentas, MCP, hooks e instruções sem inferência. Design: `docs/superpowers/specs/2026-10-21-codex-cli-analysis-design.md`. Executar seção TASK-053 de `docs/superpowers/plans/2026-10-21-codex-cli-analysis.md`.

## Contrato RED/GREEN

Arquivos: `ai_contract.py`, `portfolio.py`, `tests/test_ai_contract.py`, `tests/test_portfolio.py`. RED esperado: helpers ausentes e contrato não definido. Comando: `uv run pytest tests/test_ai_contract.py tests/test_portfolio.py tests/test_openrouter_model_curator.py -q`. Casos: action, símbolos, pesos finitos/não negativos, bool, soma zero, campos extras, texto inválido e tamanho da rationale.

## Aceitação e riscos

Preservar rota legada e matemática dos guardrails; documentar mecanismo real de isolamento. Se não comprovado, bloquear integração antes do smoke. Não basta sandbox read-only. Sem modelo real, credenciais impressas ou mudança global. Especialista limpo valida contrato antes; especialista distinto audita depois; commit ao concluir. Disco/backup antes de mudanças.

## Evidências e andamento

- Espaço disponível: aproximadamente 61,8 GiB; worktree isolado em `C:\Users\ftoniolo\.codex\worktrees\codex-cli-analysis\binance_dist`, branch `codex/codex-cli-analysis`, baseado no commit do plano TASK-052.
- RED: antes de `ai_contract.py`, `tests/test_ai_contract.py` falhou por módulo ausente, como esperado.
- GREEN: `uv run pytest tests/test_ai_contract.py tests/test_portfolio.py tests/test_openrouter_model_curator.py -q` -> 50 passed; `git diff --check` passou.
- Especialista independente auditou o contrato puro; não apontou falha material. Adicionamos cobertura de soma que transborda e símbolos inválidos.
- Préflight parcial: sandbox MXC executa; perfil customizado permite leitura do workspace temporário e nega arquivo fora dele. Em `CODEX_HOME` temporário, `codex debug prompt-input` não incluiu nenhum dos 5 marcadores globais de AGENTS testados; `codex mcp list` indicou zero servidores configurados. A autenticação ChatGPT foi verificada por link temporário ao `auth.json` existente, removido após o teste; nenhum valor foi exibido ou copiado. `codex exec --ignore-user-config --help` iniciou sob MXC. Documentação oficial confirma toggles para shell/apps/hooks/multi_agent/remote_plugin e precedência de config, mas ainda não prova a política efetiva gerenciada nesta sessão nem a separação entre rede da chamada API e rede de ferramentas. Auditoria independente dessa evidência está pendente.
- Um comando de inventário MCP anterior exibiu valores de credenciais no output da ferramenta. Não foram copiados para arquivos nem repetidos; tratar as credenciais alcançadas por esse output como potencialmente expostas e rotacionar fora deste fluxo. Nenhuma rotação foi feita.
- Auditoria independente atualizada: evidências bastam para avançar TASK-054 com fakes, sem inferência. TASK-054 deve provar via fake os argumentos/configuração/ambiente efetivos e documentar que política gerenciada, limites de rede para processos e identidade do Agendador ainda não foram demonstrados. Validação do Agendador fica em TASK-056.
- TASK-053 concluída; sem execução de modelo, alteração de produção ou mudança global. Próximo cartão: TASK-054, executor isolado testado apenas com fakes.
