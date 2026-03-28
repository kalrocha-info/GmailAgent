# Documentacao do Agente Inteligente de Gmail

Este script foi reorganizado para funcionar primeiro como um agente de analise e aprendizado, e so depois como executor de automacoes aprovadas.

## O que ele faz agora

- Classifica emails em `URGENTE`, `TRABALHO`, `PESSOAL`, `PROMOCOES` e `NOTIFICACOES`
- Define prioridade em `alta`, `media` ou `baixa`
- Gera resumo curto, acao sugerida e resposta sugerida
- Aprende com suas correcoes manuais de labels
- Cria regras dinamicas por remetente, dominio, assunto e palavras-chave
- Reaplica essas regras em emails futuros semelhantes, mesmo quando o remetente exato muda

## Como o aprendizado funciona

1. Voce corrige manualmente um email no Gmail aplicando uma label do agente, por exemplo:
   - `AGENTE/URGENTE`
   - `AGENTE/TRABALHO`
   - `AGENTE/PESSOAL`
   - `AGENTE/PROMOCOES`
   - `AGENTE/NOTIFICACOES`
2. Na proxima execucao, a funcao `learnFromUserCorrections()` le esses ajustes.
3. O script grava sinais aprendidos em `ScriptProperties`:
   - remetente exato
   - dominio do remetente
   - assunto normalizado
   - palavras-chave recorrentes
4. A funcao `buildFullPlan()` transforma esse historico em novas regras dinamicas.
5. Emails futuros podem ser classificados mesmo quando:
   - vem de outro remetente do mesmo dominio
   - repetem o mesmo assunto
   - compartilham palavras-chave recorrentes

## Ordem de prioridade do aprendizado

Quando houver mais de uma pista aprendida, o agente decide nesta ordem:

1. Remetente exato
2. Assunto aprendido
3. Dominio com confianca suficiente
4. Palavra-chave com confianca suficiente

Isso ajuda a manter o comportamento previsivel e evita generalizacoes cedo demais.

## Funcoes principais

### `runFirstTimeSetup()`
Executa a varredura historica inicial e limpa estados antigos.

### `executePlan()`
Orquestra o processamento das regras estaticas e dinamicas.

### `analyzeInbox()`
Analisa emails recentes e retorna um relatorio estruturado em JSON no Logger.

### `learnFromUserCorrections()`
Aprende com labels ajustadas manualmente por voce e persiste novas regras.

### `getLearnedCategoryForThread()`
Consulta o aprendizado em varios niveis antes de cair nas heuristicas padrao.

## Modo seguro

- `ENABLE_AUTO_ARCHIVE` comeca como `false`
- O script nao deve arquivar automaticamente sem sua confirmacao
- Emails de alta prioridade recebem destaque para revisao

## Labels usadas

- `AGENTE/URGENTE`
- `AGENTE/TRABALHO`
- `AGENTE/PESSOAL`
- `AGENTE/PROMOCOES`
- `AGENTE/NOTIFICACOES`
- `AGENTE/REVISAR`

## Instalacao

1. Abra [script.google.com](https://script.google.com)
2. Crie um novo projeto
3. Cole o conteudo de [AgentAppScript.js](/D:/AGENTES-IA/AgentAppScript.js)
4. Salve
5. Execute `runFirstTimeSetup()` uma vez
6. Depois use `analyzeInbox()` para revisar os resultados e confirmar o comportamento

## Observacao importante

O aprendizado agora usa multiplos sinais. Ainda assim, remetente e assunto pesam mais que dominio e palavra-chave. Dominio e palavras-chave exigem repeticao maior para ganhar confianca e evitar classificacoes amplas demais.
