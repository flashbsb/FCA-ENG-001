"""Controles especializados rastreáveis para a RTI.

As regras deste módulo somente registram ausência ou inconsistência documental;
não concluem viabilidade técnica ou interpretação jurídica.
"""
from __future__ import annotations

import os
import re


def _quote(text: str, match: re.Match | None, radius: int = 220) -> str:
    if not text or not match:
        return ""
    start, end = match.span()
    return re.sub(r"\s+", " ", text[max(0, start - radius):min(len(text), end + radius)]).strip()


def _finding(rule_id: str, title: str, doc: dict, match: re.Match | None, *, category: str,
             finding_type: str, fact: str, impact: str, crit: str = "Média", prio: str = "P2") -> dict:
    citation = _quote(doc.get("text", ""), match)
    return {
        "rule_id": rule_id, "title": title, "doc_origem": doc["name"],
        "doc_path": doc["relative_path"], "loc": "Trecho identificado automaticamente; confirmar seção/página.",
        "cat": category, "tipo": finding_type,
        "evid": "E1 (trecho extraído da baseline)", "crit": crit, "prio": prio,
        "citacao": citation, "fato": fact, "impacto": impact,
        "tipo_solucao": "Plano de Ação Estruturado", "proprietario": "Área técnica responsável",
    }


def _sentences_with(text: str, pattern: str):
    rx = re.compile(pattern, re.I)
    for sentence_match in re.finditer(r"[^.!?\n]{0,500}[.!?]", text, re.S):
        sentence = sentence_match.group(0)
        hit = rx.search(sentence)
        if hit:
            offset = sentence_match.start() + hit.start()
            yield re.compile(re.escape(text[offset:offset + len(hit.group(0))])).search(text)


def analyze_rfp(documents: list[dict]) -> list[dict]:
    findings = []
    names = [os.path.splitext(d["name"])[0].lower() for d in documents]
    missing_references = set()
    sla_gaps = set()
    sla_documents = set()
    for doc in documents:
        text = doc.get("text", "")
        # Referências a anexos explicitamente ausentes no lote.
        for match in re.finditer(r"\b(?:anexo|ap[eê]ndice)\s+([A-Z](?:\.\d+)?|\d+)\b", text, re.I):
            token = match.group(1).lower()
            expected = re.compile(rf"\b(?:anexo|ap[eê]ndice)[ _-]*{re.escape(token)}\b", re.I)
            reference_key = (doc["relative_path"], token)
            if not any(expected.search(name) for name in names) and reference_key not in missing_references:
                missing_references.add(reference_key)
                findings.append(_finding("RFP-ANEXO", "Referência a anexo não localizado no lote", doc, match,
                    category="RFP / Edital", finding_type="Lacuna",
                    fact=f"O texto referencia Anexo/Apêndice {match.group(1)}, mas nenhum arquivo do lote possui essa identificação.",
                    impact="A completude do escopo e dos requisitos não pode ser confirmada.", crit="Alta", prio="P1"))
        # SLA explícito sem todos os elementos mínimos no mesmo contexto documental.
        for match in _sentences_with(text, r"\b(?:sla|disponibilidade|tempo de atendimento|rma)\b"):
            if doc["relative_path"] in sla_documents:
                continue
            quote = _quote(text, match, 320).lower()
            missing = []
            if not re.search(r"\d+(?:[,.]\d+)?\s*%|\d+\s*(?:h|hora|dia|minuto)", quote): missing.append("valor")
            if not re.search(r"mensal|m[eê]s|per[ií]odo|janela|24x7|comercial", quote): missing.append("janela")
            if not re.search(r"c[aá]lculo|medição|apur|f[oó]rmula", quote): missing.append("método")
            if not re.search(r"penalidade|multa|glosa|cr[eé]dito", quote): missing.append("consequência")
            if missing and doc["relative_path"] not in sla_documents:
                sla_documents.add(doc["relative_path"])
                findings.append(_finding("RFP-SLA", "SLA sem elementos mínimos de aferição", doc, match,
                    category="RFP / Edital", finding_type="Lacuna",
                    fact="O trecho de SLA não explicita: " + ", ".join(missing) + ".",
                    impact="O aceite e a apuração de desempenho ficam sujeitos a interpretações divergentes.", crit="Alta", prio="P1"))
    return findings


