# GmailAgent

Agente inteligente para organizacao de emails no Gmail com foco em:

- classificacao por categoria
- prioridade e triagem
- aprendizado com correcoes manuais
- sugestoes de acao e resposta
- evolucao gradual das regras sem perder controle

## Estrutura do repositorio

- `src/`
  Script principal para colar no Google Apps Script.
- `docs/`
  Documentacao funcional e material de apoio.
- `examples/`
  Arquivos de referencia, como exportacoes de filtros.
- `python/`
  Base Python para analise completa, relatorios, reclassificacao segura e autopilot.

## Arquivos principais

- [src/AgentAppScript.js](/D:/AGENTES-IA/src/AgentAppScript.js)
- [docs/Documentacao_AgentAppScript.md](/D:/AGENTES-IA/docs/Documentacao_AgentAppScript.md)
- [docs/PythonAgentSetup.md](/D:/AGENTES-IA/docs/PythonAgentSetup.md)
- [examples/mailFilters.xml](/D:/AGENTES-IA/examples/mailFilters.xml)
- [pyproject.toml](/D:/AGENTES-IA/pyproject.toml)

## Como testar no Google Apps Script

1. Abra [script.google.com](https://script.google.com)
2. Crie um novo projeto
3. Apague o conteudo padrao de `Codigo.gs`
4. Copie o conteudo de [src/AgentAppScript.js](/D:/AGENTES-IA/src/AgentAppScript.js) para o projeto
5. Salve o projeto
6. Execute `runFirstTimeSetup()` para a primeira configuracao
7. Depois execute `analyzeInbox()` para revisar a classificacao e o aprendizado

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

## Proximos passos sugeridos

- testar o script no Apps Script
- validar as primeiras regras aprendidas
- revisar filtros antigos exportados em [examples/mailFilters.xml](/D:/AGENTES-IA/examples/mailFilters.xml)
- decidir quando habilitar arquivamento automatico
- executar a base Python em modo `analyze` para inventariar toda a conta antes da reclassificacao em massa

## Fluxo Python recomendado

1. Rode `gmail-agent analyze --max-messages 300` para gerar o inventario inicial.
2. Rode `gmail-agent autopilot-plan` para ver a fila de migracao automatica.
3. Rode `gmail-agent autopilot-run --cycles 3 --batch-per-label 300` para migrar labels legadas em segundo plano.
4. Rode `gmail-agent autopilot-report` para revisar o estado consolidado antes da limpeza final.
5. Rode `gmail-agent cleanup-labels --limit 50` apenas quando o relatorio mostrar labels vazias prontas para exclusao.
