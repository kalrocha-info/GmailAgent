from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom
from collections import defaultdict

from .learning import load_learning_state
from .migration import (
    ARCHIVE_TARGET_LABELS,
    EXPLICIT_SENDER_MAPPING,
    DEBT_TERMS,
    FINANCIAL_TERMS,
    NOTIFICATION_TERMS,
    PERSONAL_TERMS,
    PROMO_TERMS,
    URGENT_TERMS,
    WORK_TERMS,
    label_to_target,
)

logger = logging.getLogger(__name__)

# O Gmail tem limite para as queries, normalmente em torno de 1500 chars (varia). 
# Somos conservadores e fatiamos a cada 1200.
MAX_QUERY_LENGTH = 1200


def _debt_query() -> str:
    return _terms_query(DEBT_TERMS)


def build_filters_xml(config=None) -> str:
    """Gera um texto XML compatível com a importação de filtros do Gmail."""
    root = ET.Element("feed", xmlns="http://www.w3.org/2005/Atom")
    root.set("xmlns:apps", "http://schemas.google.com/apps/2006")
    ET.SubElement(root, "title").text = "Mail Filters"

    for criteria, actions in build_filter_specs(config):
        _add_filter_entry(root, criteria, actions)

    xml_str = ET.tostring(root, encoding="utf-8")
    parsed_xml = minidom.parseString(xml_str)

    # pretty_print nativo coloca muitas linhas em branco se não removermos, mas funciona.
    return parsed_xml.toprettyxml(indent="  ")


def build_filter_specs(config=None) -> list[tuple[dict[str, str], dict[str, str]]]:
    specs: list[tuple[dict[str, str], dict[str, str]]] = []
    learned_senders = {}
    learned_domains = {}

    if config and config.learning_rules_file and config.learning_rules_file.exists():
        state = load_learning_state(config.learning_rules_file)
        
        for sender, details in state.get("sender_rules", {}).items():
            if details.get("target_label"):
                learned_senders[sender] = label_to_target(details["target_label"]) or details["target_label"]
                
        for domain, details in state.get("domain_rules", {}).items():
            if details.get("target_label"):
                learned_domains[f"@{domain}"] = label_to_target(details["target_label"]) or details["target_label"]

    _generate_linkedin_newsletter_filters(specs)
    _generate_sender_filters(specs, _without_ambiguous_linkedin(EXPLICIT_SENDER_MAPPING))
    _generate_sender_filters(specs, _without_ambiguous_linkedin(learned_senders))
    _generate_sender_filters(specs, _without_ambiguous_linkedin(learned_domains))

    _generate_term_filters(specs, URGENT_TERMS, "03_URGENTE")
    _generate_term_filters(specs, WORK_TERMS, "01_PROFISSIONAL/VAGAS")
    _generate_term_filters(specs, PROMO_TERMS, "06_NEWSLETTER")
    _generate_term_filters(specs, NOTIFICATION_TERMS, "04_NOTIFICACOES")
    _generate_term_filters(specs, DEBT_TERMS, "02_FINANCEIRO/EM_ATRASO")
    _generate_term_filters(specs, FINANCIAL_TERMS, "02_FINANCEIRO/CONTAS", exclude_query=_debt_query())
    _generate_term_filters(specs, PERSONAL_TERMS, "04_NOTIFICACOES")

    return specs


def apply_filters(gmail_service, config=None, replace_existing: bool = False) -> dict:
    if replace_existing:
        existing = gmail_service.users().settings().filters().list(userId="me").execute().get("filter", [])
        for item in existing:
            gmail_service.users().settings().filters().delete(userId="me", id=item["id"]).execute()
    else:
        existing = []

    labels = gmail_service.users().labels().list(userId="me").execute().get("labels", [])
    label_ids = {label["name"]: label["id"] for label in labels}

    created = []
    failed = []
    for criteria, actions in build_filter_specs(config):
        target_label = actions.get("label")
        target_id = label_ids.get(target_label)
        if not target_id:
            failed.append({"criteria": criteria, "label": target_label, "error": "label ausente"})
            continue

        body = {
            "criteria": _api_criteria(criteria),
            "action": {
                "addLabelIds": [target_id],
                "removeLabelIds": ["INBOX"] if actions.get("shouldArchive") == "true" else [],
            },
        }
        try:
            created.append(gmail_service.users().settings().filters().create(userId="me", body=body).execute())
        except Exception as exc:  # noqa: BLE001
            failed.append({"criteria": criteria, "label": target_label, "error": str(exc)})

    return {
        "summary": {
            "deleted_existing": len(existing),
            "created": len(created),
            "failed": len(failed),
        },
        "created": created,
        "failed": failed,
    }


