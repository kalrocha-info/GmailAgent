from __future__ import annotations

from googleapiclient.discovery import build

from .auth import load_credentials
from .config import AppConfig


def _build_services(config: AppConfig):
    """Carrega credenciais uma única vez e constrói ambos os clientes."""
    creds = load_credentials(config)
    gmail = build("gmail", "v1", credentials=creds)
    people = build("people", "v1", credentials=creds)
    return gmail, people


def build_gmail_service(config: AppConfig):
    creds = load_credentials(config)
    return build("gmail", "v1", credentials=creds)


def build_people_service(config: AppConfig):
    creds = load_credentials(config)
    return build("people", "v1", credentials=creds)


def build_all_services(config: AppConfig):
    """Constrói Gmail e People com uma única autenticação. Preferir esta função."""
    return _build_services(config)
