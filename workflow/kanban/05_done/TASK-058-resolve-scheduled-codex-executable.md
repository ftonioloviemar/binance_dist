# TASK-058: Resolver executável Codex no Agendador do Windows

**Status:** correção integrada em produção pela opção A autorizada em TASK-057 (2026-10-29); observação do próximo ciclo agendado ainda pendente. A integração não alterou `.env`, `run_prod.bat` nem o Agendador.

**Classificação:** correção de comportamento, TDD. **Dependência:** execução Codex CLI selecionada em TASK-057.

## Causa confirmada

Em 2026-10-29 às 09:00 -03:00, o Task Scheduler terminou com resultado 0, mas o audit da aplicação marcou o ciclo como `skipped`. A análise registrou `provider=codex_cli`, `model=gpt-6-luna`, `effort=medium`, falha `executable_not_found` e fallback determinístico. A sessão interativa resolve `codex`, mas o processo agendado não. A configuração `CODEX_CLI_EXECUTABLE` está vazia. A instalação observada tem um `codex.exe` regular em `%LOCALAPPDATA%\OpenAI\Codex\bin\<diretório-opaco>\codex.exe`; não se inferiu versão a partir do nome do diretório.

## Ruling

Manter precedência de `CODEX_CLI_EXECUTABLE` e depois `PATH`. No Windows, se ambos não resolverem, considerar apenas `LOCALAPPDATA\OpenAI\Codex\bin\*\codex.exe` e usar o caminho somente quando houver exatamente um arquivo regular. Falhar fechado em zero ou múltiplos candidatos, ausência de `LOCALAPPDATA`, erro de enumeração ou em plataformas não Windows. IDs de diretório e timestamps não provam qual instalação está ativa.

## Restrições

- Não alterar `.env`, launcher, tarefa/agendamento, credenciais ou produção neste cartão.
- Não iniciar Codex real, inferência, chamadas Binance/Earn ou rebalance.
- Preservar modelo `gpt-6-luna`, esforço `medium`, fallback determinístico e logging sanitizado.

## TDD e aceitação

- Especialista `gpt-6.1-terra`/medium define e escreve testes herméticos antes da implementação.
- `gpt-6-luna`/medium executa RED, GREEN e regressão; nenhum teste executa subprocesso real do Codex.
- Foco: `uv run pytest tests/test_codex_cli_analyzer.py -q`.
- Regressão: `uv run pytest -q`; comparar falhas com o baseline limpo no mesmo commit e ambiente.
- `git diff --check`; revisar precedência, resolução Windows, falha fechada e ausência de efeitos externos.
- Auditoria independente em contexto limpo, evidência sanitizada e commit deste cartão.

## Evidência operacional e limite

- Execução agendada de 2026-10-29 às 09:00: Scheduler `Ready`, resultado 0; aplicação `skipped`, `executable_not_found`, fallback determinístico. Audit do dia não contém chamada OpenRouter.
- A próxima execução estava agendada para 21:00 -03:00. Não iniciá-la manualmente. Se o ciclo falhar, registrar a evidência e parar para direção humana; nenhuma mudança de produção ou chave OpenRouter é automática.
- A integração elimina a dependência do PATH interativo para localizar a instalação observada. O ciclo automático de 2026-10-29 21:00 -03:00 deve confirmar o comportamento no Agendador; TASK-057 limita a validação à observação read-only e determina parar para decisão humana se o ciclo estiver ausente ou falhar.

## Diagnóstico e verificação local (2026-10-29)

- A pasta do executável Codex está no `PATH` do processo interativo, mas não nas variáveis persistidas `Path` do usuário ou da máquina. `run_prod.bat` chama `uv` e não altera `PATH`. Com `.env` sem `CODEX_CLI_EXECUTABLE`, isso explica `shutil.which("codex")` retornar ausente no contexto agendado.
- A documentação oficial do Codex CLI usa `shutil.which("codex")` e trata ausência no `PATH` como CLI indisponível; não documenta o diretório versionado observado da instalação da aplicação. A busca local por esse diretório é uma compatibilidade empírica e fail-closed, não uma garantia oficial de instalação.
- Teste focal: primeiro RED -> 1 falhou, 51 passaram; falha esperada foi descoberta do executável. GREEN inicial -> 52 passaram.
- Primeira auditoria independente encontrou P1: `Path.glob()` pode suprimir `PermissionError` interno e aceitar a enumeração parcial. Corrigido com enumeração direta `Path.iterdir()` e inspeções explícitas `stat()`, que propagam falhas de acesso para fallback fechado; novo teste inclui um candidato válido e outro inacessível. Teste RED da regressão nova falhou ao tentar iniciar o candidato válido, como esperado.
- Teste focal final: `uv run pytest tests/test_codex_cli_analyzer.py -q` -> 53 passaram.
- Regressão candidata: `uv run pytest -q` -> 382 passaram, 6 falharam. Baseline limpo em `f723ef6`, mesmo comando/ambiente -> 368 passaram, as mesmas 6 falharam; nenhum novo teste introduziu falha. As seis são testes adaptativos conhecidos: falha de persistência adaptativa, quatro casos de fonte macro não confiável e bloqueio de anti-churn.
- `git diff --check` passou. Não houve Codex real, rede, Scheduler start, Binance/Earn ou outra operação externa.
- Segunda auditoria independente não encontrou novos achados; recomendação P1 inicial foi corrigida e o teste de regressão validou fail-closed.
- Evidência final e auditoria independente registradas; cartão movido para `05_done` neste commit.
