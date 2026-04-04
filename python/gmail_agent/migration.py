from __future__ import annotations

import logging
import time
from collections import Counter
from email.utils import parseaddr
from typing import Any

from googleapiclient.errors import HttpError


TARGET_LABELS = [
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
]

ARCHIVE_TARGET_LABELS = {
    "AGENTE/TRABALHO/VAGAS",
    "AGENTE/PROMOCOES",
    "AGENTE/NOTIFICACOES",
}

STALE_INBOX_ARCHIVE_TARGET_LABELS = {
    "AGENTE/TRABALHO/VAGAS",
    "AGENTE/PROMOCOES",
    "AGENTE/NOTIFICACOES",
}

EXPLICIT_LABEL_MAPPING = {
    "0_URGENTE": "AGENTE/URGENTE",
    "[Gmail]/SEGURANÇA": "AGENTE/URGENTE",
    "[Gmail]/00_INCUMPRIMENTO-PT": "AGENTE/URGENTE",
    "1_FINANCEIRO": "AGENTE/FINANCEIRO",
    "PT/1_FINANCEIRO": "AGENTE/FINANCEIRO",
    "[Gmail]/00_FINANCEIRO": "AGENTE/FINANCEIRO",
    "[Gmail]/COMPRAS": "AGENTE/FINANCEIRO",
    "[Gmail]/01_COMPRAS": "AGENTE/FINANCEIRO",
    "[Gmail]/00_GESTAO": "AGENTE/FINANCEIRO",
    "[Gmail]/02_SAUDE": "AGENTE/FINANCEIRO",
    "2_ESTUDOS": "AGENTE/TRABALHO/CANDIDATURAS",
    "PT/2_ESTUDOS": "AGENTE/TRABALHO/CANDIDATURAS",
    "[Gmail]/01_ESTUDOS": "AGENTE/TRABALHO/CANDIDATURAS",
    "[Gmail]/00_TRABALHO": "AGENTE/TRABALHO/PROJETOS",
    "[Gmail]/02_TRABALHO E CARREIRA": "AGENTE/TRABALHO/VAGAS",
    "[Gmail]/Candidaturas": "AGENTE/TRABALHO/CANDIDATURAS",
    "[Gmail]/ENTREVISTAS": "AGENTE/TRABALHO/CANDIDATURAS",
    "[Gmail]/PROFISSIONAL": "AGENTE/TRABALHO/CLIENTES-PJ",
    "3_VAGAS_PROMOCOES": "AGENTE/TRABALHO/VAGAS",
    "[Gmail]/06_NEWSLETTERS": "AGENTE/PROMOCOES",
    "[Gmail]/PROMOÇÕES": "AGENTE/PROMOCOES",
    "4_REDES_SOCIAIS": "AGENTE/NOTIFICACOES",
    "FLUXO/LinkedIn": "AGENTE/TRABALHO/VAGAS",
    "IA/Outros": "AGENTE/REVISAR",
}

