"""Funções determinísticas de qualidade para o pipeline RTI.

Este módulo não decide requisitos de engenharia: ele preserva evidências,
normaliza achados e registra cobertura para que um agente especializado ou
regra de domínio possa ser auditado no mesmo contrato SSOT.
"""
from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from collections import defaultdict


import semantic_pipeline


SCHEMA_VERSION = "2.3"
LITERAL_QUOTE_KEYS = {"citacao", "evidencia_literal", "quote", "evidence_sources"}
GENERIC_LOCATIONS = {
    "",
    "localização a confirmar",
    "localizacao a confirmar",
    "a confirmar",
    "localização desconhecida",
    "localizacao desconhecida",
    "trecho identificado automaticamente; confirmar seção/página.",
}


def _clean_literal_unicode(val):
    """Normaliza Unicode NFC e remove surrogates sem alterar a literalidade de citações."""
    if isinstance(val, str):
        if not val:
            return val
        val = val.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")
        val = unicodedata.normalize("NFC", val)
        val = re.sub(r"[\ud800-\udfff]", "", val)
        val = val.replace("\ufffd", "")
        return val
    elif isinstance(val, list):
        return [_clean_literal_unicode(item) for item in val]
    elif isinstance(val, dict):
        return {k: _clean_literal_unicode(v) for k, v in val.items()}
    return val


def sanitize_batch_isolation(val):
    """Remove ou neutraliza citações cruzadas a outros lotes para garantir isolamento estrito por lote."""
    if isinstance(val, str):
        if not val:
            return val
        val = val.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")
        val = unicodedata.normalize("NFC", val)
        val = re.sub(r"Idêntico ao achado [A-Z]{2,5}-\d{3} do Lote \d+:?\s*", "", val, flags=re.IGNORECASE)
        val = re.sub(r"— mesmo padrão do Lote \d+", "", val, flags=re.IGNORECASE)
        val = re.sub(r"\(Lote \d+\)", "", val, flags=re.IGNORECASE)
        val = re.sub(r"\(Lotes \d+(?:,\s*\d+)*(?:\s*e\s*\d+)?\)", "", val, flags=re.IGNORECASE)
        val = re.sub(r"Lote \d+ \(([^)]+)\)", r"\1", val, flags=re.IGNORECASE)
        val = val.replace(" \ufffd ", " — ")
        val = val.replace("\ufffd", "")
        return val
    elif isinstance(val, list):
        return [sanitize_batch_isolation(item) for item in val]
    elif isinstance(val, dict):
        return {
            k: (_clean_literal_unicode(v) if k in LITERAL_QUOTE_KEYS else sanitize_batch_isolation(v))
            for k, v in val.items()
        }
    return val


def clean_unicode_text(val):
    """Normaliza texto Unicode em NFC, sanitiza surrogates e garante isolamento estrito de lote."""
    if not isinstance(val, str):
        return val
    if not val:
        return ""
    return sanitize_batch_isolation(val)


# Termos que comprovam o contexto de uma lacuna por ausência. A citação deve
# mostrar o escopo efetivamente declarado, não o início arbitrário do arquivo.
EVIDENCE_ANCHORS = {
    "CARRIER-001": ["dwdm", "óptica", "fibra"],
    "CARRIER-002": ["mpls", "l2vpn", "l3vpn", "p2p"],
    "CARRIER-003": ["bgp", "peering", "ixp", "pni"],
    "CARRIER-004": ["dcn", "spine", "leaf", "evpn"],
    "CAR-BGP": ["bgp", "peering", "ixp", "pni"],
    "CAR-FIBRA": ["dwdm", "fibra apagada", "dark fiber"],
    "CAR-SERVICO": ["mpls", "l2vpn", "l3vpn", "p2p"],
    "CAR-SDWAN": ["sd-wan", "sdwan"],
    "CAR-DCN": ["dcn", "gerência", "oob"],
    "CTR-ACEITE": ["contrato", "cláusula", "contratada", "contratante"],
    "CTR-RESP": ["contrato", "cláusula", "contratada", "contratante"],
    "CARRIER": ["sd-wan", "sdwan", "bgp", "mpls", "fibra", "dwdm", "dcn"],
    "HLD": ["cluster", "redundância", "alta disponibilidade", "arquitetura"],
    "LLD": ["lld", "low level design", "configuração", "parametrização"],
    "RFP": ["rfp", "edital", "sla", "penalidade"],
    "LGPD": ["lgpd", "dados pessoais", "privacidade", "cpf"],
    "DC": ["datacenter", "data center", "tier", "ups", "rack"],
    "CLD": ["cloud", "nuvem", "aws", "azure", "gcp"],
    "INT": ["integração", "api", "rest", "soap", "esb"],
}


