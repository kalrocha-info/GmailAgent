from __future__ import annotations

import logging
import re
import time
from collections import Counter
from email.utils import parseaddr
from typing import Any

from googleapiclient.errors import HttpError


TARGET_LABELS = [
    "01_PROFI/TRABALHO",
    "01_PROFI/PROJETOS-PJ",
    "01_PROFI/VAGAS",
    "01_PROFI/CANDIDATURAS",
    "02_FINANCEIRO/CONTAS",
    "02_FINANCEIRO/EM_ATRASO",
    "03_URGENTE",
    "04_NOTIFICACOES",
    "05_COMPRAS",
    "06_NEWSLETTER",
    "07_PUBLICIDADE-PROMOCOES",
]

ARCHIVE_TARGET_LABELS = {
    "01_PROFI/VAGAS",
    "02_FINANCEIRO/EM_ATRASO",
    "04_NOTIFICACOES",
    "05_COMPRAS",
    "06_NEWSLETTER",
    "07_PUBLICIDADE-PROMOCOES",
}

EXPLICIT_LABEL_MAPPING = {
    "01_PROFISSIONAL/TRABALHO": "01_PROFI/TRABALHO",
    "01_PROFISSIONAL/PROJETOS-PJ": "01_PROFI/PROJETOS-PJ",
    "01_PROFISSIONAL/VAGAS": "01_PROFI/VAGAS",
    "01_PROFISSIONAL/CANDIDATURAS": "01_PROFI/CANDIDATURAS",
    "0_URGENTE": "03_URGENTE",
    "[Gmail]/SEGURANÇA": "03_URGENTE",
    "[Gmail]/00_INCUMPRIMENTO-PT": "03_URGENTE",
    "1_FINANCEIRO": "02_FINANCEIRO/CONTAS",
    "PT/1_FINANCEIRO": "02_FINANCEIRO/CONTAS",
    "[Gmail]/00_FINANCEIRO": "02_FINANCEIRO/CONTAS",
    "[Gmail]/COMPRAS": "05_COMPRAS",
    "[Gmail]/01_COMPRAS": "05_COMPRAS",
    "[Gmail]/00_GESTAO": "02_FINANCEIRO/CONTAS",
    "[Gmail]/02_SAUDE": "02_FINANCEIRO/CONTAS",
    "2_ESTUDOS": "01_PROFI/CANDIDATURAS",
    "PT/2_ESTUDOS": "01_PROFI/CANDIDATURAS",
    "[Gmail]/01_ESTUDOS": "01_PROFI/CANDIDATURAS",
    "[Gmail]/00_TRABALHO": "01_PROFI/TRABALHO",
    "[Gmail]/02_TRABALHO E CARREIRA": "01_PROFI/VAGAS",
    "[Gmail]/Candidaturas": "01_PROFI/CANDIDATURAS",
    "[Gmail]/ENTREVISTAS": "01_PROFI/CANDIDATURAS",
    "[Gmail]/PROFISSIONAL": "01_PROFI/PROJETOS-PJ",
    "3_VAGAS_PROMOCOES": "01_PROFI/VAGAS",
    "[Gmail]/06_NEWSLETTERS": "06_NEWSLETTER",
    "[Gmail]/PROMOÇÕES": "07_PUBLICIDADE-PROMOCOES",
    "4_REDES_SOCIAIS": "04_NOTIFICACOES",
    "FLUXO/LinkedIn": "01_PROFI/VAGAS",
    "IA/Outros": "04_NOTIFICACOES",
    "AGENTE/URGENTE": "03_URGENTE",
    "AGENTE/TRABALHO": "01_PROFI/TRABALHO",
    "AGENTE/TRABALHO/VAGAS": "01_PROFI/VAGAS",
    "AGENTE/TRABALHO/CANDIDATURAS": "01_PROFI/CANDIDATURAS",
    "AGENTE/TRABALHO/PROJETOS": "01_PROFI/PROJETOS-PJ",
    "AGENTE/TRABALHO/CLIENTES-PJ": "01_PROFI/PROJETOS-PJ",
    "AGENTE/FINANCEIRO": "02_FINANCEIRO/CONTAS",
    "AGENTE/FINANCEIRO/CONTAS": "02_FINANCEIRO/CONTAS",
    "AGENTE/FINANCEIRO/EM_ATRASO": "02_FINANCEIRO/EM_ATRASO",
    "AGENTE/CONTAS": "02_FINANCEIRO/CONTAS",
    "AGENTE/COMPRAS": "05_COMPRAS",
    "AGENTE/PESSOAL": "04_NOTIFICACOES",
    "AGENTE/PROMOCOES": "07_PUBLICIDADE-PROMOCOES",
    "AGENTE/NOTIFICACOES": "04_NOTIFICACOES",
    "AGENTE/REVISAR": "04_NOTIFICACOES",
    "AGENTES/NEWSLETTER": "06_NEWSLETTER",
}

