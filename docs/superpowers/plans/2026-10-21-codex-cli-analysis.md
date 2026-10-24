# Codex CLI Analysis Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` após aprovação da execução. Executar cartão a cartão com os especialistas de contrato e auditoria exigidos pelo projeto.

**Goal:** Entregar versão candidata que analisa carteiras via Codex CLI local com `gpt-6-luna` e esforço `medium`, substituindo OpenRouter na rota candidata.

**Architecture:** Adaptador de subprocesso isolado devolve `AIAdvice` através de contrato compartilhado de prompt, validação e guardrails. Seleção explícita de provedor permite validar a candidata sem mudar a tarefa de produção; falhas usam o fallback determinístico existente.

**Tech Stack:** Windows/PowerShell, Python 3.11+, uv, pytest, Codex CLI instalado.

**Spec:** `docs/superpowers/specs/2026-10-21-codex-cli-analysis-design.md`.

## Global Constraints

- Execução aprovada: TASK-053/054/055 concluídas nos commits `b00f295`, `5b64027` e `299cd4e`; TASK-056 está em `07_needs_human`; TASK-057 segue em `00_pending_approval` até TASK-056 aceitar e receber autorização operacional específica.
- `gpt-6-luna`, `model_reasoning_effort="medium"`; nenhuma substituição automática.
- Uma chamada; timeout padrão 120 s, máximo 300 s; saída até 64 KiB; rationale até 2.000 caracteres.
- O usuário autorizou chamadas sintéticas de TASK-056 sem limite de quantidade para diagnóstico/aceitação, sem confirmação por chamada. Nenhuma operação live, mudança global Codex ou alteração da tarefa agendada está autorizada.
- Antes de cada cartão, recuperar contexto, verificar disco e preservar backup/rollback; preservar mudanças de outras sessões.
- TDD RED → implementação mínima → GREEN → auditoria independente → commit por cartão.
- Especialista de contrato em contexto limpo antes de cada implementação não trivial e outro especialista para auditar o resultado; coordenador valida ambos conforme `docs/subagent-specialist-matrix.md` e `docs/model-selection.md`.

## Review Focus

- Windows: PATH/identidade do Agendador diferentes da sessão interativa e executável instalado em diretório versionado (TASK-053/056).
- Isolamento: herança de credenciais, hooks, instruções, ferramentas e MCP; read-only não basta (TASK-053/054).
- Processo que expira, cria descendentes ou escreve saída parcial/tardia (TASK-054).
- JSON estruturalmente válido com bool/NaN/Infinity, pesos negativos, símbolos extras, action desconhecida ou soma zero (TASK-053/054).
- Falha Codex que dispara curadoria OpenRouter ou muda silenciosamente política de trading (TASK-055).

## Mapa de arquivos proposto

- Criar `ai_contract.py`: contexto/prompt, schema e validação compartilhados, `AnalysisRequest` e transformação segura em `AIAdvice`.
- Criar `codex_cli_analyzer.py`: descoberta, preflight e ciclo de vida isolado do subprocesso.
- Modificar `portfolio.py`: reutilizar contrato sem alterar a API legada `ai_refine_targets` nem a matemática de guardrails.
- Modificar `config.py`: seletor e configuração CLI; modificar `app.py`: despacho e auditoria condicional.
- Criar `run_codex_candidate.bat`: launcher exclusivo com dry-run explícito e `AI_PROVIDER=codex_cli`, sem alterar `run_prod.bat`.
- Criar testes `tests/test_ai_contract.py`, `tests/test_codex_cli_analyzer.py`, `tests/test_app_ai_provider.py`, `tests/test_codex_candidate_launcher.py`.
- Estender `tests/test_portfolio.py`, `tests/test_config.py`; preservar testes de `tests/test_openrouter_model_curator.py`.
- Atualizar `.env.example`, `README.md` e criar `docs/codex-cli-analysis.md` na integração. `.env` real e launcher de produção pertencem só ao corte.

## TASK-053 — Contrato compartilhado e preflight offline

**Interfaces:** criar `AnalysisRequest(portfolio_value: float, current_weights: Mapping[str, float], proposed_weights: Mapping[str, float], portfolio_context: Mapping[str, Any] | None)` imutável; `build_analysis_prompt(request: AnalysisRequest) -> str`; `build_analysis_schema(request: AnalysisRequest) -> dict[str, Any]`; `parse_analysis_response(content: str, request: AnalysisRequest) -> tuple[dict[str, float], str, str]`, lançando `ValueError` em resposta inválida. `portfolio.py` importa o contrato, mantendo as classes de resultado atuais.