def _excerpt(text: str, needles: list[str], limit: int = 360) -> str:
    """Retorna uma citação literal curta, preferindo linha única com o termo relevante."""
    if not text or not text.strip():
        return ""
    lines = text.splitlines()
    for needle in needles:
        if not needle:
            continue
        needle_cf = needle.casefold()
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("[ABA:"):
                continue
            if needle_cf in stripped.casefold():
                collapsed = re.sub(r"\s+", " ", stripped).strip()
                if len(collapsed) <= limit:
                    return collapsed
                pos = collapsed.casefold().find(needle_cf)
                start = max(0, pos - 100)
                end = min(len(collapsed), pos + len(needle) + 220)
                return collapsed[start:end].strip()
    clean = re.sub(r"\s+", " ", text).strip()
    lower = clean.lower()
    for needle in needles:
        if not needle:
            continue
        pos = lower.find(needle.lower())
        if pos >= 0:
            start = max(0, pos - 100)
            end = min(len(clean), pos + len(needle) + 220)
            return clean[start:end].strip()
    for line in lines:
        collapsed = re.sub(r"\s+", " ", line).strip()
        if collapsed and not collapsed.startswith("[ABA:"):
            return collapsed[:limit].strip()
    return clean[:limit]


def _find_line_location(text: str, snippet: str) -> str:
    """Localiza a linha 1-based onde o trecho ocorre no texto extraído."""
    if not text or not snippet:
        return "Linha 1"
    clean_snip = re.sub(r"\s+", " ", snippet).strip()
    if not clean_snip:
        return "Linha 1"
    lines = text.splitlines()
    for probe_len in (80, 40):
        probe = clean_snip[:probe_len].casefold()
        if len(probe) < 6 and probe_len == 40:
            continue
        for idx, line in enumerate(lines, 1):
            if probe in re.sub(r"\s+", " ", line).strip().casefold():
                return f"Linha {idx}"
    short_probe = clean_snip[:40].casefold()
    if short_probe:
        pos = text.casefold().find(short_probe)
        if pos >= 0:
            return f"Linha {text[:pos].count(chr(10)) + 1}"
    words = [w for w in re.findall(r"[A-Za-zÀ-ÿ0-9_-]{4,}", clean_snip)][:5]
    if len(words) >= 2:
        rx = re.compile(r"\s+".join(re.escape(w) for w in words[:3]), re.I)
        match = rx.search(text)
        if match:
            return f"Linha {text[:match.start()].count(chr(10)) + 1}"
    for word in words:
        for idx, line in enumerate(lines, 1):
            if word.casefold() in line.casefold():
                return f"Linha {idx}"
    return "Linha 1"


def _stable_id(lote_name: str, finding: dict, source_text: str, ordinal: int) -> str:
    """ID reproduzível por lote/documento/regra/evidência, sem colisão entre arquivos."""
    rule = str(finding.get("rule_id") or finding.get("id") or "ACH").split("-")[0]
    document = str(finding.get("doc_path") or finding.get("doc_origem") or "documento")
    evidence = str(finding.get("citacao") or finding.get("evidencia_literal") or source_text[:500])
    material = "|".join((lote_name, document, rule, finding.get("title", ""), evidence, str(ordinal)))
    suffix = hashlib.sha1(material.encode("utf-8", "ignore")).hexdigest()[:8].upper()
    return f"{rule}-{suffix}"


