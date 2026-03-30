from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .cleanup import build_label_cleanup_plan
from .inventory import analyze_workspace
from .migration import build_reclassification_plan, execute_reclassification_plan

LEGACY_LABEL_PRIORITY = [
    "1_FINANCEIRO",
    "[Gmail]/01_COMPRAS",
    "[Gmail]/00_FINANCEIRO",
    "[Gmail]/00_GESTAO",
    "[Gmail]/02_SAUDE",
    "3_VAGAS_PROMOCOES",
    "FLUXO/LinkedIn",
    "4_REDES_SOCIAIS",
    "0_URGENTE",
    "2_ESTUDOS",
]


def enrich_report(report: dict[str, Any]) -> dict[str, Any]:
    report["reclassification_plan"] = build_reclassification_plan(report)
    report["cleanup_plan"] = build_label_cleanup_plan(report)
    return report


def build_autopilot_snapshot(gmail_service, people_service, config) -> dict[str, Any]:
    return analyze_workspace(
        gmail_service=gmail_service,
        people_service=people_service,
        config=config,
        max_messages=1,
        include_filters=False,
        include_contacts=False,
    )


def build_autopilot_plan(report: dict[str, Any]) -> dict[str, Any]:
    cleanup_plan = build_label_cleanup_plan(report)
    review = cleanup_plan.get("review_before_delete", [])
    ordered = sorted(
        review,
        key=lambda item: (_priority_index(item["name"]), -item["messagesTotal"], item["name"]),
    )

    queue = []
    for item in ordered:
        queue.append(
            {
                "id": item["id"],
                "name": item["name"],
                "messagesTotal": item["messagesTotal"],
                "threadsTotal": item["threadsTotal"],
                "priority": _priority_index(item["name"]) + 1,
                "suggested_query": f'label:"{item["name"]}"',
            }
        )

    return {
        "summary": {
            "labels_pending_migration": len(queue),
            "labels_ready_to_delete": cleanup_plan.get("summary", {}).get("ready_to_delete_count", 0),
        },
        "queue": queue,
        "ready_to_delete": cleanup_plan.get("ready_to_delete", []),
        "rules": [
            "Priorizar labels legadas com maior impacto e maior clareza de mapeamento.",
            "Rodar reclassificacao dirigida por label em lotes controlados.",
            "Rerodar cleanup-dry-run apos cada ciclo automatico.",
            "Parar quando nao houver mais progresso relevante ou quando restarem apenas labels ambiguas.",
        ],
        "next_step": (
            'Rodar `gmail-agent autopilot-run --cycles 3 --batch-per-label 300` '
            "para migrar as labels legadas prioritarias em background."
        ),
    }


def run_autopilot(
    gmail_service,
    people_service,
    config,
    cycles: int,
    batch_per_label: int,
) -> dict[str, Any]:
    executions = []
    attempted_without_progress: set[str] = set()
    stop_reason = "cycles_exhausted"

    for cycle_number in range(1, cycles + 1):
        baseline_report = build_autopilot_snapshot(
            gmail_service=gmail_service,
            people_service=people_service,
            config=config,
        )
        plan = build_autopilot_plan(baseline_report)
        queue = [
            item
            for item in plan.get("queue", [])
            if item["name"] not in attempted_without_progress
        ]

        if not queue:
            stop_reason = "no_pending_labels"
            break

        target_item = queue[0]
        target = target_item["name"]
        target_id = target_item["id"]
        before_count = _label_message_total(baseline_report.get("labels", []), target)
        target_report = analyze_workspace(
            gmail_service=gmail_service,
            people_service=people_service,
            config=config,
            max_messages=batch_per_label,
            label_ids=[target_id],
            include_filters=False,
            include_contacts=False,
        )
        execution = execute_reclassification_plan(
            gmail_service=gmail_service,
            report=target_report,
            limit=batch_per_label,
        )
        after_report = build_autopilot_snapshot(
            gmail_service=gmail_service,
            people_service=people_service,
            config=config,
        )
        after_count = _label_message_total(after_report.get("labels", []), target)
        changed = execution.get("summary", {}).get("messages_changed", 0)
        delta = before_count - after_count

        if changed == 0 and delta <= 0:
            attempted_without_progress.add(target)
        else:
            attempted_without_progress.discard(target)

        execution.update(
            {
                "cycle": cycle_number,
                "source_label": target,
                "before_messages_total": before_count,
                "after_messages_total": after_count,
                "label_delta": delta,
            }
        )
        executions.append(execution)

        if changed == 0 and delta <= 0 and len(attempted_without_progress) >= len(queue):
            stop_reason = "no_progress"
            break

    final_report = build_autopilot_snapshot(
        gmail_service=gmail_service,
        people_service=people_service,
        config=config,
    )
    final_cleanup = build_label_cleanup_plan(final_report)
    final_plan = build_autopilot_plan(final_report)

    return {
        "summary": {
            "cycles_requested": cycles,
            "cycles_executed": len(executions),
            "batch_per_label": batch_per_label,
            "labels_ready_to_delete": final_cleanup.get("summary", {}).get("ready_to_delete_count", 0),
            "labels_still_pending": final_cleanup.get("summary", {}).get("review_before_delete_count", 0),
            "stop_reason": stop_reason,
        },
        "executions": executions,
        "attempted_without_progress": sorted(attempted_without_progress),
        "final_plan": final_plan,
        "final_cleanup": final_cleanup,
    }