- [x] Especialista valida casos e asserts antes da implementação; inventariar somente configuração necessária do CLI sem valores secretos. Confirmar mecanismo suportado de desativação de ferramentas/MCP/plugins/hooks e isolamento de instruções. Documentar evidência ou bloquear o cartão; não fazer inferência para descobrir isolamento.
- [x] RED em `tests/test_ai_contract.py`: resposta `maintain` válida preserva ação; símbolos exatamente iguais aos propostos; rejeição parametrizada de bool, negativo, não finito, soma zero, campos ausentes/extras, texto nulo, action desconhecida e rationale >2.000. `build_analysis_prompt` preserva o contexto existente e `build_analysis_schema` restringe os símbolos da chamada.
- [x] Executar `uv run pytest tests/test_ai_contract.py tests/test_portfolio.py -q`; registrar falha por contrato ausente. Implementar helpers; reutilizá-los na rota legada sem impor as novas restrições às respostas OpenRouter existentes.
- [x] GREEN com o mesmo comando e testes OpenRouter; especialista independente audita ausência de alteração em guardrails. Commit do cartão e evidência do preflight. Commit: `b00f295`.

## TASK-054 — Executor Codex CLI

**Depends:** TASK-053, incluindo isolamento comprovado.

**Interfaces:** criar `CodexCliSettings(executable: str | None, timeout_seconds: int)` imutável, com defaults da spec; `analyze_with_codex(request: AnalysisRequest, settings: CodexCliSettings) -> AIAdvice`. Erros operacionais retornam `AIAdvice` com pesos propostos, ação `redistribute` e `AIModelFailure` sanitizada. Metadados aditivos em `AIAdvice`: `provider`, `reasoning_effort`, `duration_seconds`, todos opcionais com default `None`.

- [x] RED em `tests/test_codex_cli_analyzer.py`: fake de processo verifica modelo/effort explícitos, stdin, `shell=False`, diretório exclusivo, ambiente sem chaves Binance/OpenRouter e uso dos controles comprovados no preflight. Verificar que JSONL não é confundido com o arquivo final.
- [x] RED parametrizado: executável ausente, login/modelo indisponível, exit !=0, timeout, JSON inválido, arquivo ausente, saída >64 KiB, UTF-8, duas chamadas concorrentes sem colisão, prompt com aspas/metacaracteres, cleanup após falhas. Processo auxiliar local inofensivo prova encerramento de descendente e ausência de escrita tardia no Windows.
- [x] Executar `uv run pytest tests/test_codex_cli_analyzer.py tests/test_ai_contract.py -q`; registrar RED. Implementar processo com uma tentativa e deadline total; erro tipado via `AIModelFailure.error_type`, sem stderr ou payload bruto.
- [x] GREEN, auditoria independente do isolamento, deadline e limpeza, commit. Nenhum teste desta tarefa pode executar o modelo real. Commit: `5b64027`.

## TASK-055 — Seleção do provedor e integração candidata

**Depends:** TASK-054. **Interface:** `config.EnvSettings` ganha `ai_provider: str` e configurações CLI com defaults compatíveis. `app.py` despacha para `analyze_with_codex` apenas quando selecionado; `ai_refine_targets` continua sendo a API OpenRouter.

- [x] RED em `tests/test_config.py`: `AI_PROVIDER` aceita `codex_cli|openrouter|off`, ausência mantém legado, valor desconhecido falha; timeout inválido/zero/negativo/>300 falha. Codex funciona sem chave OpenRouter.
- [x] RED em `tests/test_app_ai_provider.py`: contexto/guardrails e action `maintain` preservados; todos os retornos Codex e `off` deixam `requests.post` OpenRouter e `refresh_openrouter_models` com contagem zero, mesmo com chave presente; falha retorna proposta determinística; metadados auditados sem segredos. Controles de execução usam fakes, sem rede.
- [x] RED em `tests/test_codex_candidate_launcher.py`: launcher candidato fixa dry-run e provedor, rejeita tentativa de ativar live por argumentos; não chama `run_prod.bat`. Implementar launcher candidato com escopo de ambiente local ao batch.
- [x] Executar `uv run pytest tests/test_config.py tests/test_app_ai_provider.py tests/test_codex_candidate_launcher.py tests/test_portfolio.py tests/test_openrouter_model_curator.py -q`; registrar RED, implementar configuração/despacho/auditoria e documentação do operador.
- [x] GREEN, `uv run pytest`, `git diff --check`, auditoria independente e commit. Não editar `.env` real, cronograma, nem `run_prod.bat`. Commit: `299cd4e`.

## TASK-056 — Aceitação offline e smoke sintético

**Depends:** TASK-055; execução da onda aprovada. O smoke é uma chamada de inferência explícita da aceitação, somente após os controles de TASK-053/054 passarem.