def normalize_findings(lote_name: str, findings: list[dict], documents: list[dict]) -> list[dict]:
    """Impõe o contrato mínimo, evidencia literal e ID único a cada achado."""
    docs_by_path = {d.get("relative_path"): d for d in documents if d.get("relative_path")}
    docs_by_name = {d.get("name"): d for d in documents if d.get("name")}
    seen = set()
    normalized = []
    for ordinal, raw in enumerate(findings, 1):
        item = dict(raw)
        doc = docs_by_path.get(item.get("doc_path")) or docs_by_name.get(item.get("doc_origem"), {})
        source = doc.get("text", "")
        item["rule_id"] = item.get("rule_id") or item.get("id", "ACH")
        item["doc_path"] = doc.get("relative_path") or item.get("doc_path") or item.get("doc_origem", "")
        citation = item.get("citacao") or item.get("evidencia_literal")
        if not citation:
            rule_id = str(item["rule_id"]).upper()
            prefix = rule_id.split("-", 1)[0]
            anchors = EVIDENCE_ANCHORS.get(rule_id, EVIDENCE_ANCHORS.get(prefix, []))
            citation = _excerpt(source, anchors + [item.get("rule_id", ""), item.get("title", "")])
        item["citacao"] = citation
        item["evidencia_literal"] = citation

        loc_raw = str(item.get("localizacao_exata") or item.get("loc") or "").strip()
        loc_norm = semantic_pipeline.normalize_evidence_text(loc_raw)
        is_generic_loc = (
            not loc_raw
            or len(loc_raw) < 2
            or loc_norm in GENERIC_LOCATIONS
            or "confirmar seção/página" in loc_norm
            or "confirmar secao/pagina" in loc_norm
        )
        if is_generic_loc:
            computed_loc = _find_line_location(source, citation) if citation else "Linha 1"
            item["localizacao_exata"] = computed_loc
            item["loc"] = computed_loc
        else:
            item["localizacao_exata"] = loc_raw
            if not item.get("loc"):
                item["loc"] = loc_raw

        # Achados de ausência dependem de cobertura do documento, não de uma citação inventada.
        if item.get("tipo") == "Lacuna" and not citation:
            item["evid"] = "E1 (ausência verificada na extração disponível)"
        elif citation and not item.get("evid") and not item.get("evidencia"):
            item["evid"] = "E1 (trecho extraído da baseline)"

        if not item.get("evidence_sources") and citation and item.get("doc_path"):
            if source and semantic_pipeline.quote_is_literal(source, citation):
                item["evidence_sources"] = [{
                    "document_path": item["doc_path"],
                    "document_name": doc.get("name") or item.get("doc_origem", ""),
                    "location": item["localizacao_exata"],
                    "quote": citation,
                    "sha256": doc.get("sha256", ""),
                }]

        ev_str = str(item.get("evid") or item.get("evidencia") or "").strip().upper()
        ev_level = ev_str.split()[0] if ev_str else ""
        if ev_level == "E2" and len(item.get("evidence_sources") or []) == 1 and not item.get("referencias"):
            item["referencias"] = [{
                "titulo": f"Catálogo Normativo FCA-ENG-001 ({item['rule_id']})",
                "url": "",
                "nota": "Verificação determinística sobre a baseline documental.",
            }]

        candidate = _stable_id(lote_name, item, source, ordinal)
        while candidate in seen:
            ordinal += 1
            candidate = _stable_id(lote_name, item, source, ordinal)
        seen.add(candidate)
        item["id"] = candidate
        normalized.append(item)
    return normalized


def build_extraction_coverage(documents: list[dict]) -> dict:
    rows = []
    for doc in documents:
        text = doc.get("text", "")
        status = "extraido" if text.strip() else "nao_verificavel"
        rows.append({
            "arquivo": doc["relative_path"], "formato": doc.get("ext", ""),
            "status": status, "caracteres_extraidos": len(text),
            "aviso": doc.get("warning", "") or ("Sem texto extraível; OCR ou leitor específico necessário." if not text.strip() else "")
        })
    return {"total_arquivos": len(rows), "extraidos": sum(r["status"] == "extraido" for r in rows),
            "nao_verificaveis": sum(r["status"] != "extraido" for r in rows), "arquivos": rows}