EXPLICIT_SENDER_MAPPING = {
    "groups-noreply@linkedin.com": "04_NOTIFICACOES",
    "jobs-noreply@linkedin.com": "01_PROFI/VAGAS",
    "jobalerts-noreply@linkedin.com": "01_PROFI/VAGAS",
    # "newsletters-noreply@linkedin.com" é tratado por linkedin_newsletter_target()
    "indeed.com": "01_PROFI/VAGAS",
    "infojobs.com.br": "01_PROFI/VAGAS",
    "jobrapidoalert.com": "01_PROFI/VAGAS",
    "greenhouse.io": "01_PROFI/CANDIDATURAS",
    "glassdoor.com": "01_PROFI/VAGAS",
    "wellhub.com": "01_PROFI/CANDIDATURAS",
    "upwork.com": "01_PROFI/PROJETOS-PJ",
    "99freelas.com.br": "01_PROFI/PROJETOS-PJ",
    "alignerr.com": "01_PROFI/PROJETOS-PJ",
    "sme": "01_PROFI/CANDIDATURAS",
    "vivo.com.br": "02_FINANCEIRO/CONTAS",
    "nubank.com.br": "02_FINANCEIRO/CONTAS",
    "caixa.gov.br": "02_FINANCEIRO/CONTAS",
    "caixa.gov": "02_FINANCEIRO/CONTAS",
    "bb.com.br": "02_FINANCEIRO/CONTAS",
    "itau.com.br": "02_FINANCEIRO/CONTAS",
    "bradesco.com.br": "02_FINANCEIRO/CONTAS",
    "santander.com.br": "02_FINANCEIRO/CONTAS",
    "bancointer.com.br": "02_FINANCEIRO/CONTAS",
    "shopee.com": "05_COMPRAS",
    "picpay.com": "02_FINANCEIRO/CONTAS",
    "mercadopago.com": "02_FINANCEIRO/CONTAS",
    "amazon.com": "05_COMPRAS",
    "amazon.es": "05_COMPRAS",
    "amazon.com.br": "05_COMPRAS",
    "wise.com": "02_FINANCEIRO/CONTAS",
    "oney.pt": "02_FINANCEIRO/EM_ATRASO",
    "acordocerto.com.br": "02_FINANCEIRO/EM_ATRASO",
    "scpc.com.br": "02_FINANCEIRO/EM_ATRASO",
    "serasa.com.br": "02_FINANCEIRO/EM_ATRASO",
    "spcbrasil.org.br": "02_FINANCEIRO/EM_ATRASO",
    "boavistaservicos.com.br": "02_FINANCEIRO/EM_ATRASO",
    "gov.br": "03_URGENTE",
    "google.com": "04_NOTIFICACOES",
}

URGENT_TERMS = [
    "urgente", "urgent", "alerta de segurança", "alerta de seguranca",
    "security code", "verification code", "your code", "otp",
    "access blocked", "acesso bloqueado", "novo dispositivo", "dispositivo autorizado",
    "incumprimento", "payment failed", "failed payment",
    "novo cadastro de dispositivo", "lembrar dos meus dados", "sign-in",
    "login", "security alert", "verification",
    "palavra-passe", "password reset", "reset password", "redefinição da palavra-passe",
    "verify your device", "verify your location", "unknown device", "browser has been used",
    "código de verificação", "codigo de verificacao", "please verify your device",
    "a senha", "senha foi alterada", "password was changed", "password changed",
]

WORK_TERMS = [
    "vaga", "vagas", "job", "jobs", "candidatura", "candidaturas", "application",
    "contratando", "career", "carreira", "entrevista", "interview", "greenhouse",
    "wellhub", "indeed", "infojobs", "jobrapido", "talent",
    "freelance", "projeto", "proposal", "proposal update",
    "opportunity", "opportunities", "hiring", "opening", "openings",
    "recruitment", "recruiting", "position", "positions", "role", "roles",
    "work from home", "remote", "join our team",
]

PROMO_TERMS = [
    "newsletter", "newsletters", "promo", "promoções", "promocoes", "oferta",
    "ofertas", "cupom", "desconto", "sale", "deals", "black friday", "marketing",
    "power automate", "inscrições abertas", "inscricoes abertas", "acesso vitalício",
    "acesso vitalicio", "bônus", "bonus", "imersão", "imersao",
    "python rpa", "dev studio", "hotmart", "udemy", "academy", "data science",
    "datascience", "excel", "doctor", "doctors", "curso", "formação", "formacao",
    "ganhe", "convide", "convidando seus amigos", "cartão", "cartao", "cashback",
    "pré-aprovado", "pre-aprovado", "limite disponível", "limite disponivel",
]

COMMERCIAL_PROMO_TERMS = [
    "promo", "promoção", "promocao", "promoções", "promocoes", "oferta", "ofertas",
    "cupom", "desconto", "sale", "deals", "black friday", "marketing", "cashback",
    "aproveite", "aproveitar", "imperdível", "imperdivel", "exclusivo", "exclusiva",
    "vantagem", "vantagens", "benefício", "beneficio", "benefícios", "beneficios",
    "pré-aprovado", "pre-aprovado", "limite disponível", "limite disponivel",
    "limite especial", "cartão sem anuidade", "cartao sem anuidade", "melhores condições",
    "melhores condicoes", "condições especiais", "condicoes especiais", "parcelamento especial",
    "ganhe", "economize", "preço especial", "preco especial", "últimas vagas", "ultimas vagas",
    "inscrições abertas", "inscricoes abertas", "acesso vitalício", "acesso vitalicio",
    "bônus", "bonus", "hotmart", "udemy", "curso", "cursos", "formação", "formacao",
    "imersão", "imersao", "matricule-se", "compre agora", "assine agora",
]

