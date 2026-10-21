# Análises por Codex CLI local — proposta de nova versão

Data: 2026-10-21. Estado: planejamento solicitado; implementação e ativação pendentes.

## Objetivo e escopo

Substituir as chamadas de análise do OpenRouter por invocações do Codex CLI instalado neste Windows, usando exatamente `gpt-6-luna` com `model_reasoning_effort="medium"`. A nova versão deve produzir o mesmo contrato de aconselhamento de carteira, passando pelas validações determinísticas existentes. O CLI é local; a inferência continua remota na OpenAI, com autenticação e limites da conta. Não é execução offline do modelo.

O pedido desta etapa é planejar a onda. Não executar inferência, rebalanceamento, resgate, subscrição ou mudança do Agendador para elaborar o plano.

## Evidência atual

- Baseline limpo: `3ffe6a7f9cb93360b166a21868a110797561672b`.
- Disco C: aproximadamente 61,4 GiB livres antes da escrita. Backup de `docs/STATE.md`: `state/backups/20261021-codex-cli-plan/STATE.md`, com SHA-256 igual ao original.
- `codex --version`: `codex-cli 0.163.0-alpha.10.2`.
- `Get-Command codex` resolve um `codex.exe` instalado pelo aplicativo, em diretório versionado. Não fixar esse diretório como configuração permanente sem tratar atualizações.
- `codex exec --help` confirma `--model`, `--config`, `--sandbox read-only`, `--ephemeral`, `--ignore-user-config`, `--skip-git-repo-check`, `--output-schema`, `--output-last-message`, `--json` e prompt por stdin com `-`.
- `portfolio.py:160` implementa `ai_refine_targets`; `_call_openrouter_model` monta contexto e prompt; `AIAdvice`/`AIModelFailure` carregam resultado e falhas; `_apply_ai_guardrails` limita sugestões antes da normalização e aplica pisos existentes.
- `app.py:692` seleciona modelos OpenRouter e consulta a IA; `app.py:727` inicia o bloco de curadoria após falha do primeiro modelo. A nova rota deve impedir ambos os acessos OpenRouter.
- `run_prod.bat` executa `uv run app.py rebalance --dry-run=false --adaptive`. Não usá-lo como smoke test.

## Opções consideradas

1. Trocar diretamente toda a implementação OpenRouter: menor superfície final, mas dificulta comparação, rollback e preservação dos contratos existentes.
2. Introduzir seleção explícita de provedor e um adaptador Codex CLI: recomendada. Compartilhar prompt, validação e guardrails; manter OpenRouter apenas como opção legada explícita durante a transição.
3. Usar diretamente SDK/API OpenAI: dispensaria o subprocesso, mas não atende à escolha do usuário pelo CLI local.

## Decisões propostas

