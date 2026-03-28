from __future__ import annotations

from pathlib import Path

from .config import load_config
from .google_clients import build_gmail_service, build_people_service
from .inventory import analyze_workspace
from .reporting import ensure_reports_dir, utc_stamp, write_json, write_markdown


def run_analyze(max_messages: int) -> tuple[Path, Path]:
    config = load_config()
    ensure_reports_dir(config.reports_dir)
    gmail_service = build_gmail_service(config)
    people_service = build_people_service(config)

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


def run_reclassify_dry_run() -> str:
    return (
        "Modo dry-run de reclassificacao ainda nao implementado. "
        "A base de analise e relatorios ja esta pronta para a proxima etapa."
    )


def run_cleanup_dry_run() -> str:
    return (
        "Modo dry-run de limpeza ainda nao implementado. "
        "Primeiro vamos validar o inventario e a nova estrutura de labels/filtros."
    )


def _render_markdown_summary(report: dict, max_messages: int) -> str:
    summary = report["summary"]
    recommendations = report.get("recommendations", [])
    top_labels = list(report.get("label_usage", {}).items())[:10]

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
        for label_id, count in top_labels:
            lines.append(f"- `{label_id}`: {count} mensagens")
    else:
        lines.append("- Nenhuma label encontrada na amostra.")

    lines.extend(["", "## Recomendacoes iniciais", ""])
    for recommendation in recommendations:
        lines.append(f"- {recommendation}")

    return "\n".join(lines) + "\n"
