from __future__ import annotations

import logging
from pathlib import Path

from .autopilot import (
    build_autopilot_snapshot,
    build_autopilot_plan,
    read_state,
    render_autopilot_plan,
    render_autopilot_report,
    render_autopilot_run,
    run_autopilot,
    write_state,
)
from .config import load_config
from .cleanup import build_label_cleanup_plan, execute_label_cleanup_plan
from .google_clients import build_all_services, build_gmail_service
from .inventory import analyze_workspace
from .learning import rebuild_learning_state, save_learning_state
from .migration import (
    apply_learning_state,
    archive_stale_inbox_messages,
    build_reclassification_plan,
    execute_reclassification_plan,
)
from .reporting import ensure_reports_dir, utc_stamp, write_json, write_markdown

logger = logging.getLogger(__name__)


def run_health_check() -> str:
    """Verifica se o token OAuth está válido e a conexão à API Gmail funciona."""
    config = load_config()
    logger.info("Iniciando health check...")
    try:
        gmail_service, _ = build_all_services(config)
        profile = gmail_service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress", "desconhecido")
        total = profile.get("messagesTotal", 0)
        result = (
            f"✅ Health check OK\n"
            f"   Conta: {email}\n"
            f"   Total de mensagens: {total}\n"
            f"   Token: válido"
        )
        logger.info("Health check OK: %s (%d mensagens)", email, total)
        return result
    except Exception as exc:
        result = f"❌ Health check FALHOU: {exc}"
        logger.error("Health check falhou: %s", exc)
        return result


def run_analyze(max_messages: int) -> tuple[Path, Path]:
    config = load_config()
    ensure_reports_dir(config.reports_dir)
    gmail_service, people_service = build_all_services(config)

    report = analyze_workspace(
        gmail_service=gmail_service,
        people_service=people_service,
        config=config,
        max_messages=max_messages,
    )

    stamp = utc_stamp()
    json_path = config.reports_dir / f"analysis-{stamp}.json"
    md_path = config.reports_dir / f"analysis-{stamp}.md"
    write_json(json_path, report)
    write_markdown(md_path, _render_markdown_summary(report, max_messages))
    return json_path, md_path


def run_reclassify_dry_run(limit: int) -> str:
    config = load_config()
    ensure_reports_dir(config.reports_dir)
    gmail_service, people_service = build_all_services(config)

    report = analyze_workspace(
        gmail_service=gmail_service,
        people_service=people_service,
        config=config,
        max_messages=limit,
    )
    plan = build_reclassification_plan(report)

    stamp = utc_stamp()
    json_path = config.reports_dir / f"reclassify-dry-run-{stamp}.json"
    md_path = config.reports_dir / f"reclassify-dry-run-{stamp}.md"
    write_json(json_path, plan)
    write_markdown(md_path, _render_reclassify_dry_run(plan))
    return f"Relatorios gerados:\n- {json_path}\n- {md_path}"


def run_cleanup_dry_run() -> str:
    config = load_config()
    ensure_reports_dir(config.reports_dir)
    gmail_service, people_service = build_all_services(config)

    report = analyze_workspace(
        gmail_service=gmail_service,
        people_service=people_service,
        config=config,
        max_messages=500,
    )
    report["reclassification_plan"] = build_reclassification_plan(report)
    plan = build_label_cleanup_plan(report)

    stamp = utc_stamp()
    json_path = config.reports_dir / f"cleanup-dry-run-{stamp}.json"
    md_path = config.reports_dir / f"cleanup-dry-run-{stamp}.md"
    write_json(json_path, plan)
    write_markdown(md_path, _render_cleanup_dry_run(plan))
    return f"Relatorios gerados:\n- {json_path}\n- {md_path}"


def run_reclassify(limit: int) -> str:
    config = load_config()
    ensure_reports_dir(config.reports_dir)
    gmail_service, people_service = build_all_services(config)

    report = analyze_workspace(
        gmail_service=gmail_service,
        people_service=people_service,
        config=config,
        max_messages=limit,
    )
    result = execute_reclassification_plan(
        gmail_service=gmail_service,
        report=report,
        limit=limit,
    )

    stamp = utc_stamp()
    json_path = config.reports_dir / f"reclassify-{stamp}.json"
    md_path = config.reports_dir / f"reclassify-{stamp}.md"
    write_json(json_path, result)
    write_markdown(md_path, _render_reclassify_result(result))
    return f"Relatorios gerados:\n- {json_path}\n- {md_path}"