EXPLICIT_SENDER_MAPPING = {
    "linkedin.com": "AGENTE/TRABALHO/VAGAS",
    "groups-noreply@linkedin.com": "AGENTE/NOTIFICACOES",
    "jobs-noreply@linkedin.com": "AGENTE/TRABALHO/VAGAS",
    "jobalerts-noreply@linkedin.com": "AGENTE/TRABALHO/VAGAS",
    "newsletters-noreply@linkedin.com": "AGENTE/NOTIFICACOES",
    "indeed.com": "AGENTE/TRABALHO/VAGAS",
    "infojobs.com.br": "AGENTE/TRABALHO/VAGAS",
    "jobrapidoalert.com": "AGENTE/TRABALHO/VAGAS",
    "greenhouse.io": "AGENTE/TRABALHO/CANDIDATURAS",
    "glassdoor.com": "AGENTE/TRABALHO/VAGAS",
    "wellhub.com": "AGENTE/TRABALHO/CANDIDATURAS",
    "upwork.com": "AGENTE/TRABALHO/PROJETOS",
    "99freelas.com.br": "AGENTE/TRABALHO/PROJETOS",
    "alignerr.com": "AGENTE/TRABALHO/CLIENTES-PJ",
    "sme": "AGENTE/TRABALHO/CANDIDATURAS",
    "vivo.com.br": "AGENTE/FINANCEIRO",
    "shopee.com": "AGENTE/PESSOAL",
    "picpay.com": "AGENTE/FINANCEIRO",
    "mercadopago.com": "AGENTE/FINANCEIRO",
    "amazon.com": "AGENTE/FINANCEIRO",
    "amazon.es": "AGENTE/FINANCEIRO",
    "amazon.com.br": "AGENTE/FINANCEIRO",
    "wise.com": "AGENTE/FINANCEIRO",
    "oney.pt": "AGENTE/FINANCEIRO",
    "gov.br": "AGENTE/URGENTE",
    "google.com": "AGENTE/NOTIFICACOES",
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
    "wellhub", "linkedin", "indeed", "infojobs", "jobrapido", "talent",
    "freelance", "projeto", "proposal", "proposal update",
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
            key.lower(): value["target_label"]
            for key, value in sender_rules.items()
            if value.get("target_label")
        }
        self.domain_mapping = {
            key.lower(): value["target_label"]
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
        plan = plan_message_reclassification(message, label_lookup)
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
            "Aplicar a nova label AGENTE alvo antes de remover labels antigas do email.",
            "Preservar labels de sistema do Gmail como INBOX, UNREAD, IMPORTANT e categorias nativas.",
            "Remover labels antigas somente quando houver uma correspondencia clara para AGENTE/...",
            "Manter emails sem mapeamento claro em AGENTE/REVISAR para triagem manual.",
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
    ensure_agent_labels(gmail_service, reverse_label_lookup)

    messages = report.get("messages", [])[:limit]
    changed = []
    skipped = []

    for message in messages:
        plan = plan_message_reclassification(message, label_lookup)
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
            if label_name.startswith("AGENTE/") and label_name != target_label
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

        if not any(label in STALE_INBOX_ARCHIVE_TARGET_LABELS for label in resolved_labels):
            skipped.append({
                "message_id": message.get("id"),
                "subject": message.get("subject"),
                "reason": "label nao elegivel para arquivamento tardio",
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
            "kept_labels": [label for label in resolved_labels if label.startswith("AGENTE/")],
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


def plan_message_reclassification(message: dict[str, Any], label_lookup: dict[str, str]) -> dict[str, Any]:
    resolved_labels = [label_lookup.get(label_id, label_id) for label_id in message.get("labelIds", [])]
    legacy_labels = [name for name in resolved_labels if is_legacy_label(name)]
    target = infer_target_from_message(message, resolved_labels)

    remove_labels = [label for label in legacy_labels if label != target]

    return {
        "message_id": message.get("id"),
        "thread_id": message.get("threadId"),
        "from": message.get("from"),
        "subject": message.get("subject"),
        "existing_labels": resolved_labels,
        "target_label": target,
        "remove_labels": remove_labels,
    }


def infer_target_from_message(message: dict[str, Any], resolved_labels: list[str]) -> str:
    subject = (message.get("subject") or "").lower()
    sender = (message.get("from") or "").lower()
    labels_text = " ".join(resolved_labels).lower()
    text = f"{subject} {sender} {labels_text}"

    explicit_target = first_explicit_label_target(resolved_labels)
    if explicit_target:
        return explicit_target

    if is_job_blast(text):
        return "AGENTE/TRABALHO/VAGAS"

    if is_security_urgent(text):
        return "AGENTE/URGENTE"

    if is_course_promotion(text):
        return "AGENTE/PROMOCOES"

    if is_technical_newsletter(text):
        return "AGENTE/NOTIFICACOES"

    if contains_any(text, URGENT_TERMS):
        return "AGENTE/URGENTE"

    sender_target = sender_based_target(sender, subject)
    if sender_target:
        return sender_target

    work_target = infer_work_target(text)
    if work_target:
        return work_target
    if contains_any(text, FINANCIAL_TERMS):
        return "AGENTE/FINANCEIRO"
    if contains_any(text, PROMO_TERMS):
        return "AGENTE/PROMOCOES"
    if contains_any(text, NOTIFICATION_TERMS):
        return "AGENTE/NOTIFICACOES"
    if contains_any(text, PERSONAL_TERMS):
        return "AGENTE/PESSOAL"

    if any(label.startswith("AGENTE/") for label in resolved_labels):
        for label in resolved_labels:
            if label == "AGENTE/TRABALHO":
                work_target = infer_work_target(text)
                return work_target or "AGENTE/TRABALHO/VAGAS"
            if label.startswith("AGENTE/"):
                return label

    if any(is_legacy_label(label) for label in resolved_labels):
        return suggest_target_label(next(label for label in resolved_labels if is_legacy_label(label)))

    return "AGENTE/REVISAR"


def suggest_target_label(label_name: str) -> str:
    if label_name in EXPLICIT_LABEL_MAPPING:
        return EXPLICIT_LABEL_MAPPING[label_name]

    name = label_name.lower()
    if contains_any(name, URGENT_TERMS):
        return "AGENTE/URGENTE"
    work_target = infer_work_target(name)
    if work_target:
        return work_target
    if contains_any(name, FINANCIAL_TERMS):
        return "AGENTE/FINANCEIRO"
    if contains_any(name, PROMO_TERMS):
        return "AGENTE/PROMOCOES"
    if contains_any(name, NOTIFICATION_TERMS):
        return "AGENTE/NOTIFICACOES"
    return "AGENTE/PESSOAL"


def first_explicit_label_target(labels: list[str]) -> str | None:
    for label in labels:
        if label in EXPLICIT_LABEL_MAPPING:
            return EXPLICIT_LABEL_MAPPING[label]
    return None


def is_legacy_label(name: str) -> bool:
    if name.startswith("AGENTE/"):
        return False
    prefixes = ("[Gmail]/", "PT/", "FLUXO/", "IA/")
    numeric_roots = ("0_", "1_", "2_", "3_", "4_")
    return name.startswith(prefixes) or name.startswith(numeric_roots)


def contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


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
            if target.startswith("AGENTE/TRABALHO") and contains_any(subject_lower, ["code", "security", "login", "verification", "otp", "sign-in"]):
                return "AGENTE/URGENTE"
            return target

    if "jobs" in subject_lower and "access" in subject_lower:
        return "AGENTE/TRABALHO/VAGAS"

    return None


FINANCIAL_TERMS = [
    "financeiro", "fatura", "pix", "boleto", "compra", "compras", "mercadopago",
    "picpay", "amazon", "gestao", "cartão", "cartao", "oney", "bank", "banco",
    "extrato", "seguro", "débito", "debito", "parcela", "recibo", "wise",
    "transferência", "transferencia", "pagamento", "pagável", "paga", "fechou",
]


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
        return "AGENTE/TRABALHO/CANDIDATURAS"
    if contains_any(text, ["upwork", "99freelas", "proposal", "freelance", "brief", "projeto", "cliente", "proposta", "convite para projeto"]):
        return "AGENTE/TRABALHO/PROJETOS"
    if contains_any(text, ["alignerr", "cliente pj", "pj", "prestação de serviço", "prestacao de servico", "sme careers", "empresa cliente"]):
        return "AGENTE/TRABALHO/CLIENTES-PJ"
    if contains_any(text, WORK_TERMS):
        return "AGENTE/TRABALHO/VAGAS"
    return None


def is_course_promotion(text: str) -> bool:
    course_terms = [
        "python rpa", "udemy", "academy", "bootcamp", "curso", "cursos",
        "imersão", "imersao", "dev studio", "hotmart", "acesso vitalício",
        "acesso vitalicio", "inscrições abertas", "inscricoes abertas",
        "bônus surpresa", "bonus surpresa",
    ]
    return contains_any(text, course_terms)


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
        "career opportunities", "oportunidade",
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
