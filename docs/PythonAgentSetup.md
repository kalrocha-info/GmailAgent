# Python Agent Setup

Esta versao Python foi criada para fazer a reorganizacao completa do Gmail com mais controle que o Apps Script.

## Objetivo desta entrega

- autenticar via Google OAuth
- ler Gmail e contatos sem alterar nada
- inventariar labels, filtros, mensagens e contatos
- gerar relatorios locais para decidir a nova estrutura
- reclassificar mensagens em lotes controlados
- conduzir a migracao legada em modo autopilot

## Arquivos principais

- [pyproject.toml](/D:/AGENTES-IA/pyproject.toml)
- [python/gmail_agent/cli.py](/D:/AGENTES-IA/python/gmail_agent/cli.py)
- [python/gmail_agent/inventory.py](/D:/AGENTES-IA/python/gmail_agent/inventory.py)

## Preparacao

1. Crie um ambiente virtual Python 3.11+
2. Instale o projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

3. No Google Cloud:
   - crie ou reuse um projeto
   - habilite `Gmail API`
   - habilite `People API`
   - crie credenciais `OAuth Client ID` para aplicativo desktop
   - baixe o arquivo JSON e salve na raiz do projeto como `credentials.json`

## Primeiro uso

Rode:

```powershell
gmail-agent analyze --max-messages 300
```

Na primeira vez, o navegador vai abrir para voce autorizar a conta Google.

## Comandos principais

Inventario inicial:

```powershell
gmail-agent analyze --max-messages 300
```

Plano automatico:

```powershell
gmail-agent autopilot-plan
```

Execucao automatica em ciclos:

```powershell
gmail-agent autopilot-run --cycles 3 --batch-per-label 300
```

Relatorio consolidado do piloto:

```powershell
gmail-agent autopilot-report
```

Limpeza de labels vazias:

```powershell
gmail-agent cleanup-labels --limit 50
```

## Saidas

Os relatorios sao gerados em `reports/`:

- `analysis-*.json`
- `analysis-*.md`
- `autopilot-plan-*.json`
- `autopilot-plan-*.md`
- `autopilot-run-*.json`
- `autopilot-run-*.md`
- `autopilot-report-*.json`
- `autopilot-report-*.md`
- `reports/autopilot-state.json`

## Seguranca

- `credentials.json` e `token.json` estao no `.gitignore`
- a migracao continua em lotes controlados e com relatorios locais
- labels de sistema do Gmail nao devem ser removidas pelo fluxo
- a limpeza final de labels legadas deve acontecer apenas depois do relatorio confirmar que ficaram vazias