def run_reclassify_label(label_name: str, limit: int) -> str:
    config = load_config()
    ensure_reports_dir(config.reports_dir)
    gmail_service, people_service = build_all_services(config)

    query = f'label:"{label_name}"'
    report = analyze_workspace(
        gmail_service=gmail_service,
        people_service=people_service,
        config=config,
        max_messages=limit,
        query=query,
    )
    result = execute_reclassification_plan(
        gmail_service=gmail_service,
        report=report,
        limit=limit,
    )
    result["source_label"] = label_name

    stamp = utc_stamp()
    safe_label_name = (
        label_name.replace("/", "-")
        .replace("[", "")
        .replace("]", "")
        .replace(" ", "_")
    )
    json_path = config.reports_dir / f"reclassify-label-{safe_label_name}-{stamp}.json"
    md_path = config.reports_dir / f"reclassify-label-{safe_label_name}-{stamp}.md"
    write_json(json_path, result)
    write_markdown(md_path, _render_reclassify_label_result(result))
    return f"Relatorios gerados:\n- {json_path}\n- {md_path}"


def run_cleanup_labels(limit: int | None) -> str:
    config = load_config()
    ensure_reports_dir(config.reports_dir)
    gmail_service, people_service = build_all_services(config)

    report = analyze_workspace(
        gmail_service=gmail_service,
        people_service=people_service,
        config=config,
        max_messages=500,
    )
    report["reclassification_plan"] = build_reclassification_plan(report)
    plan = build_label_cleanup_plan(report)
    result = execute_label_cleanup_plan(gmail_service, plan, limit=limit)

    stamp = utc_stamp()
    json_path = config.reports_dir / f"cleanup-labels-{stamp}.json"
    md_path = config.reports_dir / f"cleanup-labels-{stamp}.md"
    write_json(json_path, result)
    write_markdown(md_path, _render_cleanup_labels_result(result))
    return f"Relatorios gerados:\n- {json_path}\n- {md_path}"


def run_maintain_recent(limit: int, recent_days: int, learning_days: int) -> str:
    config = load_config()
    ensure_reports_dir(config.reports_dir)
    config.state_dir.mkdir(parents=True, exist_ok=True)
    logger.info(
        "run_maintain_recent: limit=%d, recent_days=%d, learning_days=%d",
        limit, recent_days, learning_days,
    )
    gmail_service = build_gmail_service(config)

    learning_report = analyze_workspace(
        gmail_service=gmail_service,
        people_service=None,
        config=config,
        max_messages=1000,
        query=f"newer_than:{learning_days}d",
        include_filters=False,
        include_contacts=False,
    )
    learning_state = rebuild_learning_state(learning_report)
    save_learning_state(config.learning_rules_file, learning_state)
    apply_learning_state(learning_state)

    inbox_report = analyze_workspace(
        gmail_service=gmail_service,
        people_service=None,
        config=config,
        max_messages=limit,
        query=f"in:inbox newer_than:{recent_days}d",
        include_filters=False,
        include_contacts=False,
    )
    recent_report = inbox_report

    inbox_messages = inbox_report.get("messages", [])
    if len(inbox_messages) < limit:
        overflow_report = analyze_workspace(
            gmail_service=gmail_service,
            people_service=None,
            config=config,
            max_messages=limit,
            query=f"newer_than:{recent_days}d",
            include_filters=False,
            include_contacts=False,
        )
        merged_messages = []
        seen_ids = set()
        for message in inbox_messages + overflow_report.get("messages", []):
            message_id = message.get("id")
            if not message_id or message_id in seen_ids:
                continue
            seen_ids.add(message_id)
            merged_messages.append(message)
            if len(merged_messages) >= limit:
                break
        recent_report = {
            **overflow_report,
            "messages": merged_messages,
            "summary": {
                **overflow_report.get("summary", {}),
                "messages_sampled": len(merged_messages),
            },
        }

    result = execute_reclassification_plan(
        gmail_service=gmail_service,
        report=recent_report,
        limit=limit,
    )
    stale_report = analyze_workspace(
        gmail_service=gmail_service,
        people_service=None,
        config=config,
        max_messages=limit,
        query="older_than:2d in:inbox -is:unread",
        include_filters=False,
        include_contacts=False,
    )
    stale_cleanup = archive_stale_inbox_messages(
        gmail_service=gmail_service,
        report=stale_report,
        limit=limit,
    )
    payload = {
        "summary": result.get("summary", {}),
        "stale_cleanup_summary": stale_cleanup.get("summary", {}),
        "learning_summary": learning_state.get("summary", {}),
        "learning_rules_file": str(config.learning_rules_file),
        "changed": result.get("changed", []),
        "skipped": result.get("skipped", []),
        "stale_archived": stale_cleanup.get("archived", []),
        "stale_skipped": stale_cleanup.get("skipped", []),
    }

    stamp = utc_stamp()
    json_path = config.reports_dir / f"maintain-recent-{stamp}.json"
    md_path = config.reports_dir / f"maintain-recent-{stamp}.md"
    write_json(json_path, payload)
    write_markdown(md_path, _render_maintain_recent_result(payload, recent_days, learning_days))
    return f"Relatorios gerados:\n- {json_path}\n- {md_path}\n- {config.learning_rules_file}"


