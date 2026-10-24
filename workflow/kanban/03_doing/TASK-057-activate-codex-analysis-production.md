# TASK-057: Corte controlado para análises Codex CLI

Status: corte autorizado pelo usuário em 2026-10-24; execução em andamento. O usuário decidiu desativar a chave OpenRouter exposta e criar uma nova somente se rollback exigir o retorno ao OpenRouter. Não criar chave substituta agora. A desativação final no Chrome permanece handoff obrigatório para o usuário. Classificação: ativação operacional sensível. Dependência: TASK-056 aceita.

## Objetivo e escopo

Selecionar Codex explicitamente no fluxo agendado existente após aceite da candidata. Design: `docs/superpowers/specs/2026-10-21-codex-cli-analysis-design.md`. Passos: seção TASK-057 de `docs/superpowers/plans/2026-10-21-codex-cli-analysis.md`.

## Verificação e aceite

Apresentar diff concreto e resultados antes da autorização. Verificar disco, backup de configuração/launcher e tarefa somente se tocada; hashes e restauração documentados. Provar contexto da identidade agendada. Observar um ciclo autorizado com Luna/médio, deadline, ausência de chamadas OpenRouter e estado final auditável. Não disparar manualmente ordens, resgates ou subscrições como teste.

## Riscos e rollback

Falha da IA conserva fallback determinístico que pode operar se o fluxo for live. Rollback restaura launcher/configuração anteriores, não desfaz operações da conta. Nenhuma mudança de agenda sem necessidade/autorização, nenhuma remoção de chaves e nenhum segredo versionado. Auditoria independente e commit dos arquivos versionados apenas; fechar somente após evidência do ciclo e registro do resultado.

## Revisão concreta do corte (2026-10-24)

- Checkout de produção: `C:\python\binance_dist`, `master`, limpo em `fe37b5d`. O candidato está em `codex/codex-cli-analysis`, com commits de implementação `b00f295`, `5b64027`, `299cd4e` e `9e6b81b`, mais a revisão documentada do corte. A aprovação operacional foi recebida; aplicar fast-forward ao HEAD revisado do branch após esta atualização documental.
- Delta operacional: adicionar `AI_PROVIDER=codex_cli` e remover `OPENROUTER_API_KEY` do `.env`, preservando as outras configurações. A chave exposta será desativada no OpenRouter. Não criar chave substituta no corte; se um rollback exigir OpenRouter, criar/configurar uma nova chave antes do próximo ciclo.
- Não alterar `run_prod.bat` nem a tarefa agendada. A tarefa existente chama `C:\python\binance_dist\run_prod.bat`, usa o usuário `viemar\ftoniolo`, logon `Interactive`, nível `Limited`, e tem ciclos diários às 09:00 e 21:00 locais. No preflight, o ciclo das 09:00 terminou com código 0 e o próximo estava previsto para 21:00. Nenhum ciclo foi iniciado por esta revisão.
- A sessão atual resolveu Codex CLI `0.164.0-alpha.11.1`; três inferências sintéticas Luna/médio foram aceitas. A tarefa usa a mesma SID interativa, mas seu PATH/autenticação efetivos ainda não foram demonstrados. O CLI expôs apenas o modelo solicitado, não uma identidade efetiva independente.
- Evidência de aceitação já disponível: testes focados 46 aprovados; suíte completa 367 aprovados e 7 falhas baseline conhecidas (6 adaptativas e 1 configuração). A validação não chamou Binance/Earn. A política de fallback determinístico pode continuar a alocar e negociar em execução live se o Codex falhar.
- Um preflight de leitura imprimiu acidentalmente o valor da chave OpenRouter no retorno da ferramenta. O valor não será repetido nem mantido em backup. O usuário autorizou desativar essa chave no Chrome e decidiu não criar substituta agora. Remover a variável do `.env` junto com a seleção Codex. A política Computer Use exige que o usuário execute o passo final de desativação da credencial; a chave correta deve ser confirmada no painel antes do clique.
- Backup pré-corte: salvar template protegido do `.env` com todas as linhas não secretas, omitindo `OPENROUTER_API_KEY`, e registrar hash do arquivo original sem mostrar valores. Rollback: restaurar o código em `fe37b5d`; se a análise OpenRouter for necessária, criar e instalar uma nova chave antes do próximo ciclo. Até isso ocorrer, o OpenRouter falha para o fallback determinístico existente. Isso não desfaz operações já executadas.
- O usuário autorizou o corte e observar o próximo ciclo agendado live. Não executar manualmente a tarefa nem um rebalance para teste. O ciclo deve comprovar provider/modelo/esforço solicitados, duração, ausência de curadoria OpenRouter, auditoria e resultado final estáveis. Parar e aplicar o rollback documentado se a evidência divergir. A tarefa agendada permanece inalterada.
