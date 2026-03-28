from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    project_root: Path
    credentials_file: Path
    token_file: Path
    reports_dir: Path
    gmail_page_size: int = 100
    contact_page_size: int = 200


SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://www.googleapis.com/auth/contacts.readonly",
]


def load_config() -> AppConfig:
    project_root = Path(__file__).resolve().parents[2]
    return AppConfig(
        project_root=project_root,
        credentials_file=project_root / "credentials.json",
        token_file=project_root / "token.json",
        reports_dir=project_root / "reports",
    )