def run_autopilot_plan() -> str:
    config = load_config()
    ensure_reports_dir(config.reports_dir)
    gmail_service, people_service = build_all_services(config)

    report = build_autopilot_snapshot(
        gmail_service=gmail_service,
        people_service=people_service,
        config=config,
    )
    plan = build_autopilot_plan(report)

    stamp = utc_stamp()
    json_path = config.reports_dir / f"autopilot-plan-{stamp}.json"
    md_path = config.reports_dir / f"autopilot-plan-{stamp}.md"
    write_json(json_path, plan)
    write_markdown(md_path, render_autopilot_plan(plan))
    return f"Relatorios gerados:\n- {json_path}\n- {md_path}"


def run_autopilot_command(cycles: int, batch_per_label: int) -> str:
    config = load_config()
    ensure_reports_dir(config.reports_dir)
    gmail_service, people_service = build_all_services(config)

    result = run_autopilot(
        gmail_service=gmail_service,
        people_service=people_service,
        config=config,
        cycles=cycles,
        batch_per_label=batch_per_label,
    )

    stamp = utc_stamp()
    json_path = config.reports_dir / f"autopilot-run-{stamp}.json"
    md_path = config.reports_dir / f"autopilot-run-{stamp}.md"
    state_path = config.reports_dir / "autopilot-state.json"
    write_json(json_path, result)
    write_markdown(md_path, render_autopilot_run(result))
    write_state(state_path, result)
    return f"Relatorios gerados:\n- {json_path}\n- {md_path}\n- {state_path}"


def run_autopilot_report() -> str:
    config = load_config()
    ensure_reports_dir(config.reports_dir)
    gmail_service, people_service = build_all_services(config)

    report = build_autopilot_snapshot(
        gmail_service=gmail_service,
        people_service=people_service,
        config=config,
    )
    cleanup_plan = build_label_cleanup_plan(report)
    state_path = config.reports_dir / "autopilot-state.json"
    state = read_state(state_path)

    stamp = utc_stamp()
    json_path = config.reports_dir / f"autopilot-report-{stamp}.json"
    md_path = config.reports_dir / f"autopilot-report-{stamp}.md"
    payload = {
        "report_summary": report.get("summary", {}),
        "cleanup_summary": cleanup_plan.get("summary", {}),
        "ready_to_delete": cleanup_plan.get("ready_to_delete", []),
        "review_before_delete": cleanup_plan.get("review_before_delete", []),
        "autopilot_state_summary": (state or {}).get("summary", {}),
    }
    write_json(json_path, payload)
    write_markdown(md_path, render_autopilot_report(report, cleanup_plan, state=state))
    return f"Relatorios gerados:\n- {json_path}\n- {md_path}"


