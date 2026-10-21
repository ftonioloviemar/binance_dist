# TASK-054: Executor Codex CLI isolado

Status: concluído. Classificação: TDD. Dependência: TASK-053 aceita com isolamento comprovado para desenvolvimento e testes com fakes; limitações restantes documentadas.

## Objetivo e escopo

Criar `codex_cli_analyzer.py` e `tests/test_codex_cli_analyzer.py`; adicionar metadados compatíveis em `AIAdvice`. Design: `docs/superpowers/specs/2026-10-21-codex-cli-analysis-design.md`. Interfaces e passos: seção TASK-054 de `docs/superpowers/plans/2026-10-21-codex-cli-analysis.md`.

## Contrato RED/GREEN

RED esperado: adaptador ausente. Comando: `uv run pytest tests/test_codex_cli_analyzer.py tests/test_ai_contract.py -q`. Provar Luna/médio, stdin, argumentos sem shell, isolamento do ambiente/cwd, arquivo final separado dos eventos, timeout total, encerramento de descendentes Windows, ausência de escrita tardia, limpeza e concorrência. Fakes e processo auxiliar inofensivo, sem inferência.

## Aceitação e riscos

Uma tentativa; timeout 120 s configurável até 300 s; saída até 64 KiB; erro sanitizado retorna proposta determinística/redistribute, sem provedor alternativo. Não herdar segredos Binance/OpenRouter nem contornar políticas. Especialistas distintos de contrato/auditoria e commit ao concluir; verificar disco/rollback antes.

TASK-053 foi aceita para avançar com fakes: o preflight demonstrou CODEX_HOME temporário sem instruções globais/MCP configurado e sandbox MXC root-deny/workspace-read. Não iniciar inferência nesta tarefa. Fake deve confirmar argumentos/overrides de runtime. A política gerenciada efetiva e a fronteira de rede API/ferramentas não foram demonstradas; registrar como limitação, sem afirmar isolamento total. Identidade do Agendador é gate de TASK-056.

## Evidências de execução

- RED: `uv run pytest tests/test_codex_cli_analyzer.py tests/test_ai_contract.py -q` -> duas falhas esperadas por módulo ausente; contrato compartilhado passou.
- GREEN: `uv run pytest tests/test_codex_cli_analyzer.py tests/test_ai_contract.py tests/test_portfolio.py tests/test_openrouter_model_curator.py -q` -> 62 passed. Inclui fakes de argumento/stdin/ambiente, saída final separada de JSONL, timeout/fallback, limites de bytes/UTF-8, concorrência, hard link sintético/removido e helper local Windows que verifica morte de descendente sem escrita tardia.
- Isolamento de instruções alinhado: workdir do executor usa `%SystemRoot%\Temp` (e rejeita raiz sob o perfil do usuário). `codex debug prompt-input` foi executado em subdiretório equivalente de `C:\Windows\Temp`, com CODEX_HOME vazio e mesmos overrides; exit 0, 0 linhas não triviais do AGENTS global coincidentes, nenhum caminho do perfil no prompt.
- ACL somente leitura: consulta da raiz `C:\Windows\Temp` retornou acesso negado; uma subpasta filha criada para a prova herdou Users com criação/travessia (sem leitura/listagem), e usuário atual/SYSTEM/Administradores com controle total. Revalidar a ACL da pasta de execução em TASK-056; não extrapolar para outras máquinas/identidades.
- Suíte completa: `uv run pytest -q --tb=short` -> 315 passed, 7 falhas basais fora do escopo (6 em `tests/test_app_adaptive.py`, uma em `tests/test_config.py`). Nenhuma falha no runner.
- Auditoria independente aprovou a conclusão offline e confirmou que o preflight de instruções corresponde ao workdir do executor. ACL da raiz `C:\Windows\Temp` não foi legível; uma subpasta filha criada para a prova herdou Users com criação/travessia sem leitura, e usuário atual/SYSTEM/Administradores com controle total. Revalidar sob identidade real antes de inferência.
- Sem inferência ou chamada de rede. Teste sintético confirma hard link de auth isolado e remoção do alias; não prova que o CLI real não atualizará o arquivo fonte. Resolver/aceitar explicitamente esse risco antes do smoke em TASK-056.
- Conclusão: `codex_cli_analyzer.py` retorna fallback determinístico e não tenta provedor alternativo; nenhuma política de trading mudou. TASK-054 concluída; próximo cartão TASK-055.
