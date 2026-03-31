from __future__ import annotations

import json
from collections import Counter, defaultdict
from email.utils import parseaddr
from pathlib import Path
from typing import Any

from .migration import TARGET_LABELS

LEARNING_TARGETS = [label for label in TARGET_LABELS if label != "AGENTE/REVISAR"]


def load_learning_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_learning_state()
    return json.loads(path.read_text(encoding="utf-8"))


def save_learning_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def empty_learning_state() -> dict[str, Any]:
    return {
        "summary": {
            "messages_considered": 0,
            "messages_with_manual_agent_label": 0,
            "sender_rules": 0,
            "domain_rules": 0,
        },
        "sender_rules": {},
        "domain_rules": {},
    }


def rebuild_learning_state(report: dict[str, Any], min_sender_hits: int = 1, min_domain_hits: int = 2) -> dict[str, Any]:
    labels = report.get("labels", [])
    label_lookup = {label["id"]: label["name"] for label in labels}
    sender_counts: dict[str, Counter] = defaultdict(Counter)
    domain_counts: dict[str, Counter] = defaultdict(Counter)

    messages_considered = 0
    messages_with_manual_agent_label = 0

    for message in report.get("messages", []):
        messages_considered += 1
        resolved_labels = [label_lookup.get(label_id, label_id) for label_id in message.get("labelIds", [])]
        learned_target = _extract_learning_target(resolved_labels)
        if not learned_target:
            continue

        sender_email = extract_sender_email(message.get("from", ""))
        if not sender_email:
            continue

        messages_with_manual_agent_label += 1
        sender_counts[sender_email][learned_target] += 1
        if "@" in sender_email:
            domain_counts[sender_email.split("@", 1)[1]][learned_target] += 1

    sender_rules = _collapse_counters(sender_counts, min_hits=min_sender_hits)
    domain_rules = _collapse_counters(domain_counts, min_hits=min_domain_hits)

    return {
        "summary": {
            "messages_considered": messages_considered,
            "messages_with_manual_agent_label": messages_with_manual_agent_label,
            "sender_rules": len(sender_rules),
            "domain_rules": len(domain_rules),
        },
        "sender_rules": sender_rules,
        "domain_rules": domain_rules,
    }


def extract_sender_email(sender_value: str) -> str:
    return parseaddr(sender_value or "")[1].strip().lower()


def _extract_learning_target(resolved_labels: list[str]) -> str | None:
    preferred = [label for label in resolved_labels if label in LEARNING_TARGETS]
    if not preferred:
        return None
    return preferred[0]


def _collapse_counters(counter_map: dict[str, Counter], min_hits: int) -> dict[str, dict[str, Any]]:
    collapsed = {}
    for key, counts in counter_map.items():
        if not counts:
            continue
        most_common = counts.most_common(2)
        winner, winner_count = most_common[0]
        runner_up_count = most_common[1][1] if len(most_common) > 1 else 0
        if winner_count < min_hits:
            continue
        if winner_count <= runner_up_count:
            continue
        collapsed[key] = {
            "target_label": winner,
            "hits": winner_count,
            "alternatives": dict(counts),
        }
    return collapsed
