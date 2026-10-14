"""Contrato e normalização para achados produzidos pela revisão semântica.

O módulo não chama modelos nem decide conformidade. Ele valida a proveniência
e o formato dos achados gerados pelo agente revisor antes da persistência.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata


SEMANTIC_DOCUMENT_EXTS = {
    ".pdf", ".docx", ".txt", ".md", ".json", ".yaml", ".yml",
    ".xlsx", ".xls", ".csv", ".svg", ".drawio",
}
VISUAL_ONLY_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
SPREADSHEET_SKILLS = {"analisar-planilha"}
VISUAL_SKILLS = {"analisar-diagramas"}
ALLOWED_TYPES = {"Lacuna", "Inconsistência", "Risco", "Ambiguidade", "Erro", "Errata/Estrutura", "Recomendação", "Boa Prática"}
ALLOWED_CRITICALITY = {"Crítica", "Alta", "Média", "Baixa", "Informativa"}
ALLOWED_PRIORITY = {"P0", "P1", "P2", "P3"}
ALLOWED_EVIDENCE = {"E1", "E2", "E3"}
MAX_TEXT_FIELD = 5000
MAX_QUOTE = 2000
MAX_EVIDENCE_SOURCES = 12


def normalize_evidence_text(value: str) -> str:
    """Normaliza somente Unicode e espaços; não remove palavras/sinais da citação."""
    normalized = unicodedata.normalize("NFC", str(value or ""))
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def quote_is_literal(source_text: str, quote: str) -> bool:
    candidate = normalize_evidence_text(quote)
    return bool(candidate) and candidate in normalize_evidence_text(source_text)


def split_text(text: str, start_char: int = 0, max_chars: int = 12000) -> dict:
    """Retorna um bloco contíguo de texto com cursor explícito para paginação."""
    if not isinstance(start_char, int) or start_char < 0:
        raise ValueError("start_char deve ser um inteiro não negativo.")
    if not isinstance(max_chars, int) or max_chars < 1:
        raise ValueError("max_chars deve ser um inteiro positivo.")
    max_chars = min(max_chars, 30000)
    start = min(start_char, len(text))
    end = min(start + max_chars, len(text))
    return {
        "start_char": start,
        "end_char": end,
        "total_chars": len(text),
        "has_more": end < len(text),
        "next_start_char": end if end < len(text) else None,
        "text": text[start:end],
    }


def build_required_scopes(documents: list[dict], skills: list[str]) -> tuple[list[dict], list[str]]:
    """Monta a matriz skill/documento; planilhas e diagramas usam seus canais próprios."""
    readable = []
    unreadable = []
    for doc in documents:
        ext = str(doc.get("ext", "")).lower()
        path = str(doc.get("relative_path", ""))
        if ext in VISUAL_ONLY_EXTS:
            continue
        if ext not in SEMANTIC_DOCUMENT_EXTS:
            continue
        if str(doc.get("text", "")).strip():
            readable.append(doc)
        else:
            unreadable.append(path)

    scopes = []
    for skill in dict.fromkeys(str(s) for s in skills if str(s) not in VISUAL_SKILLS):
        for doc in readable:
            if skill in SPREADSHEET_SKILLS and str(doc.get("ext", "")).lower() not in {".xlsx", ".xls", ".csv"}:
                continue
            scopes.append({"skill": skill, "document_path": str(doc["relative_path"])})
    return scopes, sorted(path for path in unreadable if path)


def scope_key(skill: str, document_path: str) -> str:
    return f"{skill}::{document_path}"


def normalize_semantic_finding(
    raw: dict,
    documents_by_path: dict[str, dict],
    active_skills: set[str],
    batch_name: str,
) -> dict:
    """Valida evidências literais e produz um achado compatível com o SSOT."""
    if not isinstance(raw, dict):
        raise ValueError("Achado semântico deve ser um objeto.")

    skill = str(raw.get("skill", "")).strip()
    if not skill or skill not in active_skills or skill in VISUAL_SKILLS:
        raise ValueError(f"Skill semântica não ativa ou inválida: {skill or '(vazia)'}.")

    title = str(raw.get("title", "")).strip()
    fact = str(raw.get("fato", "")).strip()
    impact = str(raw.get("impacto", "")).strip()
    if not title or not fact or not impact:
        raise ValueError("Achado semântico precisa de title, fato e impacto.")
    if any(len(v) > MAX_TEXT_FIELD for v in (title, fact, impact)):
        raise ValueError("Título, fato ou impacto excedem o limite de tamanho.")

    finding_type = str(raw.get("tipo", "")).strip()
    criticality = str(raw.get("criticidade", "")).strip()
    priority = str(raw.get("prioridade", "")).strip()
    evidence = str(raw.get("evidencia", "E1")).strip().upper()
    evidence_level = evidence.split()[0] if evidence else ""
    if finding_type not in ALLOWED_TYPES:
        raise ValueError(f"Tipo de achado semântico inválido: {finding_type!r}.")
    if criticality not in ALLOWED_CRITICALITY or priority not in ALLOWED_PRIORITY:
        raise ValueError("Criticidade ou prioridade do achado semântico inválida.")
    if evidence_level not in ALLOWED_EVIDENCE:
        raise ValueError("Grau de evidência deve começar com E1, E2 ou E3.")
    if criticality in {"Crítica", "Alta"} and evidence_level == "E1":
        raise ValueError("Achados críticos/altos exigem evidência E2 ou E3.")
    if priority == "P0" and criticality != "Crítica":
        raise ValueError("Prioridade P0 exige criticidade Crítica.")

    sources = raw.get("evidence_sources")
    if not isinstance(sources, list) or not sources:
        document_path = str(raw.get("document_path", raw.get("doc_path", ""))).strip()
        quote = str(raw.get("quote", raw.get("citacao", ""))).strip()
        sources = [{"document_path": document_path, "quote": quote,
                    "location": str(raw.get("localizacao_exata", raw.get("loc", ""))).strip()}]
    if len(sources) > MAX_EVIDENCE_SOURCES:
        raise ValueError(f"Um achado pode ter no máximo {MAX_EVIDENCE_SOURCES} fontes de evidência.")

    validated_sources = []
    source_signatures = set()
    for index, source in enumerate(sources, 1):
        if not isinstance(source, dict):
            raise ValueError(f"Fonte de evidência #{index} deve ser um objeto.")
        path = str(source.get("document_path", "")).strip()
        quote = str(source.get("quote", "")).strip()
        location = str(source.get("location", "")).strip()
        document = documents_by_path.get(path)
        if not document:
            raise ValueError(f"Fonte de evidência #{index} não pertence à baseline: {path or '(caminho vazio)' }.")
        if not quote or len(quote) > MAX_QUOTE:
            raise ValueError(f"Citação #{index} vazia ou acima de {MAX_QUOTE} caracteres.")
        if not quote_is_literal(str(document.get("text", "")), quote):
            raise ValueError(f"Citação #{index} não localizada literalmente na baseline {path}.")
        source_signature = (path, normalize_evidence_text(quote))
        if source_signature in source_signatures:
            raise ValueError(f"Fonte de evidência #{index} duplica citação já informada para {path}.")
        source_signatures.add(source_signature)
        validated_sources.append({
            "document_path": path,
            "document_name": str(document.get("name") or path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]),
            "location": location or "Localização a confirmar",
            "quote": quote,
            "sha256": str(document.get("sha256", "")),
        })

    if evidence_level == "E3" and len(validated_sources) < 2:
        raise ValueError("Evidência E3 exige ao menos duas citações literais para confronto direto.")

    primary = validated_sources[0]
    rule_id = str(raw.get("rule_id", "")).strip() or f"SEM-{skill.replace('analisar-', '').upper()}"
    material = "|".join((batch_name, skill, rule_id, primary["document_path"],
                         normalize_evidence_text(title),
                         "|".join(normalize_evidence_text(s["quote"]) for s in validated_sources)))
    finding_id = "SEM-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:10].upper()
    citations = "\n".join(
        f"{source['document_path']} — {source['location']}: {source['quote']}"
        for source in validated_sources
    )
    references = raw.get("referencias", [])
    if not isinstance(references, list):
        raise ValueError("referencias deve ser uma lista.")
    normalized_references = []
    for reference in references[:10]:
        if isinstance(reference, dict):
            title_ref = str(reference.get("titulo", "")).strip()
            url_ref = str(reference.get("url", "")).strip()
            note_ref = str(reference.get("nota", "")).strip()
            if not title_ref and not url_ref and not note_ref:
                continue
            if url_ref and not url_ref.startswith(("https://", "http://")):
                raise ValueError("URL de referência corroborativa deve usar HTTP ou HTTPS.")
            normalized_references.append({"titulo": title_ref[:300], "url": url_ref[:1000], "nota": note_ref[:MAX_TEXT_FIELD]})
        elif isinstance(reference, str):
            reference = reference.strip()
            if reference:
                normalized_references.append({"titulo": reference[:300], "url": "", "nota": ""})
    if evidence_level == "E2" and len(validated_sources) < 2 and not normalized_references:
        raise ValueError("Evidência E2 exige duas citações literais ou uma referência técnica corroborativa válida.")

    return {
        "id": finding_id,
        "title": title,
        "doc_origem": primary["document_name"],
        "loc": primary["location"],
        "categoria": str(raw.get("categoria", f"Análise semântica / {skill}"))[:300],
        "tipo": finding_type,
        "evidencia": evidence,
        "citacao": citations,
        "evidencia_literal": citations,
        "localizacao_exata": primary["location"],
        "doc_path": primary["document_path"],
        "rule_id": rule_id,
        "criticidade": criticality,
        "prioridade": priority,
        "fato": fact,
        "impacto": impact,
        "solucao": str(raw.get("solucao", ""))[:MAX_TEXT_FIELD],
        "de": str(raw.get("de", ""))[:MAX_TEXT_FIELD],
        "para": str(raw.get("para", ""))[:MAX_TEXT_FIELD],
        "is_direct": bool(raw.get("de") or raw.get("para")),
        "proprietario": str(raw.get("proprietario", "Engenharia / Arquitetura"))[:300],
        "semantic_skill": skill,
        "source_kind": "agente_semantico",
        "evidence_sources": validated_sources,
        "referencias": normalized_references,
    }


def initialize_semantic_state(documents: list[dict], skills: list[str]) -> dict:
    required, unreadable = build_required_scopes(documents, skills)
    required_skills = list(dict.fromkeys(item["skill"] for item in required))
    required_documents = list(dict.fromkeys(item["document_path"] for item in required))
    if not required:
        status = "não_verificável" if unreadable else "não_aplicável"
    else:
        status = "pendente"
    return {
        "status": status,
        "required_skills": required_skills,
        "required_documents": required_documents,
        "required_scopes": [scope_key(item["skill"], item["document_path"]) for item in required],
        "reviewed_scopes": [],
        "expected_scope_count": len(required),
        "findings_recorded": 0,
        "unreadable_documents": unreadable,
    }

