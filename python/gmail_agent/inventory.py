from __future__ import annotations

from collections import Counter
from typing import Any

from .config import AppConfig


def analyze_workspace(gmail_service, people_service, config: AppConfig, max_messages: int) -> dict[str, Any]:
    labels = fetch_labels(gmail_service)
    filters = fetch_filters(gmail_service)
    messages = fetch_messages(gmail_service, max_messages)
    contacts = fetch_contacts(people_service, config.contact_page_size)

    label_usage = count_label_usage(messages)

    return {
        "summary": {
            "messages_sampled": len(messages),
            "labels_total": len(labels),
            "filters_total": len(filters),
            "contacts_total": len(contacts),
        },
        "labels": labels,
        "filters": filters,
        "contacts": contacts,
        "messages": messages,
        "label_usage": dict(sorted(label_usage.items(), key=lambda item: (-item[1], item[0]))),
        "recommendations": build_recommendations(labels, filters, label_usage),
    }


def fetch_labels(gmail_service) -> list[dict[str, Any]]:
    response = gmail_service.users().labels().list(userId="me").execute()
    labels = response.get("labels", [])
    return [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "type": item.get("type"),
            "messagesTotal": item.get("messagesTotal", 0),
            "messagesUnread": item.get("messagesUnread", 0),
            "threadsTotal": item.get("threadsTotal", 0),
            "threadsUnread": item.get("threadsUnread", 0),
        }
        for item in labels
    ]


def fetch_filters(gmail_service) -> list[dict[str, Any]]:
    response = gmail_service.users().settings().filters().list(userId="me").execute()
    filters = response.get("filter", [])
    normalized = []
    for item in filters:
        normalized.append(
            {
                "id": item.get("id"),
                "criteria": item.get("criteria", {}),
                "action": item.get("action", {}),
            }
        )
    return normalized


def fetch_messages(gmail_service, max_messages: int) -> list[dict[str, Any]]:
    page_token = None
    collected = []

    while len(collected) < max_messages:
        response = (
            gmail_service.users()
            .messages()
            .list(
                userId="me",
                includeSpamTrash=False,
                maxResults=min(100, max_messages - len(collected)),
                pageToken=page_token,
            )
            .execute()
        )

        for message in response.get("messages", []):
            full = gmail_service.users().messages().get(
                userId="me",
                id=message["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            collected.append(normalize_message(full))
            if len(collected) >= max_messages:
                break

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return collected


def fetch_contacts(people_service, page_size: int) -> list[dict[str, Any]]:
    contacts = []
    page_token = None

    while True:
        response = (
            people_service.people()
            .connections()
            .list(
                resourceName="people/me",
                pageSize=page_size,
                pageToken=page_token,
                personFields="names,emailAddresses,organizations,memberships",
            )
            .execute()
        )

        for person in response.get("connections", []):
            contacts.append(
                {
                    "resourceName": person.get("resourceName"),
                    "names": [item.get("displayName") for item in person.get("names", []) if item.get("displayName")],
                    "emails": [item.get("value") for item in person.get("emailAddresses", []) if item.get("value")],
                    "organizations": [item.get("name") for item in person.get("organizations", []) if item.get("name")],
                }
            )

        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return contacts


def normalize_message(message: dict[str, Any]) -> dict[str, Any]:
    headers = {
        header.get("name", "").lower(): header.get("value", "")
        for header in message.get("payload", {}).get("headers", [])
    }
    return {
        "id": message.get("id"),
        "threadId": message.get("threadId"),
        "labelIds": message.get("labelIds", []),
        "snippet": message.get("snippet", ""),
        "from": headers.get("from", ""),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", ""),
    }


def count_label_usage(messages: list[dict[str, Any]]) -> Counter:
    counter = Counter()
    for message in messages:
        for label_id in message.get("labelIds", []):
            counter[label_id] += 1
    return counter


def build_recommendations(labels: list[dict[str, Any]], filters: list[dict[str, Any]], label_usage: Counter) -> list[str]:
    recommendations = []
    user_labels = [label for label in labels if label.get("type") == "user"]

    if len(user_labels) > 15:
        recommendations.append("Ha muitas labels personalizadas; vale consolidar em uma hierarquia mais curta antes da limpeza final.")
    if filters:
        recommendations.append("Mapear filtros por criterio e acao antes de remover qualquer um; alguns podem estar duplicados ou sobrepostos.")
    unused_labels = [label["name"] for label in user_labels if label_usage.get(label["id"], 0) == 0]
    if unused_labels:
        recommendations.append("Existem labels sem uso recente na amostra analisada; revisar se devem ser arquivadas ou removidas.")

    recommendations.append("Rodar primeiro em modo analyze/dry-run e so depois habilitar reclassificacao em massa.")
    return recommendations