def render_autopilot_plan(plan: dict[str, Any]) -> str:
    summary = plan.get("summary", {})
    queue = plan.get("queue", [])

    lines = [
        "# Autopilot Plan",
        "",
        f"- Labels pendentes de migracao: {summary.get('labels_pending_migration', 0)}",
        f"- Labels prontas para exclusao: {summary.get('labels_ready_to_delete', 0)}",
        "",
        "## Fila sugerida de migracao",
        "",
    ]

    if queue:
        for item in queue[:20]:
            lines.append(
                f"- `{item['name']}` ({item['messagesTotal']} mensagens, {item['threadsTotal']} threads, prioridade {item['priority']})"
            )
    else:
        lines.append("- Nenhuma label legada pendente.")

    lines.extend(["", "## Regras do piloto automatico", ""])
    for rule in plan.get("rules", []):
        lines.append(f"- {rule}")

    next_step = plan.get("next_step")
    if next_step:
        lines.extend(["", "## Proximo passo", "", f"- {next_step}"])

    return "\n".join(lines) + "\n"


def render_autopilot_run(result: dict[str, Any]) -> str:
    summary = result.get("summary", {})
    executions = result.get("executions", [])
    cleanup = result.get("final_cleanup", {})
    final_plan = result.get("final_plan", {})

    lines = [
        "# Autopilot Run",
        "",
        f"- Ciclos solicitados: {summary.get('cycles_requested', 0)}",
        f"- Ciclos executados: {summary.get('cycles_executed', 0)}",
        f"- Lote por label: {summary.get('batch_per_label', 0)}",
        f"- Motivo de parada: {summary.get('stop_reason', 'desconhecido')}",
        f"- Labels prontas para exclusao apos a execucao: {summary.get('labels_ready_to_delete', 0)}",
        f"- Labels ainda pendentes: {summary.get('labels_still_pending', 0)}",
        "",
        "## Ciclos executados",
        "",
    ]

    if executions:
        for item in executions:
            exec_summary = item.get("summary", {})
            lines.append(
                f"- Ciclo {item.get('cycle', '?')}: `{item.get('source_label', '')}` -> "
                f"{exec_summary.get('messages_changed', 0)} alteradas, "
                f"{exec_summary.get('messages_skipped', 0)} ignoradas, "
                f"delta da label {item.get('label_delta', 0)}"
            )
    else:
        lines.append("- Nenhum ciclo executado.")

    stalled = result.get("attempted_without_progress", [])
    if stalled:
        lines.extend(["", "## Labels sem progresso nesta rodada", ""])
        for item in stalled:
            lines.append(f"- `{item}`")

    ready = cleanup.get("ready_to_delete", [])
    lines.extend(["", "## Labels prontas para exclusao agora", ""])
    if ready:
        for item in ready[:20]:
            lines.append(f"- `{item['name']}`")
    else:
        lines.append("- Nenhuma label pronta para exclusao ainda.")

    queue = final_plan.get("queue", [])
    lines.extend(["", "## Proximas labels sugeridas", ""])
    if queue:
        for item in queue[:10]:
            lines.append(f"- `{item['name']}` ({item['messagesTotal']} mensagens)")
    else:
        lines.append("- Nenhuma label legada pendente.")

    return "\n".join(lines) + "\n"


def render_autopilot_report(
    report: dict[str, Any],
    cleanup_plan: dict[str, Any],
    state: dict[str, Any] | None = None,
) -> str:
    summary = report.get("summary", {})
    review = cleanup_plan.get("review_before_delete", [])
    ready = cleanup_plan.get("ready_to_delete", [])
    ordered = sorted(
        review,
        key=lambda item: (_priority_index(item["name"]), -item["messagesTotal"], item["name"]),
    )

    lines = [
        "# Autopilot Report",
        "",
        f"- Mensagens amostradas agora: {summary.get('messages_sampled', 0)}",
        f"- Labels prontas para exclusao: {len(ready)}",
        f"- Labels ainda pendentes de migracao: {len(review)}",
    ]

    if state:
        state_summary = state.get("summary", {})
        lines.extend(
            [
                f"- Ultimo autopilot-run executou {state_summary.get('cycles_executed', 0)} ciclo(s)",
                f"- Ultimo motivo de parada: {state_summary.get('stop_reason', 'desconhecido')}",
            ]
        )

    lines.extend(["", "## Proximas labels a atacar", ""])
    if ordered:
        for item in ordered[:15]:
            lines.append(f"- `{item['name']}` ({item['messagesTotal']} mensagens, {item['threadsTotal']} threads)")
    else:
        lines.append("- Nenhuma label pendente.")

    lines.extend(["", "## Labels prontas para exclusao", ""])
    if ready:
        for item in ready[:20]:
            lines.append(f"- `{item['name']}`")
    else:
        lines.append("- Nenhuma label pronta ainda.")

    lines.extend(["", "## Acao recomendada", ""])
    if ordered:
        lines.append("- Rodar `gmail-agent autopilot-run --cycles 3 --batch-per-label 300` para continuar a migracao automatica.")
    else:
        lines.append("- Rodar `gmail-agent cleanup-labels --limit 50` se o relatorio estiver de acordo com o esperado.")

    return "\n".join(lines) + "\n"


def write_state(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def read_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _priority_index(name: str) -> int:
    try:
        return LEGACY_LABEL_PRIORITY.index(name)
    except ValueError:
        return len(LEGACY_LABEL_PRIORITY) + 1


def _label_message_total(labels: list[dict[str, Any]], name: str) -> int:
    for item in labels:
        if item.get("name") == name:
            return item.get("messagesTotal", 0)
    return 0
