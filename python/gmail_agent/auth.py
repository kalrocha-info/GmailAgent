from __future__ import annotations

import logging
from pathlib import Path

from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .config import AppConfig, SCOPES

logger = logging.getLogger(__name__)


def load_credentials(config: AppConfig) -> Credentials:
    """
    Carrega credenciais OAuth2 do token.json.
    Se o token estiver expirado, tenta renová-lo automaticamente.
    Se a renovação falhar (token revogado ou rede indisponível),
    lança uma exceção clara em vez de encerrar silenciosamente.
    """
    creds: Credentials | None = None

    if config.token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(config.token_file), SCOPES)
        except Exception as exc:
            logger.warning("Falha ao ler token.json: %s — será solicitado novo login.", exc)
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            logger.info("Token expirado. Tentando renovar automaticamente...")
            creds.refresh(Request())
            logger.info("Token renovado com sucesso.")
            _save_token(config.token_file, creds)
            return creds
        except RefreshError as exc:
            logger.error(
                "Falha ao renovar token OAuth (RefreshError): %s\n"
                "O token pode ter sido revogado ou o projeto Google Cloud pode estar em modo 'Teste' "
                "(tokens expiram em 7 dias). Apague o arquivo token.json e execute o agente "
                "manualmente para gerar um novo token.",
                exc,
            )
            raise RuntimeError(
                f"Token OAuth inválido ou revogado. Apague {config.token_file} e "
                "autentique-se novamente executando o agente manualmente.\n"
                f"Detalhe: {exc}"
            ) from exc
        except TransportError as exc:
            logger.error("Erro de rede ao renovar token: %s", exc)
            raise RuntimeError(
                f"Sem conexão de rede para renovar o token OAuth: {exc}"
            ) from exc
        except Exception as exc:
            logger.error("Erro inesperado ao renovar token: %s", exc)
            raise RuntimeError(f"Erro inesperado na autenticação: {exc}") from exc

    # Fluxo interativo — necessário apenas na primeira execução
    _assert_credentials_file(config.credentials_file)
    logger.info("Iniciando fluxo de autenticação interativo...")
    flow = InstalledAppFlow.from_client_secrets_file(
        str(config.credentials_file),
        SCOPES,
    )
    creds = flow.run_local_server(port=0)
    _save_token(config.token_file, creds)
    return creds


def _save_token(path: Path, creds: Credentials) -> None:
    try:
        path.write_text(creds.to_json(), encoding="utf-8")
    except OSError as exc:
        logger.warning("Não foi possível salvar o token renovado em %s: %s", path, exc)


def _assert_credentials_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo de credenciais não encontrado em {path}. "
            "Baixe o OAuth client do Google Cloud e salve como credentials.json na raiz do projeto."
        )
