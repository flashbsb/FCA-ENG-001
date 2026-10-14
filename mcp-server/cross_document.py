"""Correlação determinística entre os documentos de um mesmo lote."""
from __future__ import annotations

from collections import defaultdict
import re


def _context(text: str, match: re.Match, radius: int = 160) -> str:
    return re.sub(r"\s+", " ", text[max(0, match.start() - radius):min(len(text), match.end() + radius)]).strip()


def delivery_deadline_conflicts(documents: list[dict]) -> list[dict]:
    """Confronta prazos explicitamente qualificados como prazo de entrega."""
    matches = []
    rx = re.compile(r"\bprazo\s+de\s+entrega\D{0,60}?(\d+)\s*(dias?|mes(?:es)?)\b", re.I)
    for doc in documents:
        for match in rx.finditer(doc.get("text", "")):
            matches.append((doc, match, f"{match.group(1)} {match.group(2).lower()}"))
    values = {value for _, _, value in matches}
    docs = {doc["relative_path"] for doc, _, _ in matches}
    if len(values) < 2 or len(docs) < 2:
        return []
    first, second = matches[0], next(item for item in matches if item[2] != matches[0][2])
    doc_a, match_a, value_a = first
    doc_b, match_b, value_b = second
    return [{
        "rule_id": "XREF-PRAZO", "title": "Divergência de prazo de entrega entre documentos do lote",
        "doc_origem": doc_a["name"], "doc_path": doc_a["relative_path"],
        "loc": "Confronto cruzado de prazos de entrega", "cat": "Correlação cruzada",
        "tipo": "Inconsistência", "evid": "E3 (confronto direto entre documentos)", "crit": "Alta", "prio": "P1",
        "citacao": f"{doc_a['name']}: {_context(doc_a['text'], match_a)} | {doc_b['name']}: {_context(doc_b['text'], match_b)}",
        "fato": f"Os documentos declaram prazos de entrega distintos: {value_a} e {value_b}.",
        "impacto": "O cronograma e o critério de aceite não possuem referência única.",
        "tipo_solucao": "Plano de Ação Estruturado", "proprietario": "Gestão de Contratos / Engenharia",
    }]


def standards_without_edition(documents: list[dict]) -> list[dict]:
    """Identifica referências ISO/IEC/ABNT sem ano ou edição no mesmo trecho."""
    findings = []
    rx = re.compile(r"\b(?:ISO(?:/IEC)?|ABNT(?:\s+NBR)?|IEEE)\s*[- ]?\d{3,6}\b", re.I)
    for doc in documents:
        seen = set()
        text = doc.get("text", "")
        for match in rx.finditer(text):
            standard = match.group(0).upper()
            context = _context(text, match)
            if standard in seen or re.search(r"\b(?:19|20)\d{2}\b|ed(?:iç[aã]o|\.)?\s*\d+", context, re.I):
                continue
            seen.add(standard)
            findings.append({
                "rule_id": "RFP-NORMA", "title": "Norma referenciada sem edição identificável",
                "doc_origem": doc["name"], "doc_path": doc["relative_path"],
                "loc": "Trecho de referência normativa", "cat": "RFP / Edital", "tipo": "Lacuna",
                "evid": "E1 (trecho extraído da baseline)", "crit": "Média", "prio": "P2",
                "citacao": context, "fato": f"A referência a {standard} não apresenta ano ou edição no trecho extraído.",
                "impacto": "A versão normativa aplicável não fica objetivamente determinada.",
                "tipo_solucao": "Plano de Ação Estruturado", "proprietario": "Engenharia de Requisitos / Contratos",
            })
    return findings


def run(documents: list[dict], skills: list[str]) -> list[dict]:
    findings = delivery_deadline_conflicts(documents)
    if "analisar-rfp" in skills:
        findings.extend(standards_without_edition(documents))
    return findings