RULE_PREFIX_CHECKLIST_MAP = {
    "edit-004": ["rfc.md", "editorial.md"],
    "edit-005": ["iso.md", "editorial.md"],
    "edit-006": ["iso.md", "editorial.md"],
    "edit-007": ["estrutura_e_referencias.md", "editorial.md"],
    "edit-008": ["estrutura_e_referencias.md", "editorial.md"],
    "edit-009": ["iso.md", "rfc.md", "editorial.md"],
    "edit": ["editorial.md", "estrutura_e_referencias.md"],
    "estr": ["estrutura_e_referencias.md", "editorial.md"],
    "rfp-norma": ["rfp.md", "iso.md", "ieee.md"],
    "rfp": ["rfp.md", "contratos.md"],
    "xref-prazo": ["rfp.md", "contratos.md"],
    "xref-sla": ["contratos.md", "rfp.md"],
    "ctr": ["contratos.md"],
    "hld": ["hld.md", "arquitetura.md"],
    "lld": ["lld.md", "arquitetura.md"],
    "car": ["carrier.md", "arquitetura.md"],
    "carrier": ["carrier.md", "arquitetura.md"],
    "lgpd": ["lgpd.md", "seguranca.md"],
    "cld": ["cloud.md", "arquitetura.md", "seguranca.md"],
    "dc": ["datacenter.md", "arquitetura.md"],
    "int": ["integracoes.md", "arquitetura.md", "tm_forum.md"],
    "xls": ["planilha.md", "tabelas.md"],
    "xref-qtd": ["planilha.md", "tabelas.md"],
    "dia": ["diagramas.md", "imagens.md"],
    "vis": ["diagramas.md", "imagens.md"],
    "visual": ["diagramas.md", "imagens.md"],
}

SKILL_CHECKLIST_MAP = {
    "analisar-documento": ["editorial.md", "estrutura_e_referencias.md"],
    "analisar-rfp": ["rfp.md", "contratos.md"],
    "analisar-hld": ["hld.md", "arquitetura.md"],
    "analisar-lld": ["lld.md", "arquitetura.md"],
    "analisar-contrato": ["contratos.md"],
    "analisar-carrier": ["carrier.md", "arquitetura.md"],
    "analisar-cloud": ["cloud.md", "arquitetura.md"],
    "analisar-datacenter": ["datacenter.md", "arquitetura.md"],
    "analisar-integracoes": ["integracoes.md", "tm_forum.md"],
    "analisar-lgpd": ["lgpd.md", "seguranca.md"],
    "analisar-planilha": ["planilha.md", "tabelas.md"],
    "analisar-diagramas": ["diagramas.md", "imagens.md"],
}

AUTOMATED_CHECKLISTS = {
    "editorial.md", "estrutura_e_referencias.md", "rfp.md", "contratos.md",
    "hld.md", "lld.md", "arquitetura.md", "carrier.md", "lgpd.md",
    "seguranca.md", "cloud.md", "datacenter.md", "integracoes.md",
    "planilha.md", "tabelas.md", "diagramas.md", "imagens.md",
    "iso.md", "rfc.md", "ieee.md",
}


