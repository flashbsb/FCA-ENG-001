"""Correlação determinística entre os documentos de um mesmo lote."""
from __future__ import annotations

from collections import defaultdict
import re

from audit_pipeline import strip_non_normative_comments


def _context(text: str, match: re.Match, radius: int = 160) -> str:
    start, end = match.span()
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    if line_end - line_start >= 15 and "\n" not in text[start:end]:
        win_start = max(line_start, start - radius)
        win_end = min(line_end, end + radius)
    else:
        win_start = max(0, start - radius)
        win_end = min(len(text), end + radius)
    return re.sub(r"\s+", " ", text[win_start:win_end]).strip()


def delivery_deadline_conflicts(documents: list[dict]) -> list[dict]:
    """Confronta prazos explicitamente qualificados como prazo de entrega."""
    matches = []
    rx = re.compile(r"\bprazo\s+de\s+entrega\D{0,60}?(\d+)\s*(dias?|mes(?:es)?)\b", re.I)
    has_primary = any(doc.get("role") == "alvo_principal" for doc in documents)
    has_supporting = any(doc.get("role") == "apoio_cruzamento" for doc in documents)
    for doc in documents:
        for match in rx.finditer(doc.get("text", "")):
            matches.append((doc, match, f"{match.group(1)} {match.group(2).lower()}"))
    pair = next(
        (
            (a, b)
            for i, a in enumerate(matches)
            for b in matches[i + 1:]
            if a[0]["relative_path"] != b[0]["relative_path"]
            and a[2] != b[2]
            and (
                not (has_primary and has_supporting)
                or a[0].get("role") == "alvo_principal"
                or b[0].get("role") == "alvo_principal"
            )
        ),
        None,
    )
    if not pair:
        return []
    first, second = pair
    if has_primary and has_supporting and first[0].get("role") != "alvo_principal" and second[0].get("role") == "alvo_principal":
        first, second = second, first
    doc_a, match_a, value_a = first
    doc_b, match_b, value_b = second
    line_a = doc_a["text"][:match_a.start()].count("\n") + 1
    line_b = doc_b["text"][:match_b.start()].count("\n") + 1
    loc_a = f"Linha {line_a}"
    loc_b = f"Linha {line_b}"
    quote_a = _context(doc_a["text"], match_a)
    quote_b = _context(doc_b["text"], match_b)
    return [{
        "rule_id": "XREF-PRAZO", "title": "Divergência de prazo de entrega entre documentos do lote",
        "doc_origem": doc_a["name"], "doc_path": doc_a["relative_path"],
        "loc": f"{loc_a} (confronto com {doc_b['name']} {loc_b})", "cat": "Correlação cruzada",
        "tipo": "Inconsistência", "evid": "E3 (confronto direto entre documentos)", "crit": "Alta", "prio": "P1",
        "citacao": f"{doc_a['name']}: {quote_a} | {doc_b['name']}: {quote_b}",
        "fato": f"Os documentos declaram prazos de entrega distintos: {value_a} e {value_b}.",
        "impacto": "O cronograma e o critério de aceite não possuem referência única.",
        "tipo_solucao": "Plano de Ação Estruturado", "proprietario": "Gestão de Contratos / Engenharia",
        "evidence_sources": [
            {
                "document_path": doc_a["relative_path"],
                "document_name": doc_a["name"],
                "location": loc_a,
                "quote": quote_a,
                "sha256": doc_a.get("sha256", ""),
            },
            {
                "document_path": doc_b["relative_path"],
                "document_name": doc_b["name"],
                "location": loc_b,
                "quote": quote_b,
                "sha256": doc_b.get("sha256", ""),
            },
        ],
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
            loc_str = f"Linha {text[:match.start()].count(chr(10)) + 1}"
            findings.append({
                "rule_id": "RFP-NORMA", "title": "Norma referenciada sem edição identificável",
                "doc_origem": doc["name"], "doc_path": doc["relative_path"],
                "loc": loc_str, "localizacao_exata": loc_str, "cat": "RFP / Edital", "tipo": "Lacuna",
                "evid": "E1 (trecho extraído da baseline)", "crit": "Média", "prio": "P2",
                "citacao": context, "fato": f"A referência a {standard} não apresenta ano ou edição no trecho extraído.",
                "impacto": "A versão normativa aplicável não fica objetivamente determinada.",
                "tipo_solucao": "Plano de Ação Estruturado", "proprietario": "Engenharia de Requisitos / Contratos",
            })
    return findings


def run(documents: list[dict], skills: list[str]) -> list[dict]:
    norm_docs = [
        {**doc, "text": strip_non_normative_comments(doc.get("text", ""))}
        for doc in documents
    ]
    findings = delivery_deadline_conflicts(norm_docs)
    has_primary = any(doc.get("role") == "alvo_principal" for doc in norm_docs)
    target_norm_docs = (
        [doc for doc in norm_docs if doc.get("role", "alvo_principal") == "alvo_principal"]
        if has_primary else norm_docs
    )
    if "analisar-rfp" in skills:
        findings.extend(standards_without_edition(target_norm_docs))
    return findings