def analyze_lld(documents: list[dict]) -> list[dict]:
    findings = []
    for doc in documents:
        text = doc.get("text", "")
        trigger = re.search(r"\b(?:lld|low level design|parametriza|configura[cç][aã]o detalhada|runbook)\b", text, re.I)
        if not trigger:
            continue
        checks = [("LLD-ROLLBACK", r"rollback|revers[aã]o", "Procedimento de rollback não identificado", "O documento de detalhamento não contém referência a reversão/rollback.", "Uma falha de implantação pode não ter procedimento documentado de recuperação."),
                  ("LLD-TESTE", r"plano de teste|caso de teste|crit[eé]rio de aceite", "Plano de teste e aceite não identificado", "O documento de detalhamento não contém plano de teste ou critério de aceite.", "A implementação pode não possuir validação objetiva pós-mudança."),
                  ("LLD-ENDERECO", r"\b(?:ip|vlan|sub-?rede|endere[cç]amento)\b", "Endereçamento ou VLAN não identificado", "O documento de detalhamento não contém referência a endereçamento, VLAN ou sub-rede.", "A implementabilidade do desenho não pode ser confirmada."),]
        for rule, required, title, fact, impact in checks:
            if not re.search(required, text, re.I):
                findings.append(_finding(rule, title, doc, trigger, category="LLD / Detalhamento", finding_type="Lacuna", fact=fact, impact=impact))
    return findings


def analyze_contract(documents: list[dict]) -> list[dict]:
    findings = []
    for doc in documents:
        text = doc.get("text", "")
        trigger = re.search(r"\b(?:contrato|cl[aá]usula|penalidade|rescis[aã]o|glosa)\b", text, re.I)
        if not trigger:
            continue
        for rule, required, title, fact in [
            ("CTR-ACEITE", r"crit[eé]rio de aceite|aceite", "Critério de aceite não identificado", "Há conteúdo contratual, mas não foi localizado critério de aceite."),
            ("CTR-RESP", r"contratante|contratada|respons[aá]vel", "Responsabilidades das partes não identificadas", "Há conteúdo contratual, mas não foi localizada atribuição explícita às partes."),
        ]:
            if not re.search(required, text, re.I):
                findings.append(_finding(rule, title, doc, trigger, category="Contrato / SLA", finding_type="Lacuna", fact=fact,
                    impact="A obrigação documental deve ser encaminhada à área competente para esclarecimento, sem interpretação jurídica."))
    return findings


def analyze_spreadsheets(documents: list[dict]) -> list[dict]:
    findings = []
    for doc in documents:
        if doc.get("ext") not in (".xlsx", ".xls", ".csv"):
            continue
        text = doc.get("text", "")
        trigger = re.search(r"\S", text)
        if not trigger:
            findings.append(_finding("XLS-EXTRACAO", "Planilha sem conteúdo extraível", doc, trigger,
                category="Planilha / Quantitativo", finding_type="Lacuna", fact="A planilha não retornou células de texto ou valores na extração.",
                impact="A conferência de quantitativos e fórmulas não pode ser realizada."))
            continue
        header_found = any(re.search(r"quant|qtd|item|descri[cç][aã]o|modelo|valor|pre[cç]o|origem|status", line, re.I)
                           for line in text.splitlines() if line.strip() and not line.lstrip().startswith("[ABA:"))
        if not header_found:
            findings.append(_finding("XLS-CABECALHO", "Cabeçalho de planilha não identificável", doc, trigger,
                category="Planilha / Quantitativo", finding_type="Ambiguidade", fact="A primeira linha extraída não contém cabeçalho identificável de item, quantitativo ou valor.",
                impact="A rastreabilidade dos dados tabulares fica reduzida.", crit="Baixa", prio="P3"))
    return findings


def analyze_diagrams(documents: list[dict]) -> list[dict]:
    findings = []
    images = [d for d in documents if d.get("ext") in (".png", ".jpg", ".jpeg", ".svg", ".drawio", ".bmp")]
    for doc in images:
        if not re.match(r"fig\d{2}_", os.path.basename(doc["name"]), re.I):
            findings.append(_finding("DIA-NOME", "Diagrama fora do padrão de nomenclatura rastreável", doc, None,
                category="Diagrama/Imagem", finding_type="Errata/Estrutura",
                fact="O nome do arquivo não segue o padrão figNN_documento_secao_descricao.",
                impact="A vinculação do diagrama à seção e à baseline fica menos rastreável.", crit="Baixa", prio="P3"))
    return findings


def run_specialized_controls(documents: list[dict], skills: list[str]) -> list[dict]:
    active = set(skills)
    findings = []
    if "analisar-rfp" in active: findings.extend(analyze_rfp(documents))
    if "analisar-lld" in active: findings.extend(analyze_lld(documents))
    if "analisar-contrato" in active: findings.extend(analyze_contract(documents))
    if "analisar-planilha" in active: findings.extend(analyze_spreadsheets(documents))
    if "analisar-diagramas" in active: findings.extend(analyze_diagrams(documents))
    return findings