def _render_markdown_summary(report: dict, max_messages: int) -> str:
    summary = report["summary"]
    recommendations = report.get("recommendations", [])
    top_labels = report.get("label_usage_resolved", [])[:12]
    label_analysis = report.get("label_analysis", {})
    filter_analysis = report.get("filter_analysis", {})
    proposed = report.get("proposed_structure", {})

    lines = [
        "# Relatorio de Analise do Gmail",
        "",
        f"- Mensagens analisadas na amostra: {summary['messages_sampled']} de ate {max_messages}",
        f"- Labels totais: {summary['labels_total']}",
        f"- Filtros totais: {summary['filters_total']}",
        f"- Contatos totais: {summary['contacts_total']}",
        "",
        "## Labels mais presentes na amostra",
        "",
    ]

    if top_labels:
        for item in top_labels:
            lines.append(f"- `{item['name']}` (`{item['id']}`): {item['count']} mensagens")
    else:
        lines.append("- Nenhuma label encontrada na amostra.")

    lines.extend(["", "## Estrutura atual de labels", ""])
    lines.append(f"- Labels de sistema: {label_analysis.get('system_labels_total', 0)}")
    lines.append(f"- Labels personalizadas: {label_analysis.get('user_labels_total', 0)}")

    grouped_prefixes = label_analysis.get("grouped_prefixes", [])[:10]
    if grouped_prefixes:
        lines.extend(["", "### Grupos de labels", ""])
        for item in grouped_prefixes:
            lines.append(f"- `{item['prefix']}`: {item['count']} labels")

    legacy_candidates = label_analysis.get("legacy_candidates", [])[:12]
    if legacy_candidates:
        lines.extend(["", "### Labels antigas prioritarias para revisao", ""])
        for item in legacy_candidates:
            lines.append(f"- `{item['name']}`: {item['usage_in_sample']} ocorrencias na amostra")

    duplicate_groups = filter_analysis.get("duplicate_groups", [])[:10]
    lines.extend(["", "## Redundancias detectadas em filtros", ""])
    if duplicate_groups:
        for item in duplicate_groups:
            lines.append(f"- {item['count']} filtros compartilham a assinatura `{item['signature']}`")
    else:
        lines.append("- Nenhum grupo duplicado foi encontrado na amostra de filtros normalizados.")

    repeated_senders = filter_analysis.get("repeated_senders", [])[:10]
    if repeated_senders:
        lines.extend(["", "### Remetentes com muitos filtros", ""])
        for item in repeated_senders:
            lines.append(f"- `{item['from']}` aparece em {item['count']} filtros")

    lines.extend(["", "## Nova estrutura recomendada", ""])
    for item in proposed.get("root_labels", []):
        lines.append(f"- `{item}`")

    lines.extend(["", "## Regras de migracao recomendadas", ""])
    for item in proposed.get("rules", []):
        lines.append(f"- {item}")

    lines.extend(["", "## Recomendacoes iniciais", ""])
    for recommendation in recommendations:
        lines.append(f"- {recommendation}")

    return "\n".join(lines) + "\n"


def _render_reclassify_dry_run(plan: dict) -> str:
    summary = plan.get("summary", {})
    mapping = plan.get("legacy_mapping", [])
    sampled_actions = plan.get("sampled_actions", [])

    lines = [
        "# Dry Run de Reclassificacao",
        "",
        f"- Mensagens consideradas: {summary.get('messages_considered', 0)}",
        f"- Mensagens com acao sugerida: {summary.get('messages_with_action', 0)}",
        "",
        "## Contagem por label alvo",
        "",
    ]

    by_target = summary.get("messages_by_target_label", {})
    if by_target:
        for label, count in by_target.items():
            lines.append(f"- `{label}`: {count} mensagens")
    else:
        lines.append("- Nenhuma acao sugerida.")

    lines.extend(["", "## Mapeamento de labels antigas", ""])
    for item in mapping[:20]:
        lines.append(
            f"- `{item['source_label_name']}` -> `{item['suggested_target_label']}` "
            f"({item['usage_in_sample']} ocorrencias na amostra)"
        )

    lines.extend(["", "## Acoes de migracao", ""])
    for rule in plan.get("migration_rules", []):
        lines.append(f"- {rule}")

    lines.extend(["", "## Amostra de acoes por mensagem", ""])
    for item in sampled_actions[:25]:
        remove_labels = ", ".join(item.get("remove_labels", [])) or "nenhuma"
        lines.append(
            f"- `{item['subject'] or 'Sem assunto'}` -> aplicar `{item['target_label']}` e remover `{remove_labels}`"
        )

    return "\n".join(lines) + "\n"