def build_checklist_status(active_checklists: list[str], findings: list[dict], coverage: dict) -> dict:
    """Vincula achados aos 26 checklists de domínio e declara o estado real de verificação."""
    by_checklist = defaultdict(list)
    seen_per_checklist = defaultdict(set)

    def _add(chk: str, f: dict):
        fid = f.get("id", id(f))
        if fid not in seen_per_checklist[chk]:
            seen_per_checklist[chk].add(fid)
            by_checklist[chk].append(f)

    for finding in findings:
        rule = str(finding.get("rule_id") or finding.get("id") or "").lower()
        matched_rule = False
        for prefix, chks in RULE_PREFIX_CHECKLIST_MAP.items():
            if rule.startswith(prefix):
                for chk in chks:
                    _add(chk, finding)
                matched_rule = True
        sem_skill = str(finding.get("semantic_skill", "")).lower()
        if sem_skill in SKILL_CHECKLIST_MAP:
            for chk in SKILL_CHECKLIST_MAP[sem_skill]:
                _add(chk, finding)
            matched_rule = True
        if not matched_rule:
            cat = str(finding.get("cat") or finding.get("categoria") or "").lower()
            if "carrier" in cat or "dcn" in cat:
                _add("carrier.md", finding)
            elif "cloud" in cat or "nuvem" in cat:
                _add("cloud.md", finding)
            elif "datacenter" in cat:
                _add("datacenter.md", finding)
            elif "integra" in cat or "api" in cat:
                _add("integracoes.md", finding)
            elif "lgpd" in cat or "privacidade" in cat:
                _add("lgpd.md", finding)
            elif "contrato" in cat or "sla" in cat:
                _add("contratos.md", finding)
            elif "rfp" in cat or "edital" in cat:
                _add("rfp.md", finding)
            elif "hld" in cat:
                _add("hld.md", finding)
            elif "lld" in cat:
                _add("lld.md", finding)
            elif "planilha" in cat or "quantitativo" in cat:
                _add("planilha.md", finding)
            elif "diagrama" in cat or "imagem" in cat:
                _add("diagramas.md", finding)
            elif "estrutur" in cat or "redacional" in cat or "rfc" in cat:
                _add("editorial.md", finding)
                _add("estrutura_e_referencias.md", finding)

    result = {}
    for checklist in active_checklists:
        linked = by_checklist.get(checklist, [])
        if coverage.get("nao_verificaveis"):
            state = "Parcialmente verificável"
            obs = "Há arquivos sem texto extraível; não declarar conformidade integral."
        elif linked:
            state = "Não conforme"
            obs = f"{len(linked)} achado(s) vinculado(s) a controles deste checklist."
        elif checklist in AUTOMATED_CHECKLISTS and coverage.get("extraidos", 0) > 0:
            state = "Conforme (Controles Determinísticos)"
            obs = "Controles determinísticos executados sem apontamentos; sujeito à revisão semântica."
        else:
            state = "Não verificado"
            obs = "Checklist selecionado para verificação durante a revisão semântica especializada."
        result[checklist] = {
            "conformidade": state,
            "observacao": obs,
            "itens": [
                {
                    "verificacao": f.get("title", f.get("titulo", "")),
                    "status": "Não conforme",
                    "achado": f.get("id", "—"),
                    "evidencia": f.get("citacao", f.get("evidencia_literal", "")),
                }
                for f in linked
            ],
        }
    return result


def find_cross_document_conflicts(documents: list[dict]) -> list[dict]:
    """Detecta valores divergentes de SLA declarados em arquivos diferentes."""
    values = defaultdict(list)
    pattern = re.compile(r"\b(?:sla|disponibilidade)[^\n.]{0,120}?(\d{1,2}[,.]\d{1,4})\s*%", re.I)
    for doc in documents:
        text = doc.get("text", "")
        for match in pattern.finditer(text):
            value = match.group(1).replace(",", ".")
            line_no = text[:match.start()].count("\n") + 1
            values[value].append((doc, match.group(0), line_no))
    if len(values) < 2:
        return []
    refs = [(value, entries[0]) for value, entries in values.items() if entries]
    if len({entry[1][0]["relative_path"] for entry in refs}) < 2:
        return []
    first = refs[0]
    second = next(
        (r for r in refs[1:] if r[1][0]["relative_path"] != first[1][0]["relative_path"]),
        refs[1],
    )
    value_a, (doc_a, quote_a, line_a) = first
    value_b, (doc_b, quote_b, line_b) = second
    loc_a = f"Linha {line_a}"
    loc_b = f"Linha {line_b}"
    return [{
        "rule_id": "XREF-SLA", "title": "Divergência de meta de SLA entre documentos do lote",
        "doc_origem": doc_a["name"], "doc_path": doc_a["relative_path"],
        "loc": f"{loc_a} (confronto com {doc_b['name']} {loc_b})", "cat": "Correlação cruzada", "tipo": "Inconsistência",
        "evid": "E3 (confronto direto entre documentos)", "crit": "Alta", "prio": "P1",
        "citacao": f"{doc_a['name']}: {quote_a} | {doc_b['name']}: {quote_b}",
        "fato": f"O lote contém metas de SLA divergentes: {value_a}% e {value_b}%.",
        "impacto": "A divergência impede um critério único de aceite e apuração contratual.",
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

