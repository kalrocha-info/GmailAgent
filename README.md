# GmailAgent

Agente inteligente para organizacao de emails no Gmail com foco em:

- classificacao por categoria
- prioridade e triagem
- aprendizado com correcoes manuais
- sugestoes de acao e resposta
- evolucao gradual das regras sem perder controle

## Estrutura do repositorio

- `docs/`
  Documentacao operacional da versao Python.
- `examples/`
  Arquivos de referencia, como exportacoes de filtros.
- `python/`
  Implementacao oficial do agente para analise, relatorios, reclassificacao segura e autopilot.

## Arquivos principais

- [docs/PythonAgentSetup.md](/D:/AGENTES-IA/docs/PythonAgentSetup.md)
- [examples/mailFilters.xml](/D:/AGENTES-IA/examples/mailFilters.xml)
- [pyproject.toml](/D:/AGENTES-IA/pyproject.toml)

## Implementacao oficial

A versao Python e a unica implementacao ativa e mantida. O antigo prototipo em Google Apps Script foi descontinuado para evitar regras duplicadas e comportamentos divergentes.

## Fluxo recomendado de uso

1. Rode o agente em modo seguro, sem arquivamento automatico.
2. Corrija manualmente as classificacoes que nao ficaram boas.
3. Rode o agente novamente para ele aprender com suas correcoes.
4. So depois considere habilitar automacoes mais agressivas.

## Aprendizado do agente

O agente aprende com labels aplicadas manualmente por voce e passa a usar estes sinais:

- remetente exato
- dominio
- assunto
- palavras-chave recorrentes

A ordem de confianca e:

1. Remetente
2. Assunto
3. Dominio
4. Palavra-chave

## Fluxo Python recomendado

1. Rode `gmail-agent analyze --max-messages 300` para gerar o inventario inicial.
2. Rode `gmail-agent autopilot-plan` para ver a fila de migracao automatica.
3. Rode `gmail-agent autopilot-run --cycles 3 --batch-per-label 300` para migrar labels legadas em segundo plano.
4. Rode `gmail-agent autopilot-report` para revisar o estado consolidado antes da limpeza final.
5. Rode `gmail-agent cleanup-labels --limit 50` apenas quando o relatorio mostrar labels vazias prontas para exclusao.

## Manutencao autonoma

Depois da migracao inicial, o comando abaixo serve para manter emails novos classificados e aprender com suas labels `AGENTE/...` aplicadas manualmente:

```powershell
gmail-agent maintain-recent --limit 300 --recent-days 7 --learning-days 14
```

O fluxo recomendado e agendar esse comando no Windows para rodar a cada 60 minutos.

## Politicas de seguranca

- Mensagens sem evidencias suficientes permanecem sem nova classificacao e aparecem no relatorio para revisao.
- O aprendizado exige pelo menos duas decisoes consistentes por remetente e confianca minima de 80%.
- O arquivamento tardio respeita a lista explicita de categorias arquivaveis; categorias urgentes e de acompanhamento permanecem na caixa de entrada.
- `apply-filters --replace-existing` valida todas as labels antes de alterar filtros. Se a criacao de um novo filtro falhar, os novos filtros sao revertidos e os antigos sao preservados.