def _render_reclassify_result(result: dict) -> str:
    summary = result.get("summary", {})
    changed = result.get("changed", [])
    skipped = result.get("skipped", [])

    lines = [
        "# Reclassificacao Executada",
        "",
        f"- Mensagens solicitadas: {summary.get('messages_requested', 0)}",
        f"- Mensagens examinadas: {summary.get('messages_examined', 0)}",
        f"- Mensagens alteradas: {summary.get('messages_changed', 0)}",
        f"- Mensagens ignoradas: {summary.get('messages_skipped', 0)}",
        "",
        "## Amostra de mensagens alteradas",
        "",
    ]

    if changed:
        for item in changed[:30]:
            removed = ", ".join(item.get("removed_label_names", [])) or "nenhuma"
            archived = " e arquivada da caixa de entrada" if item.get("archived_from_inbox") else ""
            lines.append(
                f"- `{item['subject'] or 'Sem assunto'}` -> aplicada `{item['applied_target_label']}`{archived}; removidas `{removed}`"
            )
    else:
        lines.append("- Nenhuma mensagem foi alterada.")

    lines.extend(["", "## Amostra de mensagens ignoradas", ""])
    if skipped:
        for item in skipped[:20]:
            lines.append(f"- `{item['subject'] or 'Sem assunto'}` -> {item['reason']}")
    else:
        lines.append("- Nenhuma mensagem foi ignorada.")

    return "\n".join(lines) + "\n"


def _render_cleanup_dry_run(plan: dict) -> str:
    summary = plan.get("summary", {})
    ready = plan.get("ready_to_delete", [])
    review = plan.get("review_before_delete", [])

    lines = [
        "# Dry Run de Limpeza de Labels",
        "",
        f"- Labels prontas para exclusao: {summary.get('ready_to_delete_count', 0)}",
        f"- Labels para revisar antes da exclusao: {summary.get('review_before_delete_count', 0)}",
        f"- Labels mantidas: {summary.get('keep_count', 0)}",
        "",
        "## Labels prontas para exclusao",
        "",
    ]

    if ready:
        for item in ready[:50]:
            lines.append(
                f"- `{item['name']}` ({item['messagesTotal']} mensagens, {item['threadsTotal']} threads)"
            )
    else:
        lines.append("- Nenhuma label pronta para exclusao segura neste momento.")

    lines.extend(["", "## Labels que ainda precisam de revisao", ""])
    if review:
        for item in review[:50]:
            lines.append(
                f"- `{item['name']}` ({item['messagesTotal']} mensagens, {item['threadsTotal']} threads)"
            )
    else:
        lines.append("- Nenhuma label pendente de revisao.")

    lines.extend(["", "## Regras desta fase", ""])
    for rule in plan.get("rules", []):
        lines.append(f"- {rule}")

    return "\n".join(lines) + "\n"


def _render_cleanup_labels_result(result: dict) -> str:
    summary = result.get("summary", {})
    deleted = result.get("deleted", [])
    failed = result.get("failed", [])

    lines = [
        "# Limpeza de Labels Executada",
        "",
        f"- Labels solicitadas para exclusao: {summary.get('requested', 0)}",
        f"- Labels excluidas: {summary.get('deleted', 0)}",
        f"- Falhas: {summary.get('failed', 0)}",
        "",
        "## Labels excluidas",
        "",
    ]

    if deleted:
        for item in deleted:
            lines.append(f"- `{item['name']}`")
    else:
        lines.append("- Nenhuma label foi excluida.")

    lines.extend(["", "## Falhas", ""])
    if failed:
        for item in failed:
            lines.append(f"- `{item['name']}` -> {item['error']}")
    else:
        lines.append("- Nenhuma falha.")

    return "\n".join(lines) + "\n"