- Criar `AI_PROVIDER=codex_cli|openrouter|off`. Durante implementação, ausência da variável conserva o comportamento legado; um launcher candidato seleciona explicitamente `codex_cli`. A mudança do launcher de produção pertence somente à ativação aprovada.
- Modelo `gpt-6-luna` e esforço `medium` são constantes da versão candidata. Não trocar silenciosamente por outro modelo, esforço ou provedor.
- `CODEX_CLI_EXECUTABLE` opcional configura o executável; ausência usa descoberta de `codex` no PATH. Falha de descoberta é diagnosticada. Não instalar nem atualizar o CLI automaticamente.
- `CODEX_CLI_TIMEOUT_SECONDS` inteiro positivo, padrão 120, máximo 300. Uma invocação por análise, sem retry automático. Orçamento inclui inicialização, saída e encerramento da árvore do processo. Timeout retorna o fallback determinístico existente e diagnóstico sanitizado.
- Entrada preserva o contexto atual necessário à análise, sem ampliar os dados de conta enviados. Segredos Binance/OpenRouter nunca entram no prompt, argumentos, ambiente herdado ou diagnóstico do subprocesso.
- Prompt por stdin, argumentos como lista e `shell=False`; diretório temporário exclusivo por chamada fora do repositório, saída final em arquivo exclusivo, schema explícito e limpeza em sucesso/falha. Não interpretar JSONL de eventos como resposta da análise.
- Usar autenticação já disponível ao CLI. Não copiar `auth.json`, criar chaves, mudar rotas globais ou imprimir tokens. Validar acesso sob a identidade real do Agendador antes do corte; a sessão interativa não comprova isso.
- Isolar configuração herdada e impedir ferramentas, MCP, plugins, hooks e instruções do projeto durante a análise. `read-only` sozinho não comprova ausência de acesso a segredos. TASK-053 deve estabelecer e testar o mecanismo suportado pela versão instalada; se não for possível, a integração fica bloqueada antes de qualquer inferência. Não usar flags de bypass nem contornar política do executor.
- Pedir objeto com `action` em `maintain|redistribute`, `targets` com os símbolos da proposta e `rationale` textual limitada a 2.000 caracteres. Gerar schema para os símbolos da chamada com campos obrigatórios e propriedades adicionais proibidas. Todos os pesos devem ser números finitos, não negativos e com soma positiva; rejeitar booleanos, símbolos extras, JSON vazio/truncado e resposta acima de 64 KiB. Aplicar os guardrails existentes e normalização somente após validação.
- Preservar semântica existente: falha técnica devolve os pesos propostos pelo algoritmo e ação `redistribute`. Isso pode permitir operações determinísticas se a execução já for live; não significa pausar trading. Mudar essa política seria uma decisão de estratégia separada.
- Auditar provedor, modelo solicitado/efetivo quando disponível, esforço, duração, resultado, código de falha e uso de fallback. Tokens somente quando reportados; custo monetário não deve ser inferido a partir da assinatura. Não guardar prompt, carteira completa, resposta bruta ou stderr bruto.
- Em `codex_cli` e `off`, nenhuma chamada à curadoria, catálogo ou inferência OpenRouter, mesmo com chave OpenRouter presente ou CLI falhando. Retorno ao OpenRouter exige seleção explícita.

## Contratos e limites

`AIAdvice` continua sendo o contrato consumido pelo fluxo de rebalanceamento. Acrescentar metadados somente com defaults compatíveis. O adaptador gera conselho, nunca ordens ou comandos. Perfis, fontes macro, gate de frescor BTC 0..15 minutos, drift, custos, filtros Binance e execução de Earn seguem os caminhos existentes.

Não prometer que o clamp pré-normalização equivale a um limite final absoluto de cinco pontos percentuais: a normalização e os pisos podem alterar isso. Preservar a matemática existente e registrar qualquer divergência em cartão separado, sem ampliar esta onda.

## Aceitação da onda

- Testes offline demonstram Luna/médio explícitos, isolamento, parsing estrito, deadline/limpeza e fallback sem OpenRouter.
- Integração preserva conselho, `maintain`, guardrails, auditoria e chamadas simuladas de execução.
- Replay usa entradas sintéticas ou sanitizadas, com preços/filtros congelados e comparação ao baseline determinístico; divergência de conselho não é prova de melhora financeira.
- Smoke real restrito a contexto sintético comprova CLI, autenticação, modelo e contrato. Seu lançamento fica para a execução aprovada, após isolamento comprovado; nesta etapa não ocorreu chamada ao modelo.
- Ativação exige aceite dos resultados, backup de launcher/configuração/tarefa quando aplicável, rollback e observação de um ciclo na identidade agendada. Produção e operações live exigem autorização explícita.

## Pendências verificáveis

Não sei ainda se a autenticação desta máquina permite `gpt-6-luna` no CLI sob o usuário do Agendador, nem se os controles instalados conseguem eliminar todas as ferramentas e configurações herdadas. O help prova a interface, não essas capacidades. TASK-053 resolve o isolamento; TASK-056 resolve inferência/autenticação. Falha mantém a versão atual em operação.

## Referências oficiais consultadas

- [Codex não interativo](https://learn.chatgpt.com/docs/non-interactive-mode): schema de saída, saída final separada, autenticação persistida.
- [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna): identificador e suporte a esforço `medium`.
- Flags da versão instalada: `codex exec --help`, consultado sem inferência.

Plano executável: `docs/superpowers/plans/2026-10-21-codex-cli-analysis.md`.
