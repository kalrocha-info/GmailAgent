from __future__ import annotations

from collections import Counter
from collections import defaultdict
from typing import Any

from .config import AppConfig


def analyze_workspace(
    gmail_service,
    people_service,
    config: AppConfig,
    max_messages: int,
    query: str | None = None,
    label_ids: list[str] | None = None,
    include_filters: bool = True,
    include_contacts: bool = True,
) -> dict[str, Any]:
    labels = fetch_labels(gmail_service)
    filters = fetch_filters(gmail_service) if include_filters else []
    messages = fetch_messages(gmail_service, max_messages, query=query, label_ids=label_ids)
    contacts = fetch_contacts(people_service, config.contact_page_size) if include_contacts else []

    label_usage = count_label_usage(messages)
    label_lookup = {label["id"]: label["name"] for label in labels}
    resolved_label_usage = resolve_label_usage(label_usage, label_lookup)
    label_analysis = analyze_labels(labels, label_usage)
    filter_analysis = analyze_filters(filters, label_lookup)
    proposed_structure = build_proposed_structure(label_analysis, filter_analysis)

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
        "label_usage_resolved": resolved_label_usage,
        "label_analysis": label_analysis,
        "filter_analysis": filter_analysis,
        "proposed_structure": proposed_structure,
        "recommendations": build_recommendations(labels, filters, label_usage, label_analysis, filter_analysis),
    }


def fetch_labels(gmail_service) -> list[dict[str, Any]]:
    response = gmail_service.users().labels().list(userId="me").execute()
    labels = response.get("labels", [])
    detailed = []
    for item in labels:
        full = gmail_service.users().labels().get(userId="me", id=item.get("id")).execute()
        detailed.append(
            {
                "id": full.get("id"),
                "name": full.get("name"),
                "type": full.get("type"),
                "messagesTotal": full.get("messagesTotal", 0),
                "messagesUnread": full.get("messagesUnread", 0),
                "threadsTotal": full.get("threadsTotal", 0),
                "threadsUnread": full.get("threadsUnread", 0),
            }
        )
    return detailed


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


