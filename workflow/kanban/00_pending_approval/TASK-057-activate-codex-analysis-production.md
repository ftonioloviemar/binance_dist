# TASK-057: Corte controlado para análises Codex CLI

Status: revisão concreta preparada; aguardando aprovação operacional final e rotação da chave OpenRouter exposta no retorno da ferramenta. Nenhuma alteração de produção foi feita. Classificação: ativação operacional sensível. Dependência: TASK-056 aceita e autorização explícita para produção.

## Objetivo e escopo

Selecionar Codex explicitamente no fluxo agendado existente após aceite da candidata. Design: `docs/superpowers/specs/2026-10-21-codex-cli-analysis-design.md`. Passos: seção TASK-057 de `docs/superpowers/plans/2026-10-21-codex-cli-analysis.md`.

## Verificação e aceite

Apresentar diff concreto e resultados antes da autorização. Verificar disco, backup de configuração/launcher e tarefa somente se tocada; hashes e restauração documentados. Provar contexto da identidade agendada. Observar um ciclo autorizado com Luna/médio, deadline, ausência de chamadas OpenRouter e estado final auditável. Não disparar manualmente ordens, resgates ou subscrições como teste.

## Riscos e rollback

Falha da IA conserva fallback determinístico que pode operar se o fluxo for live. Rollback restaura launcher/configuração anteriores, não desfaz operações da conta. Nenhuma mudança de agenda sem necessidade/autorização, nenhuma remoção de chaves e nenhum segredo versionado. Auditoria independente e commit dos arquivos versionados apenas; fechar somente após evidência do ciclo e registro do resultado.

## Revisão concreta do corte (2026-10-24)

- Checkout de produção: `C:\python\binance_dist`, `master`, limpo em `fe37b5d`. O candidato está em `codex/codex-cli-analysis` e pode avançar por fast-forward até `9e6b81b`, incluindo `b00f295`, `5b64027`, `299cd4e` e `9e6b81b`. Não aplicar antes da aprovação operacional final.
- Delta de seleção do provedor: adicionar `AI_PROVIDER=codex_cli` ao `.env`, preservando as outras configurações. `AI_PROVIDER` está ausente no checkout atual. Separadamente, `OPENROUTER_API_KEY` precisa ser rotacionada devido à exposição; portanto o `.env` também receberá a nova chave, que nunca deve ser impressa, copiada para evidência ou versionada.
- Não alterar `run_prod.bat` nem a tarefa agendada. A tarefa existente chama `C:\python\binance_dist\run_prod.bat`, usa o usuário `viemar\ftoniolo`, logon `Interactive`, nível `Limited`, e tem ciclos diários às 09:00 e 21:00 locais. No preflight, o ciclo das 09:00 terminou com código 0 e o próximo estava previsto para 21:00. Nenhum ciclo foi iniciado por esta revisão.
- A sessão atual resolveu Codex CLI `0.164.0-alpha.11.1`; três inferências sintéticas Luna/médio foram aceitas. A tarefa usa a mesma SID interativa, mas seu PATH/autenticação efetivos ainda não foram demonstrados. O CLI expôs apenas o modelo solicitado, não uma identidade efetiva independente.
- Evidência de aceitação já disponível: testes focados 46 aprovados; suíte completa 367 aprovados e 7 falhas baseline conhecidas (6 adaptativas e 1 configuração). A validação não chamou Binance/Earn. A política de fallback determinístico pode continuar a alocar e negociar em execução live se o Codex falhar.
- Um preflight de leitura imprimiu acidentalmente o valor da chave OpenRouter no retorno da ferramenta. O valor não foi incluído em arquivos nem repetido. Criar uma chave substituta enquanto a atual ainda está ativa; gravar só a nova chave em `.env` preservando `AI_PROVIDER` ausente; validar a credencial pelo GET autenticado `/api/v1/key` (sem inferência nem operação Binance); então criar backup protegido do `.env` já rotacionado, registrar hash sem imprimir valores, e adicionar `AI_PROVIDER=codex_cli` por substituição atômica. Revogar a chave exposta imediatamente após confirmar a troca. Assim qualquer ciclo durante a rotação usa uma chave válida. A criação exige management key e retorna o plaintext uma única vez; use a UI e não exponha management key, novo valor, hash ou corpo da resposta em ferramentas/logs. Persistir somente status HTTP e resultado sanitizado do GET, pois o JSON inclui metadados e rótulo parcial da chave. Referências oficiais: [criar chave](https://openrouter.ai/docs/api/api-reference/api-keys/create-a-new-api-key), [validar chave atual](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-api-key), [excluir chave](https://openrouter.ai/docs/api/api-reference/api-keys/delete-an-api-key).
- O backup pré-seleção comprova preservação/integridade do `.env`; o GET comprova autenticação da nova chave, mas não orçamento/entitlement nem uma futura inferência OpenRouter ponta a ponta. Rollback: restaurar o checkout de código a `fe37b5d` e o `.env` pré-seleção (com a nova chave validada), sem restaurar a chave exposta. Isso não desfaz operações já executadas.
- Se a chave substituta não puder ser criada, validada e instalada antes do próximo ciclo das 21:00, não permitir que o Agendador rode com a chave exposta/inválida: parar aqui e decidir com o usuário um bloqueio temporário do ciclo. Não alterar a tarefa sem aprovação explícita.
- O aceite operacional exige aprovação do usuário para o corte e para observar o próximo ciclo agendado live; não executar manualmente a tarefa nem um rebalance para teste. O ciclo deve comprovar provider/modelo/esforço solicitados, duração, ausência de curadoria OpenRouter, auditoria e resultado final estáveis. Parar e aplicar o rollback documentado se a evidência divergir.
