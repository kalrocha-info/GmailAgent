from __future__ import annotations

import argparse

from .commands import run_analyze, run_cleanup_dry_run, run_reclassify_dry_run


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

    subparsers.add_parser("reclassify-dry-run", help="Prepara a futura reclassificacao sem alterar mensagens.")
    subparsers.add_parser("cleanup-dry-run", help="Prepara a futura limpeza sem apagar labels/filtros.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "analyze":
        json_path, md_path = run_analyze(max_messages=args.max_messages)
        print(f"Relatorios gerados:\n- {json_path}\n- {md_path}")
        return 0

    if args.command == "reclassify-dry-run":
        print(run_reclassify_dry_run())
        return 0

    if args.command == "cleanup-dry-run":
        print(run_cleanup_dry_run())
        return 0

    parser.error("Comando invalido.")
    return 2