def _render_reclassify_label_result(result: dict) -> str:
    summary = result.get("summary", {})
    source_label = result.get("source_label", "")
    changed = result.get("changed", [])
    skipped = result.get("skipped", [])

    lines = [
        "# Reclassificacao por Label",
        "",
        f"- Label de origem: `{source_label}`",
        f"- Mensagens solicitadas: {summary.get('messages_requested', 0)}",
        f"- Mensagens examinadas: {summary.get('messages_examined', 0)}",
        f"- Mensagens alteradas: {summary.get('messages_changed', 0)}",
        f"- Mensagens ignoradas: {summary.get('messages_skipped', 0)}",
        "",
        "## Amostra de mensagens alteradas",
        "",
    ]

    if changed:
        for item in changed[:30]:
            removed = ", ".join(item.get("removed_label_names", [])) or "nenhuma"
            archived = " e arquivada da caixa de entrada" if item.get("archived_from_inbox") else ""
            lines.append(
                f"- `{item['subject'] or 'Sem assunto'}` -> aplicada `{item['applied_target_label']}`{archived}; removidas `{removed}`"
            )
    else:
        lines.append("- Nenhuma mensagem foi alterada.")

    lines.extend(["", "## Amostra de mensagens ignoradas", ""])
    if skipped:
        for item in skipped[:20]:
            lines.append(f"- `{item['subject'] or 'Sem assunto'}` -> {item['reason']}")
    else:
        lines.append("- Nenhuma mensagem foi ignorada.")

    return "\n".join(lines) + "\n"


def _render_maintain_recent_result(payload: dict, recent_days: int, learning_days: int) -> str:
    summary = payload.get("summary", {})
    stale_summary = payload.get("stale_cleanup_summary", {})
    learning_summary = payload.get("learning_summary", {})
    changed = payload.get("changed", [])
    skipped = payload.get("skipped", [])
    stale_archived = payload.get("stale_archived", [])

    lines = [
        "# Manutencao de Emails Recentes",
        "",
        f"- Janela de manutencao: ultimos {recent_days} dia(s)",
        f"- Janela de aprendizado: ultimos {learning_days} dia(s)",
        f"- Mensagens examinadas: {summary.get('messages_examined', 0)}",
        f"- Mensagens alteradas: {summary.get('messages_changed', 0)}",
        f"- Mensagens ignoradas: {summary.get('messages_skipped', 0)}",
        f"- Mensagens lidas com 2+ dias arquivadas da inbox: {stale_summary.get('messages_archived', 0)}",
        "",
        "## Aprendizado aplicado",
        "",
        f"- Mensagens recentes consideradas para aprender: {learning_summary.get('messages_considered', 0)}",
        f"- Mensagens com label AGENTE aproveitadas como decisao manual: {learning_summary.get('messages_with_manual_agent_label', 0)}",
        f"- Regras por remetente aprendidas: {learning_summary.get('sender_rules', 0)}",
        f"- Regras por dominio aprendidas: {learning_summary.get('domain_rules', 0)}",
        "",
        "## Amostra de mensagens alteradas",
        "",
    ]

    if changed:
        for item in changed[:25]:
            removed = ", ".join(item.get("removed_label_names", [])) or "nenhuma"
            archived = " e arquivada da caixa de entrada" if item.get("archived_from_inbox") else ""
            lines.append(
                f"- `{item['subject'] or 'Sem assunto'}` -> aplicada `{item['applied_target_label']}`{archived}; removidas `{removed}`"
            )
    else:
        lines.append("- Nenhuma mensagem recente precisou de alteracao.")

    lines.extend(["", "## Amostra de mensagens ignoradas", ""])
    if skipped:
        for item in skipped[:15]:
            lines.append(f"- `{item['subject'] or 'Sem assunto'}` -> {item['reason']}")
    else:
        lines.append("- Nenhuma mensagem foi ignorada.")

    lines.extend(["", "## Amostra de arquivamento tardio da inbox", ""])
    if stale_archived:
        for item in stale_archived[:20]:
            labels = ", ".join(item.get("kept_labels", [])) or "nenhuma"
            lines.append(
                f"- `{item['subject'] or 'Sem assunto'}` -> arquivada da inbox; mantidas `{labels}`"
            )
    else:
        lines.append("- Nenhuma mensagem lida com 2+ dias precisou sair da inbox nesta execucao.")

    return "\n".join(lines) + "\n"


def run_generate_filters() -> str:
    from .filters import build_filters_xml
    from .reporting import ensure_reports_dir, utc_stamp
    
    config = load_config()
    ensure_reports_dir(config.reports_dir)
    stamp = utc_stamp()
    xml_path = config.reports_dir / f"filters-{stamp}.xml"
    
    xml_content = build_filters_xml(config)
    xml_path.write_text(xml_content, encoding="utf-8")
    
    return f"Filtros gerados com sucesso e prontos para importacao no Gmail!\n- {xml_path}"
