from __future__ import annotations

from googleapiclient.discovery import build

from .auth import load_credentials
from .config import AppConfig


def build_gmail_service(config: AppConfig):
    creds = load_credentials(config)
    return build("gmail", "v1", credentials=creds)


def build_people_service(config: AppConfig):
    creds = load_credentials(config)
    return build("people", "v1", credentials=creds)