def _api_criteria(criteria: dict[str, str]) -> dict[str, str]:
    result = {}
    for key, value in criteria.items():
        if key == "hasTheWord":
            result["query"] = value
        elif key == "doesNotHaveTheWord":
            result["negatedQuery"] = value
        else:
            result[key] = value
    return result


def _add_filter_entry(root: ET.Element, criteria: dict[str, str], actions: dict[str, str]) -> None:
    """Constrói o bloco <entry> padrão do Gmail."""
    entry = ET.SubElement(root, "entry")
    ET.SubElement(entry, "category", term="filter")
    ET.SubElement(entry, "title").text = "Mail Filter"
    ET.SubElement(entry, "content") # A tag content entra vazia

    for k, v in criteria.items():
        ET.SubElement(entry, "apps:property", name=k, value=v)
    
    for k, v in actions.items():
        ET.SubElement(entry, "apps:property", name=k, value=v)


def _generate_sender_filters(specs: list[tuple[dict[str, str], dict[str, str]]], mapping: dict[str, str]) -> None:
    """Fatia as listas de remententes para não exceder limites de query no property `from`."""
    grouped = defaultdict(list)
    for sender, target in mapping.items():
        grouped[target].append(sender)
    
    for target, senders in grouped.items():
        actions = {"label": target}
        if target in ARCHIVE_TARGET_LABELS:
            actions["shouldArchive"] = "true"
        extra_criteria = {}
        if target == "02_FINANCEIRO/CONTAS":
            extra_criteria["doesNotHaveTheWord"] = _debt_query()

        chunk = []
        chunk_len = 0
        
        for sender in senders:
            if chunk_len + len(sender) + 4 > MAX_QUERY_LENGTH and chunk:
                criteria = {"from": " OR ".join(chunk), **extra_criteria}
                specs.append((criteria, actions))
                chunk = []
                chunk_len = 0
            
            chunk.append(sender)
            chunk_len += len(sender) + 4
        
        if chunk:
            criteria = {"from": " OR ".join(chunk), **extra_criteria}
            specs.append((criteria, actions))


def _without_ambiguous_linkedin(mapping: dict[str, str]) -> dict[str, str]:
    ambiguous = {"linkedin.com", "@linkedin.com", "newsletters-noreply@linkedin.com"}
    return {
        sender: target
        for sender, target in mapping.items()
        if sender.lower() not in ambiguous
    }


def _generate_linkedin_newsletter_filters(specs: list[tuple[dict[str, str], dict[str, str]]]) -> None:
    job_terms = [
        "vaga",
        "vagas",
        "home office",
        "oportunidade",
        "oportunidades",
        "contratando",
        "candidate-se",
        "job",
        "jobs",
    ]
    job_query = " OR ".join(f'"{term}"' if " " in term else term for term in job_terms)
    sender = "newsletters-noreply@linkedin.com"

    specs.append((
        {"from": sender, "hasTheWord": job_query},
        {"label": "01_PROFISSIONAL/VAGAS", "shouldArchive": "true"},
    ))
    specs.append((
        {"from": sender, "doesNotHaveTheWord": job_query},
        {"label": "06_NEWSLETTER", "shouldArchive": "true"},
    ))


def _generate_term_filters(
    specs: list[tuple[dict[str, str], dict[str, str]]],
    terms: list[str],
    target: str,
    exclude_query: str | None = None,
) -> None:
    """Fatia listas de dicionário/termos no property `hasTheWord`."""
    if not terms:
        return
        
    actions = {"label": target}
    if target in ARCHIVE_TARGET_LABELS:
        actions["shouldArchive"] = "true"

    chunk = []
    chunk_len = 0
    for term in terms:
        safe_term = _safe_term(term)
        
        if chunk_len + len(safe_term) + 4 > MAX_QUERY_LENGTH and chunk:
            criteria = {"hasTheWord": " OR ".join(chunk)}
            if exclude_query:
                criteria["doesNotHaveTheWord"] = exclude_query
            specs.append((criteria, actions))
            chunk = []
            chunk_len = 0
        
        chunk.append(safe_term)
        chunk_len += len(safe_term) + 4
    
    if chunk:
        criteria = {"hasTheWord": " OR ".join(chunk)}
        if exclude_query:
            criteria["doesNotHaveTheWord"] = exclude_query
        specs.append((criteria, actions))


def _terms_query(terms: list[str]) -> str:
    return " OR ".join(_safe_term(term) for term in terms)


def _safe_term(term: str) -> str:
    return f'"{term}"' if " " in term else term
