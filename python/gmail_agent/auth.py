from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .config import AppConfig, SCOPES


def load_credentials(config: AppConfig) -> Credentials:
    creds = None
    if config.token_file.exists():
        creds = Credentials.from_authorized_user_file(str(config.token_file), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        _assert_credentials_file(config.credentials_file)
        flow = InstalledAppFlow.from_client_secrets_file(
            str(config.credentials_file),
            SCOPES,
        )
        creds = flow.run_local_server(port=0)

    config.token_file.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _assert_credentials_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo de credenciais nao encontrado em {path}. "
            "Baixe o OAuth client do Google Cloud e salve como credentials.json na raiz do projeto."
        )