NOTIFICATION_TERMS = [
    "social", "redes sociais", "forum", "notification", "notificação", "notificacao",
    "groups-noreply", "reddit", "community", "grupo",
    "limite mensal", "usage limit", "usage tier", "companion", "limite", "tier update",
    "billing caps", "plan update", "quota",
    "what's new", "whats new", "vs code", "github copilot", "developer newsletter",
    "newsletter", "parallel agents", "multi-step planning", "skills",
    "publicações receberam", "publicacoes receberam", "impressões", "impressoes",
    "viu seu perfil", "começou a seguir você", "comecou a seguir voce",
    "pedido está a caminho", "pedido esta a caminho", "tracking", "shipment",
    "entrega", "out for delivery", "a caminho",
    "dev news", "openai dev news", "plugins in codex",
]

PERSONAL_TERMS = [
    "agenda", "pessoal", "família", "familia", "mensagem", "wishlist", "lista de desejos",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BUG-5 corrigido: estado de aprendizado como objeto explícito, não variável global
# ---------------------------------------------------------------------------

class LearningState:
    """Encapsula os mapeamentos aprendidos de forma explícita, sem globals mutáveis."""

    def __init__(self) -> None:
        self.sender_mapping: dict[str, str] = {}
        self.domain_mapping: dict[str, str] = {}

    def load(self, state: dict[str, Any] | None) -> None:
        sender_rules = (state or {}).get("sender_rules", {})
        domain_rules = (state or {}).get("domain_rules", {})
        self.sender_mapping = {
            key.lower(): label_to_target(value["target_label"]) or value["target_label"]
            for key, value in sender_rules.items()
            if value.get("target_label")
        }
        self.domain_mapping = {
            key.lower(): label_to_target(value["target_label"]) or value["target_label"]
            for key, value in domain_rules.items()
            if value.get("target_label")
        }

    def clear(self) -> None:
        self.sender_mapping = {}
        self.domain_mapping = {}


# Instância global — mas agora é uma classe com estado bem definido
_learning_state = LearningState()

# Manter compatibilidade com código existente que usa os dicts diretamente
LEARNED_SENDER_MAPPING: dict[str, str] = _learning_state.sender_mapping
LEARNED_DOMAIN_MAPPING: dict[str, str] = _learning_state.domain_mapping


def apply_learning_state(state: dict[str, Any] | None) -> None:
    """Carrega estado de aprendizado usando LearningState — sem globals soltos."""
    _learning_state.load(state)
    # Atualiza referências para compatibilidade
    global LEARNED_SENDER_MAPPING, LEARNED_DOMAIN_MAPPING
    LEARNED_SENDER_MAPPING = _learning_state.sender_mapping
    LEARNED_DOMAIN_MAPPING = _learning_state.domain_mapping


def build_reclassification_plan(report: dict[str, Any]) -> dict[str, Any]:
    labels = report.get("labels", [])
    messages = report.get("messages", [])
    label_lookup = {label["id"]: label["name"] for label in labels}
    filter_rules = build_filter_rules(report)
    legacy_candidates = report.get("label_analysis", {}).get("legacy_candidates", [])

    legacy_mapping = []
    migration_counter: Counter = Counter()
    sampled_actions = []

    for item in legacy_candidates:
        target = suggest_target_label(item["name"])
        legacy_mapping.append(
            {
                "source_label_id": item["id"],
                "source_label_name": item["name"],
                "usage_in_sample": item["usage_in_sample"],
                "suggested_target_label": target,
            }
        )

    for message in messages:
        plan = plan_message_reclassification(message, label_lookup, filter_rules=filter_rules)
        if plan["target_label"]:
            migration_counter[plan["target_label"]] += 1
        if plan["remove_labels"] or plan["target_label"]:
            sampled_actions.append(plan)

    return {
        "target_labels": TARGET_LABELS,
        "legacy_mapping": legacy_mapping,
        "summary": {
            "messages_considered": len(messages),
            "messages_with_action": len(sampled_actions),
            "messages_by_target_label": dict(sorted(migration_counter.items(), key=lambda item: (-item[1], item[0]))),
        },
        "sampled_actions": sampled_actions[:120],
        "migration_rules": [
            "Aplicar a nova label alvo antes de remover labels antigas do email.",
            "Preservar labels de sistema do Gmail como INBOX, UNREAD, IMPORTANT e categorias nativas.",
            "Remover labels antigas somente quando houver uma correspondencia clara para a nova taxonomia.",
            "Usar 04_NOTIFICACOES para mensagens sem mapeamento claro.",
        ],
    }


def execute_reclassification_plan(
    gmail_service,
    report: dict[str, Any],
    limit: int,
) -> dict[str, Any]:
    labels = report.get("labels", [])
    label_lookup = {label["id"]: label["name"] for label in labels}
    reverse_label_lookup = {label["name"]: label["id"] for label in labels}
    filter_rules = build_filter_rules(report)
    ensure_agent_labels(gmail_service, reverse_label_lookup)

    messages = report.get("messages", [])[:limit]
    changed = []
    skipped = []

    for message in messages:
        plan = plan_message_reclassification(message, label_lookup, filter_rules=filter_rules)
        target_label = plan["target_label"]
        if not target_label:
            skipped.append({
                "message_id": message.get("id"),
                "subject": message.get("subject"),
                "reason": "sem label alvo",
            })
            continue

        add_label_ids = []
        remove_label_ids = []
        existing_label_names = plan["existing_labels"]

        target_label_id = reverse_label_lookup.get(target_label)
        if not target_label_id:
            skipped.append({
                "message_id": message.get("id"),
                "subject": message.get("subject"),
                "reason": f"label alvo ausente: {target_label}",
            })
            continue

        if target_label not in existing_label_names:
            add_label_ids.append(target_label_id)

        for label_name in plan["remove_labels"]:
            label_id = reverse_label_lookup.get(label_name)
            if label_id:
                remove_label_ids.append(label_id)

        conflicting_agent_labels = [
            label_name
            for label_name in existing_label_names
            if is_classification_label(label_name)
            and label_name != target_label
            and label_name not in plan["remove_labels"]
        ]
        for label_name in conflicting_agent_labels:
            label_id = reverse_label_lookup.get(label_name)
            if label_id and label_id not in remove_label_ids:
                remove_label_ids.append(label_id)

        if target_label in ARCHIVE_TARGET_LABELS:
            inbox_label_id = reverse_label_lookup.get("INBOX")
            if inbox_label_id and inbox_label_id not in remove_label_ids and "INBOX" in existing_label_names:
                remove_label_ids.append(inbox_label_id)

        if not add_label_ids and not remove_label_ids:
            skipped.append({
                "message_id": message.get("id"),
                "subject": message.get("subject"),
                "reason": "nenhuma alteracao necessaria",
            })
            continue

        # BUG-7 corrigido: try/except por mensagem individual — falha numa mensagem não para o lote
        try:
            _api_modify_with_retry(
                gmail_service,
                message["id"],
                add_label_ids,
                remove_label_ids,
            )
        except Exception as exc:
            logger.warning(
                "Falha ao modificar mensagem %s ('%s'): %s — ignorando e continuando.",
                message.get("id"), message.get("subject"), exc,
            )
            skipped.append({
                "message_id": message.get("id"),
                "subject": message.get("subject"),
                "reason": f"erro API: {exc}",
            })
            continue

        changed.append({
            "message_id": message.get("id"),
            "thread_id": message.get("threadId"),
            "subject": message.get("subject"),
            "from": message.get("from"),
            "applied_target_label": target_label,
            "added_label_ids": add_label_ids,
            "removed_label_ids": remove_label_ids,
            "removed_label_names": plan["remove_labels"] + conflicting_agent_labels,
            "archived_from_inbox": target_label in ARCHIVE_TARGET_LABELS and "INBOX" in existing_label_names,
        })

    logger.info(
        "Reclassificação: %d alteradas, %d ignoradas de %d mensagens.",
        len(changed), len(skipped), len(messages),
    )

    return {
        "summary": {
            "messages_requested": limit,
            "messages_examined": len(messages),
            "messages_changed": len(changed),
            "messages_skipped": len(skipped),
            "filter_rules_considered": len(filter_rules),
        },
        "changed": changed,
        "skipped": skipped,
    }


def archive_stale_inbox_messages(
    gmail_service,
    report: dict[str, Any],
    limit: int,
) -> dict[str, Any]:
    labels = report.get("labels", [])
    label_lookup = {label["id"]: label["name"] for label in labels}
    reverse_label_lookup = {label["name"]: label["id"] for label in labels}
    inbox_label_id = reverse_label_lookup.get("INBOX")
    unread_label_name = "UNREAD"

    archived = []
    skipped = []

    for message in report.get("messages", [])[:limit]:
        resolved_labels = [label_lookup.get(label_id, label_id) for label_id in message.get("labelIds", [])]
        if "INBOX" not in resolved_labels:
            skipped.append({
                "message_id": message.get("id"),
                "subject": message.get("subject"),
                "reason": "fora da caixa de entrada",
            })
            continue
        if unread_label_name in resolved_labels:
            skipped.append({
                "message_id": message.get("id"),
                "subject": message.get("subject"),
                "reason": "ainda nao lida",
            })
            continue

        kept_agent_labels = [label for label in resolved_labels if is_classification_label(label)]
        archive_labels = [label for label in kept_agent_labels if label in ARCHIVE_TARGET_LABELS]
        if not archive_labels:
            skipped.append({
                "message_id": message.get("id"),
                "subject": message.get("subject"),
                "reason": "categoria deve permanecer na caixa de entrada",
            })
            continue

        if not inbox_label_id:
            skipped.append({
                "message_id": message.get("id"),
                "subject": message.get("subject"),
                "reason": "label INBOX nao encontrada",
            })
            continue

        try:
            _api_modify_with_retry(gmail_service, message["id"], [], [inbox_label_id])
        except Exception as exc:
            logger.warning("Falha ao arquivar mensagem %s: %s", message.get("id"), exc)
            skipped.append({
                "message_id": message.get("id"),
                "subject": message.get("subject"),
                "reason": f"erro API: {exc}",
            })
            continue

        archived.append({
            "message_id": message.get("id"),
            "subject": message.get("subject"),
            "from": message.get("from"),
            "kept_labels": kept_agent_labels,
        })

    return {
        "summary": {
            "messages_requested": limit,
            "messages_archived": len(archived),
            "messages_skipped": len(skipped),
        },
        "archived": archived,
        "skipped": skipped,
    }


def plan_message_reclassification(
    message: dict[str, Any],
    label_lookup: dict[str, str],
    filter_rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_labels = [label_lookup.get(label_id, label_id) for label_id in message.get("labelIds", [])]
    target = infer_target_from_message(message, resolved_labels, filter_rules=filter_rules)

    remove_labels = [
        label
        for label in resolved_labels
        if label != target and (is_legacy_label(label) or is_classification_label(label))
    ]

    return {
        "message_id": message.get("id"),
        "thread_id": message.get("threadId"),
        "from": message.get("from"),
        "subject": message.get("subject"),
        "existing_labels": resolved_labels,
        "target_label": target,
        "remove_labels": remove_labels,
    }


def infer_target_from_message(
    message: dict[str, Any],
    resolved_labels: list[str],
    filter_rules: list[dict[str, Any]] | None = None,
) -> str | None:
    subject = (message.get("subject") or "").lower()
    sender = (message.get("from") or "").lower()
    labels_text = " ".join(resolved_labels).lower()
    body_text = (message.get("body_text") or "").lower()
    snippet_text = (message.get("snippet") or "").lower()
    content_without_labels = f"{subject} {snippet_text} {body_text} {sender}"
    content_text = f"{content_without_labels} {labels_text}"
    text = f"{subject} {sender} {labels_text}"

    if is_security_urgent(content_without_labels):
        return "03_URGENTE"

    explicit_target = first_explicit_label_target(resolved_labels)
    if explicit_target:
        return explicit_target

    # Sinais críticos do conteúdo prevalecem sobre regras aprendidas. Isso evita
    # que uma correção antiga de remetente esconda uma cobrança ou restrição real.
    if is_debt_or_credit_restriction(content_without_labels):
        return "02_FINANCEIRO/EM_ATRASO"

    sender_target = sender_based_target(sender, subject)
    if sender_target:
        return sender_target

    linkedin_target = linkedin_newsletter_target(sender, content_text)
    if linkedin_target:
        return linkedin_target

    filter_target = filter_based_target(message, filter_rules or [])
    if filter_target:
        return filter_target

    if contains_any(content_without_labels, URGENT_TERMS):
        return "03_URGENTE"

    if is_job_blast(content_without_labels):
        return "01_PROFI/VAGAS"

    work_target = infer_work_target(content_without_labels)
    if work_target:
        return work_target

    if is_commercial_promotion(content_without_labels):
        return "07_PUBLICIDADE-PROMOCOES"

    if is_course_promotion(content_without_labels):
        return "07_PUBLICIDADE-PROMOCOES"

    if is_technical_newsletter(content_without_labels):
        return "06_NEWSLETTER"

    if contains_any(content_without_labels, FINANCIAL_TERMS):
        return "02_FINANCEIRO/CONTAS"
    if contains_any(content_without_labels, PROMO_TERMS):
        return "07_PUBLICIDADE-PROMOCOES"
    if contains_any(content_without_labels, NOTIFICATION_TERMS):
        return "04_NOTIFICACOES"
    if contains_any(content_without_labels, PERSONAL_TERMS):
        return "04_NOTIFICACOES"

    agent_target = first_agent_label_target(resolved_labels, allow_review=True)
    if agent_target:
        return agent_target

    if any(is_legacy_label(label) for label in resolved_labels):
        return suggest_target_label(next(label for label in resolved_labels if is_legacy_label(label)))

    # Sem evidência suficiente, não alteramos a mensagem. O chamador registra a
    # decisão como "sem label alvo" para revisão, evitando falso aprendizado.
    return None


def suggest_target_label(label_name: str) -> str:
    if label_name in EXPLICIT_LABEL_MAPPING:
        return EXPLICIT_LABEL_MAPPING[label_name]

    name = label_name.lower()
    if contains_any(name, URGENT_TERMS):
        return "03_URGENTE"
    if is_debt_or_credit_restriction(name):
        return "02_FINANCEIRO/EM_ATRASO"
    work_target = infer_work_target(name)
    if work_target:
        return work_target
    if is_commercial_promotion(name):
        return "07_PUBLICIDADE-PROMOCOES"
    if contains_any(name, FINANCIAL_TERMS):
        return "02_FINANCEIRO/CONTAS"
    if contains_any(name, PROMO_TERMS):
        return "07_PUBLICIDADE-PROMOCOES"
    if contains_any(name, NOTIFICATION_TERMS):
        return "04_NOTIFICACOES"
    return "04_NOTIFICACOES"


def first_explicit_label_target(labels: list[str]) -> str | None:
    for label in labels:
        if label in EXPLICIT_LABEL_MAPPING:
            return EXPLICIT_LABEL_MAPPING[label]
    return None


def first_agent_label_target(labels: list[str], allow_review: bool) -> str | None:
    candidates = [
        label
        for label in labels
        if label in TARGET_LABELS
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda label: TARGET_LABELS.index(label))


def build_filter_rules(report: dict[str, Any]) -> list[dict[str, Any]]:
    labels = report.get("labels", [])
    label_lookup = {label["id"]: label["name"] for label in labels}
    rules = []

    for item in report.get("filters", []):
        action = item.get("action", {})
        target = _filter_action_target(action, label_lookup)
        if not target:
            continue
        criteria = item.get("criteria", {})
        if not criteria:
            continue
        rules.append({
            "id": item.get("id"),
            "criteria": criteria,
            "target_label": target,
            "specificity": _filter_specificity(criteria),
        })

    rules.sort(key=lambda rule: (-rule["specificity"], rule.get("id") or ""))
    return rules


def _filter_action_target(action: dict[str, Any], label_lookup: dict[str, str]) -> str | None:
    added_labels = [
        label_lookup.get(label_id, label_id)
        for label_id in action.get("addLabelIds", [])
    ]
    for label in added_labels:
        target = label_to_target(label)
        if target:
            return target
    return None


def label_to_target(label: str) -> str | None:
    if label in TARGET_LABELS:
        return label
    if label in EXPLICIT_LABEL_MAPPING:
        return EXPLICIT_LABEL_MAPPING[label]
    for target in TARGET_LABELS:
        if label.startswith(f"{target}/"):
            return target
    if label.startswith("AGENTE/") or label.startswith("AGENTES/"):
        return suggest_target_label(label)
    if is_legacy_label(label):
        return suggest_target_label(label)
    return None


def _filter_specificity(criteria: dict[str, Any]) -> int:
    return sum(1 for value in criteria.values() if value)


def filter_based_target(message: dict[str, Any], filter_rules: list[dict[str, Any]]) -> str | None:
    for rule in filter_rules:
        if _filter_matches_message(rule.get("criteria", {}), message):
            return rule["target_label"]
    return None


def _filter_matches_message(criteria: dict[str, Any], message: dict[str, Any]) -> bool:
    sender = message.get("from", "")
    recipient = message.get("to", "")
    subject = message.get("subject", "")
    snippet = message.get("snippet", "")
    text = f"{subject} {sender} {recipient} {snippet}"

    matched = False
    supported_keys = {"from", "to", "subject", "query", "hasTheWord", "negatedQuery", "doesNotHaveTheWord"}
    if any(key not in supported_keys for key in criteria):
        return False

    from_query = criteria.get("from")
    if from_query:
        if not _query_matches(sender, from_query):
            return False
        matched = True

    to_query = criteria.get("to")
    if to_query:
        if not _query_matches(recipient, to_query):
            return False
        matched = True

    subject_query = criteria.get("subject")
    if subject_query:
        if not _query_matches(subject, subject_query):
            return False
        matched = True

    has_query = criteria.get("query") or criteria.get("hasTheWord")
    if has_query:
        if not _query_matches(text, has_query):
            return False
        matched = True

    negated_query = criteria.get("negatedQuery") or criteria.get("doesNotHaveTheWord")
    if negated_query and _query_matches(text, negated_query):
        return False

    return matched


def _query_matches(text: str, query: str) -> bool:
    normalized_text = text.lower()
    clauses = _split_or_clauses(query)
    return any(_query_clause_matches(normalized_text, clause) for clause in clauses)


def _split_or_clauses(query: str) -> list[str]:
    clauses = re.split(r"\s+\bOR\b\s+", query, flags=re.IGNORECASE)
    return [clause.strip(" (){}") for clause in clauses if clause.strip(" (){}")]


def _query_clause_matches(normalized_text: str, clause: str) -> bool:
    tokens = re.findall(r'"([^"]+)"|(\S+)', clause)
    positives = []
    negatives = []
    for quoted, raw in tokens:
        token = (quoted or raw).strip("(){}").lower()
        if not token:
            continue
        if token.startswith("-"):
            negatives.append(token[1:])
        else:
            positives.append(token)

    if not positives and not negatives:
        return False

    if any(_query_token_matches(normalized_text, token) for token in negatives):
        return False
    return all(_query_token_matches(normalized_text, token) for token in positives)


def _query_token_matches(normalized_text: str, token: str) -> bool:
    if ":" in token:
        token = token.split(":", 1)[1]
    token = token.strip('"')
    if not token:
        return False
    if token == "*":
        return True
    if "*" in token:
        pattern = re.escape(token).replace(r"\*", ".*")
        return re.search(pattern, normalized_text) is not None
    return token in normalized_text


def is_legacy_label(name: str) -> bool:
    if name in TARGET_LABELS:
        return False
    if name.startswith("01_PROFISSIONAL/"):
        return True
    prefixes = ("[Gmail]/", "PT/", "FLUXO/", "IA/", "AGENTE/", "AGENTES/")
    numeric_roots = ("0_", "1_", "2_", "3_", "4_")
    return name.startswith(prefixes) or name.startswith(numeric_roots)


def is_classification_label(name: str) -> bool:
    return name in TARGET_LABELS or is_legacy_label(name)


def contains_any(text: str, terms: list[str]) -> bool:
    return any(re.search(rf'\b{re.escape(term)}\b', text) for term in terms)


def ensure_agent_labels(gmail_service, reverse_label_lookup: dict[str, str]) -> None:
    for label_name in TARGET_LABELS:
        if label_name in reverse_label_lookup:
            continue
        try:
            created = gmail_service.users().labels().create(
                userId="me",
                body={
                    "name": label_name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            ).execute()
            reverse_label_lookup[label_name] = created["id"]
            logger.info("Label criada: %s", label_name)
        except HttpError as exc:
            if exc.resp and exc.resp.status == 409:
                logger.warning("Label %s já existe (409); continue.", label_name)
            else:
                raise


def sender_based_target(sender: str, subject: str) -> str | None:
    sender_lower = sender.lower()
    subject_lower = subject.lower()
    sender_email = parseaddr(sender or "")[1].strip().lower()

    if sender_email and sender_email in LEARNED_SENDER_MAPPING:
        return LEARNED_SENDER_MAPPING[sender_email]

    if sender_email and "@" in sender_email:
        sender_domain = sender_email.split("@", 1)[1]
        if sender_domain in LEARNED_DOMAIN_MAPPING:
            return LEARNED_DOMAIN_MAPPING[sender_domain]

    for needle, target in EXPLICIT_SENDER_MAPPING.items():
        if needle in sender_lower:
            if target.startswith("01_PROFI") and contains_any(subject_lower, ["code", "security", "login", "verification", "otp", "sign-in"]):
                return "03_URGENTE"
            return target

    if "jobs" in subject_lower and "access" in subject_lower:
        return "01_PROFI/VAGAS"

    return None


def linkedin_newsletter_target(sender: str, text: str) -> str | None:
    sender_email = parseaddr(sender or "")[1].strip().lower()
    sender_lower = (sender or "").lower()
    if sender_email != "newsletters-noreply@linkedin.com" and "newsletters-noreply@linkedin.com" not in sender_lower:
        return None
    if is_job_blast(text) or infer_work_target(text) == "01_PROFI/VAGAS":
        return "01_PROFI/VAGAS"
    return "06_NEWSLETTER"


FINANCIAL_TERMS = [
    "financeiro", "fatura", "faturas", "pix", "boleto", "boletos",
    "compra", "compras", "mercadopago",
    "picpay", "amazon", "gestão", "gestao", "cartão", "cartão de crédito",
    "cartao", "cartao de credito", "oney", "bank", "banco",
    "débito automático", "debito automatico", "parcela", "parcelas",
    "recibo", "recibos", "wise",
    "transferência bancária", "transferencia bancaria",
    "transferência", "transferencia", "pagamento", "pagamentos",
    "pagável", "fechou", "fatura fechada",
]


DEBT_TERMS = [
    "cpf negativado",
    "cpf irregular",
    "status do cpf",
    "consulta cpf",
    "score",
    "serasa",
    "spc",
    "scpc",
    "boa vista",
    "boavista",
    "inadimplência",
    "inadimplencia",
    "inadimplente",
    "dívida",
    "divida",
    "dívidas",
    "dividas",
    "débito em aberto",
    "debito em aberto",
    "débito em cpf",
    "debito em cpf",
    "pagamento em aberto",
    "não recebemos o pagamento",
    "nao recebemos o pagamento",
    "ainda não recebemos o pagamento",
    "ainda nao recebemos o pagamento",
    "em atraso",
    "atraso",
    "atrasada",
    "atrasado",
    "incumprimento",
    "negativação",
    "negativacao",
    "restrição no cpf",
    "restricao no cpf",
    "restrições no cpf",
    "restricoes no cpf",
    "regularize",
    "regularização",
    "regularizacao",
    "renegociação",
    "renegociacao",
    "renegociar",
    "negociar",
    "negocie",
    "negociação",
    "negociacao",
    "proposta de renegociação",
    "proposta de renegociacao",
    "propostas de renegociação",
    "propostas de renegociacao",
    "acordo de dívida",
    "acordo de divida",
    "renegociação de dívida",
    "renegociacao de divida",
    "renegociação de dívidas",
    "renegociacao de dividas",
    "aviso de dívida",
    "aviso de divida",
    "aviso de dívidas",
    "aviso de dividas",
    "cartão em atraso",
    "cartao em atraso",
    "cartão atrasado",
    "cartao atrasado",
    "pendências do cartão",
    "pendencias do cartao",
    "pendência do cartão",
    "pendencia do cartao",
    "pendências no cartão",
    "pendencias no cartao",
    "pendência no cartão",
    "pendencia no cartao",
    "negociar todas as pendências do cartão",
    "negociar todas as pendencias do cartao",
    "fatura em atraso",
    "fatura atrasada",
    "parcelar fatura",
    "parcelamento de fatura",
    "fatura parcelada",
    "pagamento de cartão em atraso",
    "pagamento de cartao em atraso",
    "pagamento do cartão em atraso",
    "pagamento do cartao em atraso",
    "empréstimo em atraso",
    "emprestimo em atraso",
    "pagamento do seu empréstimo",
    "pagamento do seu emprestimo",
    "parcelas em atraso",
    "parcelas atrasadas",
    "empresa de cobrança",
    "empresa de cobranca",
    "assessoria de cobrança",
    "assessoria de cobranca",
    "recuperação de crédito",
    "recuperacao de credito",
    "crédito em atraso",
    "credito em atraso",
    "limpe seu nome",
    "nome limpo",
    "nome sujo",
    "cobrança",
    "cobranca",
    "cobranças",
    "cobrancas",
    "pendência financeira",
    "pendencia financeira",
    "pendências financeiras",
    "pendencias financeiras",
    "protesto",
    "protestado",
    "penhora",
    "penhorado",
    "penhorada",
]


def is_debt_or_credit_restriction(text: str) -> bool:
    return contains_any(text, DEBT_TERMS)


def infer_work_target(text: str) -> str | None:
    if contains_any(
        text,
        [
            "entrevista",
            "interview",
            "application update",
            "application received",
            "we've received your application",
            "recebemos sua candidatura",
            "retorno da sua candidatura",
            "candidate",
            "recruiter",
            "candidatura",
            "candidaturas",
            "greenhouse",
            "wellhub",
            "job offer",
            "hired you",
            "invitation to interview",
            "contract has started",
        ],
    ):
        return "01_PROFI/CANDIDATURAS"
    if contains_any(text, ["upwork", "99freelas", "proposal", "freelance", "brief", "projeto", "cliente", "proposta", "convite para projeto"]):
        return "01_PROFI/PROJETOS-PJ"
    if contains_any(text, ["alignerr", "cliente pj", "pj", "prestação de serviço", "prestacao de servico", "sme careers", "empresa cliente"]):
        return "01_PROFI/PROJETOS-PJ"
    if contains_any(text, WORK_TERMS):
        return "01_PROFI/VAGAS"
    return None


def is_course_promotion(text: str) -> bool:
    course_terms = [
        "python rpa", "udemy", "academy", "bootcamp", "curso", "cursos",
        "imersão", "imersao", "dev studio", "hotmart", "acesso vitalício",
        "acesso vitalicio", "inscrições abertas", "inscricoes abertas",
        "bônus surpresa", "bonus surpresa",
    ]
    return contains_any(text, course_terms)


def is_commercial_promotion(text: str) -> bool:
    if is_job_blast(text):
        return False
    if is_technical_newsletter(text):
        return False
    return contains_any(text, COMMERCIAL_PROMO_TERMS)


def is_security_urgent(text: str) -> bool:
    security_terms = [
        "verification code", "security code", "código de verificação",
        "codigo de verificacao", "verify your device", "please verify your device",
        "verify your location", "unknown device", "browser has been used",
        "código de login", "codigo de login", "otp", "password reset", "reset password",
        "redefinição da palavra-passe", "novo cadastro de dispositivo", "security alert",
    ]
    return contains_any(text, security_terms)


def is_technical_newsletter(text: str) -> bool:
    newsletter_terms = [
        "what's new", "whats new", "vs code", "github copilot", "parallel agents",
        "multi-step planning", "developer newsletter",
        "building ai on the right data foundation", "announcing", "newsletter",
    ]
    return contains_any(text, newsletter_terms)


def is_job_blast(text: str) -> bool:
    job_terms = [
        "vaga", "vagas", "home office", "oportunidades", "candidate-se",
        "está contratando", "esta contratando", "job", "jobs",
        "career opportunities", "oportunidade", "oportunidade de emprego",
        "hiring", "we are hiring", "join our team", "work with us",
        "recruiting", "recruitment",
    ]
    return contains_any(text, job_terms)


def _api_modify_with_retry(
    gmail_service,
    message_id: str,
    add_label_ids: list[str],
    remove_label_ids: list[str],
    max_retries: int = 3,
    base_delay: float = 2.0,
) -> None:
    """Modifica labels de uma mensagem com retry exponencial."""
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            gmail_service.users().messages().modify(
                userId="me",
                id=message_id,
                body={
                    "addLabelIds": add_label_ids,
                    "removeLabelIds": remove_label_ids,
                },
            ).execute()
            return
        except HttpError as exc:
            status = exc.resp.status if exc.resp else 0
            if status in (429, 500, 502, 503, 504):
                delay = base_delay * (2 ** attempt)
                logger.warning("HTTP %d ao modificar %s (tentativa %d/%d), aguardando %.1fs...",
                               status, message_id, attempt + 1, max_retries, delay)
                time.sleep(delay)
                last_exc = exc
            else:
                raise
        except Exception as exc:
            time.sleep(base_delay * (2 ** attempt))
            last_exc = exc

    raise RuntimeError(f"Falha após {max_retries} tentativas em {message_id}") from last_exc