- [x] Criar conjunto versionado `tests/fixtures/codex_analysis/` com entradas sintéticas e saídas fixas válidas/inválidas; `tests/test_codex_analysis_replay.py` testa aplicação/fallback e isolamento do histórico. Não gerar novos conselhos durante o replay offline. Os fixtures e testes estão prontos para o commit do cartão.
- [x] Comparar proposta determinística e conselho capturado com preços/filtros congelados, incluindo maintain, redistribuição, sem dados macro e fonte BTC vencida; manter gate de 15 minutos, custos, filtros e shadow existentes. Nenhuma ordem/endpoint Earn pode ser chamado.
- [x] Rodar `uv run pytest` e `git diff --check`; testar processo auxiliar e launcher offline. Registrar contagens e limitações, sem apresentar replay como prova de rentabilidade. Resultado mais recente: 367 passaram; 7 falhas baseline conhecidas (6 `tests/test_app_adaptive.py`, 1 `tests/test_config.py`).
- [x] Corrigir cleanup pós-inferência: Restart Manager + Toolhelp identificaram `git.exe` descendente do `codex exec` mantendo arquivo temporário após o processo-raiz terminar. Após exit, enumerar descendentes, fixar handles, revalidar ancestralidade e encerrar somente os verificados antes da leitura/limpeza; retry busy limitado pela deadline absoluta. Testes Windows provam que o reaper não age enquanto a raiz roda, encerra apenas descendente sintético e preserva processo independente; PID reutilizado/ancestralidade perdida são ignorados.
- [x] Executar chamadas sintéticas Luna/médio pelo adaptador com contexto fixo e evidência sanitizada. O usuário autorizou chamadas ilimitadas para TASK-056 sem confirmação por chamada; não repetir automaticamente dentro de uma chamada. Três execuções consecutivas aceitaram resposta estruturada (4.219s, 3.578s, 4.125s), terminaram 12/12 handles de descendentes no total e tiveram zero erro busy de cleanup. Não se conhece a divisão dos nove handles entre execuções 2 e 3. CLI não expõe identidade efetiva independente. Não alterar produção, tarefa ou modelo.
- [x] Verificar identidade, diretório, PATH e acesso à autenticação no contexto da tarefa existente por meios de leitura; se depender de login interativo ou mudança de tarefa, registrar pendência antes do corte. Não criar tarefa nova para testar sem autorização. Identidade/logon e launcher foram verificados; PATH/auth efetivos da tarefa permanecem lacunas registradas, sem iniciar ou mudar a tarefa.
- [x] Revisão independente final dos documentos/evidência e consistência do cartão; commit dos fixtures/docs e movimentação para `05_done`. Auditorias de contrato/replay, diagnóstico e consistência documental passaram. A identidade efetiva independente e o PATH/auth efetivos do Agendador permanecem limitações para TASK-057, sem invalidar aceitação sintética. TASK-057 segue bloqueada por aprovação operacional própria.

## TASK-057 — Ativação controlada e rollback

**Depends:** TASK-056 aceita; autorização explícita do usuário para corte de produção. É uma aprovação operacional distinta da execução de código.

- [ ] Apresentar diff concreto de configuração/launcher, resultados e exposição ao fallback determinístico; obter autorização antes de aplicá-lo.
- [ ] Verificar disco; copiar arquivos operacionais tocados e exportar tarefa somente se houver mudança dela. Registrar hashes e comando real de restauração, sem segredos. Manter tarefa/agenda existente se não precisar mudar.
- [ ] Selecionar `AI_PROVIDER=codex_cli` explicitamente em produção; não remover chave OpenRouter nem o adaptador legado neste corte. Preservar modelo/esforço fixos.
- [ ] Observar um ciclo agendado autorizado: provedor/modelo/esforço corretos, tempo dentro do orçamento, nenhuma curadoria OpenRouter, auditoria e resultado visível estáveis. Não disparar manualmente trading para validar.
- [ ] Em falha, restaurar exatamente launcher/configuração anteriores, após confirmar hashes; rollback não desfaz ordens já executadas. Registrar resultado e aprovação do retorno antes de encerrar.
- [ ] Executar verificações específicas do launcher, `git diff --check`, auditoria independente e commit apenas de arquivos versionados. Segredos/backups permanecem fora do Git.

## Fechamento e continuidade

Mover fisicamente cada cartão até `05_done` somente após seus critérios, com commit antes do seguinte. Capturar regra reutilizável de análise isolada em `docs/lessons-learned.md` após comprovação, não antes. Atualizar `docs/STATE.md` com cartão ativo, evidência e próxima ação segura. Remoção definitiva do legado OpenRouter e mudança da política de fallback exigem cartões futuros separados.
