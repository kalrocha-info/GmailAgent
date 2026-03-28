# Python Agent Setup

Esta versao Python foi criada para fazer a reorganizacao completa do Gmail com mais controle que o Apps Script.

## Objetivo desta primeira entrega

- autenticar via Google OAuth
- ler Gmail e contatos sem alterar nada
- inventariar labels, filtros, mensagens e contatos
- gerar relatorios locais para decidir a nova estrutura

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

## Saidas

Os relatorios sao gerados em `reports/`:

- `analysis-*.json`
- `analysis-*.md`

## Seguranca

- `credentials.json` e `token.json` estao no `.gitignore`
- esta primeira versao nao altera emails, labels, filtros ou contatos
- os comandos de reclassificacao e limpeza ainda estao em `dry-run`
