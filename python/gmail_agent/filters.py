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
    FINANCIAL_TERMS,
    NOTIFICATION_TERMS,
    PERSONAL_TERMS,
    PROMO_TERMS,
    URGENT_TERMS,
    WORK_TERMS,
)

logger = logging.getLogger(__name__)

# O Gmail tem limite para as queries, normalmente em torno de 1500 chars (varia). 
# Somos conservadores e fatiamos a cada 1200.
MAX_QUERY_LENGTH = 1200


def build_filters_xml(config=None) -> str:
    """Gera um texto XML compatível com a importação de filtros do Gmail."""
    root = ET.Element("feed", xmlns="http://www.w3.org/2005/Atom")
    root.set("xmlns:apps", "http://schemas.google.com/apps/2006")
    ET.SubElement(root, "title").text = "Mail Filters"

    learned_senders = {}
    learned_domains = {}

    if config and config.learning_rules_file and config.learning_rules_file.exists():
        state = load_learning_state(config.learning_rules_file)
        
        for sender, details in state.get("sender_rules", {}).items():
            if details.get("target_label"):
                learned_senders[sender] = details["target_label"]
                
        for domain, details in state.get("domain_rules", {}).items():
            if details.get("target_label"):
                learned_domains[f"@{domain}"] = details["target_label"]

    _generate_sender_filters(root, EXPLICIT_SENDER_MAPPING)
    _generate_sender_filters(root, learned_senders)
    _generate_sender_filters(root, learned_domains)

    _generate_term_filters(root, URGENT_TERMS, "AGENTE/URGENTE")
    _generate_term_filters(root, WORK_TERMS, "AGENTE/TRABALHO/VAGAS")
    _generate_term_filters(root, PROMO_TERMS, "AGENTE/PROMOCOES")
    _generate_term_filters(root, NOTIFICATION_TERMS, "AGENTE/NOTIFICACOES")
    _generate_term_filters(root, FINANCIAL_TERMS, "AGENTE/FINANCEIRO")
    _generate_term_filters(root, PERSONAL_TERMS, "AGENTE/PESSOAL")

    xml_str = ET.tostring(root, encoding="utf-8")
    parsed_xml = minidom.parseString(xml_str)
    
    # pretty_print nativo coloca muitas linhas em branco se não removermos, mas funciona.
    return parsed_xml.toprettyxml(indent="  ")


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


def _generate_sender_filters(root: ET.Element, mapping: dict[str, str]) -> None:
    """Fatia as listas de remententes para não exceder limites de query no property `from`."""
    grouped = defaultdict(list)
    for sender, target in mapping.items():
        grouped[target].append(sender)
    
    for target, senders in grouped.items():
        actions = {"label": target}
        if target in ARCHIVE_TARGET_LABELS:
            actions["shouldArchive"] = "true"

        chunk = []
        chunk_len = 0
        
        for sender in senders:
            if chunk_len + len(sender) + 4 > MAX_QUERY_LENGTH and chunk:
                criteria = {"from": " OR ".join(chunk)}
                _add_filter_entry(root, criteria, actions)
                chunk = []
                chunk_len = 0
            
            chunk.append(sender)
            chunk_len += len(sender) + 4
        
        if chunk:
            criteria = {"from": " OR ".join(chunk)}
            _add_filter_entry(root, criteria, actions)


def _generate_term_filters(root: ET.Element, terms: list[str], target: str) -> None:
    """Fatia listas de dicionário/termos no property `hasTheWord`."""
    if not terms:
        return
        
    actions = {"label": target}
    if target in ARCHIVE_TARGET_LABELS:
        actions["shouldArchive"] = "true"

    chunk = []
    chunk_len = 0
    for term in terms:
        # Tenta não quebrar buscas com espaço
        safe_term = f'"{term}"' if ' ' in term else term
        
        if chunk_len + len(safe_term) + 4 > MAX_QUERY_LENGTH and chunk:
            criteria = {"hasTheWord": " OR ".join(chunk)}
            _add_filter_entry(root, criteria, actions)
            chunk = []
            chunk_len = 0
        
        chunk.append(safe_term)
        chunk_len += len(safe_term) + 4
    
    if chunk:
        criteria = {"hasTheWord": " OR ".join(chunk)}
        _add_filter_entry(root, criteria, actions)
