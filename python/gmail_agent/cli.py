from __future__ import annotations

import argparse
import logging
import sys

from .commands import (
    run_analyze,
    run_autopilot_command,
    run_autopilot_plan,
    run_autopilot_report,
    run_cleanup_dry_run,
    run_cleanup_labels,
    run_health_check,
    run_maintain_recent,
    run_reclassify,
    run_reclassify_label,
    run_reclassify_dry_run,
)


def _setup_logging(verbose: bool = False) -> None:
    """
    Configura logging estruturado para stdout.
    Usa StreamHandler explícito com flush automático para garantir que o
    PowerShell Start-Process -RedirectStandardOutput captura tudo corretamente.
    """
    # Reconfigurar stdout para UTF-8 sem buffering (crítico para o redirect do PS1)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        except Exception:
            pass

    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    # StreamHandler explícito apontado para sys.stdout com flush a cada linha
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Reduzir ruído das bibliotecas Google
    logging.getLogger("googleapiclient.discovery").setLevel(logging.WARNING)
    logging.getLogger("google.auth").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gmail-agent",
        description="Ferramenta Python para analisar Gmail, labels, filtros e contatos.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Ativa logging detalhado (DEBUG).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # health-check — diagnóstico rápido do token
    subparsers.add_parser(
        "health-check",
        help="Verifica se o token OAuth está válido e a conexão à API Gmail funciona.",
    )

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

    _setup_logging(verbose=getattr(args, "verbose", False))
    logger = logging.getLogger(__name__)
    logger.info("gmail-agent iniciado. Comando: %s", args.command)
    sys.stdout.flush()

    try:
        if args.command == "health-check":
            result = run_health_check()
            print(result, flush=True)
            return 0

        if args.command == "analyze":
            json_path, md_path = run_analyze(max_messages=args.max_messages)
            print(f"Relatorios gerados:\n- {json_path}\n- {md_path}", flush=True)
            return 0

        if args.command == "autopilot-plan":
            print(run_autopilot_plan(), flush=True)
            return 0

        if args.command == "autopilot-run":
            print(run_autopilot_command(cycles=args.cycles, batch_per_label=args.batch_per_label), flush=True)
            return 0

        if args.command == "autopilot-report":
            print(run_autopilot_report(), flush=True)
            return 0

        if args.command == "reclassify-dry-run":
            print(run_reclassify_dry_run(limit=args.limit), flush=True)
            return 0

        if args.command == "reclassify":
            print(run_reclassify(limit=args.limit), flush=True)
            return 0

        if args.command == "reclassify-label":
            print(run_reclassify_label(label_name=args.label, limit=args.limit), flush=True)
            return 0

        if args.command == "cleanup-labels":
            print(run_cleanup_labels(limit=args.limit), flush=True)
            return 0

        if args.command == "cleanup-dry-run":
            print(run_cleanup_dry_run(), flush=True)
            return 0

        if args.command == "maintain-recent":
            print(
                run_maintain_recent(
                    limit=args.limit,
                    recent_days=args.recent_days,
                    learning_days=args.learning_days,
                ),
                flush=True,
            )
            return 0

        parser.error("Comando invalido.")
        return 2

    except RuntimeError as exc:
        # Erros de autenticação (ex: token expirado) — mensagem clara sem stack trace completo
        logger.error("Erro crítico: %s", exc)
        print(f"\nERRO: {exc}", file=sys.stderr, flush=True)
        return 1
    except KeyboardInterrupt:
        logger.info("Execução interrompida pelo utilizador.")
        return 130
    except Exception as exc:
        logger.exception("Erro inesperado: %s", exc)
        sys.stdout.flush()
        return 1
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
