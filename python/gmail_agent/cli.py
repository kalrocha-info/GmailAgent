from __future__ import annotations

import argparse

from .commands import (
    run_analyze,
    run_autopilot_command,
    run_autopilot_plan,
    run_autopilot_report,
    run_cleanup_dry_run,
    run_cleanup_labels,
    run_maintain_recent,
    run_reclassify,
    run_reclassify_label,
    run_reclassify_dry_run,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gmail-agent",
        description="Ferramenta Python para analisar Gmail, labels, filtros e contatos.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="Inventaria Gmail e contatos sem alterar nada.")
    analyze.add_argument(
        "--max-messages",
        type=int,
        default=300,
        help="Quantidade maxima de mensagens na amostra inicial.",
    )

    autopilot_plan = subparsers.add_parser("autopilot-plan", help="Gera um plano automatico consolidado de migracao.")
    autopilot_run = subparsers.add_parser("autopilot-run", help="Executa ciclos automaticos de reclassificacao dirigida.")
    autopilot_run.add_argument(
        "--cycles",
        type=int,
        default=3,
        help="Quantidade de ciclos automaticos a executar.",
    )
    autopilot_run.add_argument(
        "--batch-per-label",
        type=int,
        default=300,
        help="Quantidade maxima de mensagens processadas por label em cada ciclo.",
    )
    subparsers.add_parser("autopilot-report", help="Gera um relatorio consolidado do estado atual para confirmacao.")

    reclassify_dry_run = subparsers.add_parser("reclassify-dry-run", help="Prepara a futura reclassificacao sem alterar mensagens.")
    reclassify_dry_run.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Quantidade maxima de mensagens consideradas no dry-run.",
    )

    reclassify = subparsers.add_parser("reclassify", help="Executa a reclassificacao real em lote limitado.")
    reclassify.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Quantidade maxima de mensagens a reclassificar nesta execucao.",
    )

    reclassify_label = subparsers.add_parser("reclassify-label", help="Executa a reclassificacao real focada em uma label legada.")
    reclassify_label.add_argument(
        "--label",
        required=True,
        help="Nome exato da label de origem a ser esvaziada.",
    )
    reclassify_label.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Quantidade maxima de mensagens dessa label a reclassificar nesta execucao.",
    )

    cleanup_labels = subparsers.add_parser("cleanup-labels", help="Exclui apenas labels legadas vazias e seguras.")
    cleanup_labels.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Quantidade maxima de labels vazias para excluir nesta execucao.",
    )

    subparsers.add_parser("cleanup-dry-run", help="Prepara a futura limpeza sem apagar labels/filtros.")

    maintain_recent = subparsers.add_parser("maintain-recent", help="Classifica emails recentes e aprende com labels AGENTE aplicadas manualmente.")
    maintain_recent.add_argument(
        "--limit",
        type=int,
        default=300,
        help="Quantidade maxima de mensagens recentes a revisar por execucao.",
    )
    maintain_recent.add_argument(
        "--recent-days",
        type=int,
        default=7,
        help="Janela de dias usada para reclassificar emails recentes.",
    )
    maintain_recent.add_argument(
        "--learning-days",
        type=int,
        default=14,
        help="Janela de dias usada para aprender com suas decisoes manuais.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "analyze":
        json_path, md_path = run_analyze(max_messages=args.max_messages)
        print(f"Relatorios gerados:\n- {json_path}\n- {md_path}")
        return 0

    if args.command == "autopilot-plan":
        print(run_autopilot_plan())
        return 0

    if args.command == "autopilot-run":
        print(run_autopilot_command(cycles=args.cycles, batch_per_label=args.batch_per_label))
        return 0

    if args.command == "autopilot-report":
        print(run_autopilot_report())
        return 0

    if args.command == "reclassify-dry-run":
        print(run_reclassify_dry_run(limit=args.limit))
        return 0

    if args.command == "reclassify":
        print(run_reclassify(limit=args.limit))
        return 0

    if args.command == "reclassify-label":
        print(run_reclassify_label(label_name=args.label, limit=args.limit))
        return 0

    if args.command == "cleanup-labels":
        print(run_cleanup_labels(limit=args.limit))
        return 0

    if args.command == "cleanup-dry-run":
        print(run_cleanup_dry_run())
        return 0

    if args.command == "maintain-recent":
        print(
            run_maintain_recent(
                limit=args.limit,
                recent_days=args.recent_days,
                learning_days=args.learning_days,
            )
        )
        return 0

    parser.error("Comando invalido.")
    return 2
