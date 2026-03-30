from __future__ import annotations

from typing import Any


def build_label_cleanup_plan(report: dict[str, Any]) -> dict[str, Any]:
    labels = report.get("labels", [])
    legacy_names = {
        item["source_label_name"]
        for item in report.get("reclassification_plan", {}).get("legacy_mapping", [])
    }

    ready_to_delete = []
    review_before_delete = []
    keep = []

    for label in labels:
        name = label["name"]
        if label.get("type") == "system":
            continue
        if name.startswith("AGENTE/"):
            keep.append(_label_summary(label, "label do novo sistema"))
            continue

        summary = _label_summary(label, "label legada")
        is_legacy = name in legacy_names or _looks_legacy(name)
        is_empty = label.get("messagesTotal", 0) == 0 and label.get("threadsTotal", 0) == 0

        if is_legacy and is_empty:
            summary["reason"] = "label legada vazia"
            ready_to_delete.append(summary)
        elif is_legacy:
            summary["reason"] = "label legada ainda com mensagens/threads"
            review_before_delete.append(summary)
        else:
            keep.append(summary)

    return {
        "summary": {
            "ready_to_delete_count": len(ready_to_delete),
            "review_before_delete_count": len(review_before_delete),
            "keep_count": len(keep),
        },
        "ready_to_delete": sorted(ready_to_delete, key=lambda item: item["name"]),
        "review_before_delete": sorted(
            review_before_delete,
            key=lambda item: (-item["messagesTotal"], item["name"]),
        ),
        "keep": sorted(keep, key=lambda item: item["name"]),
        "rules": [
            "Nao remover labels AGENTE.",
            "Nao remover labels de sistema do Gmail.",
            "Remover primeiro apenas labels legadas vazias.",
            "Labels legadas ainda com mensagens devem ser revisadas apos nova rodada de reclassificacao.",
        ],
    }


def execute_label_cleanup_plan(gmail_service, plan: dict[str, Any], limit: int | None = None) -> dict[str, Any]:
    candidates = plan.get("ready_to_delete", [])
    if limit is not None:
        candidates = candidates[:limit]

    deleted = []
    failed = []

    for item in candidates:
        try:
            gmail_service.users().labels().delete(userId="me", id=item["id"]).execute()
            deleted.append(item)
        except Exception as exc:  # noqa: BLE001
            failed.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "error": str(exc),
                }
            )

    return {
        "summary": {
            "requested": len(candidates),
            "deleted": len(deleted),
            "failed": len(failed),
        },
        "deleted": deleted,
        "failed": failed,
    }


def _label_summary(label: dict[str, Any], kind: str) -> dict[str, Any]:
    return {
        "id": label.get("id"),
        "name": label.get("name"),
        "type": label.get("type"),
        "messagesTotal": label.get("messagesTotal", 0),
        "threadsTotal": label.get("threadsTotal", 0),
        "kind": kind,
    }


def _looks_legacy(name: str) -> bool:
    prefixes = ("[Gmail]/", "PT/", "FLUXO/", "IA/", "0_", "1_", "2_", "3_", "4_")
    return name.startswith(prefixes)