def fetch_messages(
    gmail_service,
    max_messages: int,
    query: str | None = None,
    label_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    page_token = None
    collected = []

    while len(collected) < max_messages:
        kwargs = {
            "userId": "me",
            "includeSpamTrash": False,
            "maxResults": min(100, max_messages - len(collected)),
            "pageToken": page_token,
        }
        if query:
            kwargs["q"] = query
        if label_ids:
            kwargs["labelIds"] = label_ids

        response = gmail_service.users().messages().list(**kwargs).execute()

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


def resolve_label_usage(label_usage: Counter, label_lookup: dict[str, str]) -> list[dict[str, Any]]:
    resolved = []
    for label_id, count in sorted(label_usage.items(), key=lambda item: (-item[1], item[0])):
        resolved.append(
            {
                "id": label_id,
                "name": label_lookup.get(label_id, label_id),
                "count": count,
            }
        )
    return resolved


def analyze_labels(labels: list[dict[str, Any]], label_usage: Counter) -> dict[str, Any]:
    user_labels = [label for label in labels if label.get("type") == "user"]
    system_labels = [label for label in labels if label.get("type") == "system"]
    by_prefix = defaultdict(list)

    for label in user_labels:
        name = label["name"]
        if "/" in name:
            prefix = name.split("/", 1)[0]
        elif "_" in name:
            prefix = name.split("_", 1)[0]
        else:
            prefix = "SEM_GRUPO"
        by_prefix[prefix].append(label)

    unused = []
    active = []
    agent_labels = []
    legacy_candidates = []

    for label in user_labels:
        usage = label_usage.get(label["id"], 0)
        enriched = {
            "id": label["id"],
            "name": label["name"],
            "usage_in_sample": usage,
        }
        if usage == 0:
            unused.append(enriched)
        else:
            active.append(enriched)
        if label["name"].startswith("AGENTE/"):
            agent_labels.append(enriched)
        if not label["name"].startswith("AGENTE/") and _is_legacy_label_name(label["name"]):
            legacy_candidates.append(enriched)

    grouped_prefixes = [
        {
            "prefix": prefix,
            "count": len(items),
            "labels": sorted(label["name"] for label in items),
        }
        for prefix, items in sorted(by_prefix.items(), key=lambda item: (-len(item[1]), item[0]))
    ]

    return {
        "system_labels_total": len(system_labels),
        "user_labels_total": len(user_labels),
        "grouped_prefixes": grouped_prefixes,
        "active_user_labels": sorted(active, key=lambda item: (-item["usage_in_sample"], item["name"])),
        "unused_user_labels": sorted(unused, key=lambda item: item["name"]),
        "agent_labels": sorted(agent_labels, key=lambda item: item["name"]),
        "legacy_candidates": sorted(legacy_candidates, key=lambda item: (-item["usage_in_sample"], item["name"])),
    }


def analyze_filters(filters: list[dict[str, Any]], label_lookup: dict[str, str]) -> dict[str, Any]:
    grouped = defaultdict(list)
    action_counter = Counter()
    from_counter = Counter()

    for item in filters:
        normalized = normalize_filter(item, label_lookup)
        signature = f"{normalized['criteria_signature']} -> {normalized['action_signature']}"
        grouped[signature].append(normalized)

        if normalized["action"].get("archive"):
            action_counter["archive"] += 1
        if normalized["action"].get("markImportant"):
            action_counter["mark_important"] += 1
        if normalized["action"].get("addLabels"):
            action_counter["add_label"] += 1

        from_value = normalized["criteria"].get("from")
        if from_value:
            from_counter[from_value] += 1

    duplicate_groups = [
        {
            "signature": signature,
            "count": len(items),
            "filters": items,
        }
        for signature, items in grouped.items()
        if len(items) > 1
    ]

    repeated_senders = [
        {"from": sender, "count": count}
        for sender, count in from_counter.most_common(20)
        if count > 1
    ]

    return {
        "total_filters": len(filters),
        "actions_summary": dict(action_counter),
        "duplicate_groups": duplicate_groups,
        "repeated_senders": repeated_senders,
        "normalized_filters_sample": [normalize_filter(item, label_lookup) for item in filters[:25]],
    }


def normalize_filter(item: dict[str, Any], label_lookup: dict[str, str]) -> dict[str, Any]:
    criteria = item.get("criteria", {})
    action = item.get("action", {})

    add_labels = [label_lookup.get(label_id, label_id) for label_id in action.get("addLabelIds", [])]
    remove_labels = [label_lookup.get(label_id, label_id) for label_id in action.get("removeLabelIds", [])]

    normalized_action = {
        "addLabels": sorted(add_labels),
        "removeLabels": sorted(remove_labels),
        "archive": "INBOX" in remove_labels,
        "markImportant": "IMPORTANT" in add_labels,
        "neverSpam": "SPAM" in remove_labels,
    }

    criteria_signature = "|".join(
        f"{key}={criteria[key]}"
        for key in sorted(criteria)
        if criteria.get(key)
    ) or "sem_criterio"

    action_signature = "|".join(
        [
            f"add={','.join(normalized_action['addLabels'])}" if normalized_action["addLabels"] else "",
            f"remove={','.join(normalized_action['removeLabels'])}" if normalized_action["removeLabels"] else "",
            "archive" if normalized_action["archive"] else "",
            "important" if normalized_action["markImportant"] else "",
        ]
    ).strip("|") or "sem_acao"

    return {
        "id": item.get("id"),
        "criteria": criteria,
        "action": normalized_action,
        "criteria_signature": criteria_signature,
        "action_signature": action_signature,
    }


def build_proposed_structure(label_analysis: dict[str, Any], filter_analysis: dict[str, Any]) -> dict[str, Any]:
    top_legacy = [item["name"] for item in label_analysis["legacy_candidates"][:12]]
    top_duplicates = [
        {
            "signature": item["signature"],
            "count": item["count"],
        }
        for item in filter_analysis["duplicate_groups"][:10]
    ]

    return {
        "root_labels": [
            "AGENTE/URGENTE",
            "AGENTE/TRABALHO/VAGAS",
            "AGENTE/TRABALHO/CANDIDATURAS",
            "AGENTE/TRABALHO/PROJETOS",
            "AGENTE/TRABALHO/CLIENTES-PJ",
            "AGENTE/FINANCEIRO",
            "AGENTE/PESSOAL",
            "AGENTE/PROMOCOES",
            "AGENTE/NOTIFICACOES",
            "AGENTE/REVISAR",
        ],
        "rules": [
            "Reclassificar todos os emails mantendo labels de sistema do Gmail.",
            "Remover labels antigas dos emails somente depois de aplicar a nova classificacao.",
            "Preservar filtros antigos ate a fase de comparacao e consolidacao.",
            "Unificar labels antigas com nomes equivalentes antes de excluir qualquer uma.",
        ],
        "legacy_labels_to_review_first": top_legacy,
        "duplicate_filter_groups_to_review_first": top_duplicates,
    }


def build_recommendations(
    labels: list[dict[str, Any]],
    filters: list[dict[str, Any]],
    label_usage: Counter,
    label_analysis: dict[str, Any],
    filter_analysis: dict[str, Any],
) -> list[str]:
    recommendations = []
    user_labels = [label for label in labels if label.get("type") == "user"]

    if len(user_labels) > 15:
        recommendations.append("Ha muitas labels personalizadas; vale consolidar em uma hierarquia mais curta antes da limpeza final.")
    if filters:
        recommendations.append("Mapear filtros por criterio e acao antes de remover qualquer um; alguns podem estar duplicados ou sobrepostos.")
    unused_labels = [label["name"] for label in user_labels if label_usage.get(label["id"], 0) == 0]
    if unused_labels:
        recommendations.append("Existem labels sem uso recente na amostra analisada; revisar se devem ser arquivadas ou removidas.")
    if filter_analysis["duplicate_groups"]:
        recommendations.append("Foram detectados filtros com assinatura repetida; vale consolidar esses grupos antes da limpeza final.")
    if label_analysis["legacy_candidates"]:
        recommendations.append("Ha labels antigas coexistindo com labels AGENTE; a reclassificacao completa deve remover essa sobreposicao antes da exclusao.")

    recommendations.append("Rodar primeiro em modo analyze/dry-run e so depois habilitar reclassificacao em massa.")
    return recommendations


def _is_legacy_label_name(name: str) -> bool:
    prefixes = (
        "[Gmail]/",
        "0_",
        "1_",
        "2_",
        "3_",
        "4_",
        "PT/",
        "FLUXO/",
        "IA/",
    )
    return name.startswith(prefixes)
