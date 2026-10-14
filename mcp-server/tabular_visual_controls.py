"""Correlações conservadoras para planilhas e diagramas estruturados."""
from __future__ import annotations

import re


def _clean(value: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", value.lower()).strip()


def _tokens(value: str) -> set[str]:
    ignored = {"item", "descricao", "descrição", "modelo", "quantidade", "qtd", "unidade", "und", "servico", "serviço"}
    return {x for x in _clean(value).split() if len(x) > 2 and x not in ignored}


def _sheet_rows(doc: dict):
    lines = [line.strip() for line in doc.get("text", "").splitlines() if "|" in line]
    if not lines:
        return []
    header = [cell.strip() for cell in lines[0].split("|")]
    quantity_index = next((i for i, cell in enumerate(header) if re.search(r"quant|qtd", cell, re.I)), None)
    label_index = next((i for i, cell in enumerate(header) if re.search(r"descri|item|modelo|produto|servi", cell, re.I)), None)
    if quantity_index is None or label_index is None:
        return []
    rows = []
    for line in lines[1:]:
        cells = [cell.strip() for cell in line.split("|")]
        if max(quantity_index, label_index) >= len(cells):
            continue
        number = re.search(r"\b(\d+(?:[.,]\d+)?)\b", cells[quantity_index])
        if number and _tokens(cells[label_index]):
            rows.append((cells[label_index], number.group(1).replace(",", "."), line))
    return rows


def spreadsheet_text_conflicts(documents: list[dict]) -> list[dict]:
    """Confronta quantidade de item somente quando há cabeçalho explícito e contexto textual correspondente."""
    findings = []
    sheets = [doc for doc in documents if doc.get("ext") in (".xlsx", ".xls", ".csv")]
    texts = [doc for doc in documents if doc.get("ext") not in (".xlsx", ".xls", ".csv", ".png", ".jpg", ".jpeg", ".svg", ".drawio", ".bmp")]
    seen = set()
    for sheet in sheets:
        for label, quantity, row in _sheet_rows(sheet):
            label_tokens = _tokens(label)
            for text_doc in texts:
                body = text_doc.get("text", "")
                lower = body.lower()
                if not label_tokens or not all(token in lower for token in label_tokens):
                    continue
                position = min(lower.find(token) for token in label_tokens)
                context = re.sub(r"\s+", " ", body[max(0, position - 120):position + 320])
                numbers = {value.replace(",", ".") for value in re.findall(r"\b\d+(?:[.,]\d+)?\b", context)}
                if numbers and quantity not in numbers:
                    key = (sheet["relative_path"], text_doc["relative_path"], _clean(label), quantity)
                    if key in seen:
                        continue
                    seen.add(key)
                    findings.append({
                        "rule_id": "XREF-QTD", "title": "Quantitativo divergente entre planilha e documento textual",
                        "doc_origem": sheet["name"], "doc_path": sheet["relative_path"],
                        "loc": "Linha de planilha e trecho textual correlacionado", "cat": "Planilha / Quantitativo",
                        "tipo": "Inconsistência", "evid": "E3 (confronto direto entre planilha e texto)", "crit": "Alta", "prio": "P1",
                        "citacao": f"{sheet['name']}: {row} | {text_doc['name']}: {context}",
                        "fato": f"A planilha informa {quantity} para '{label}', mas o trecho correlacionado contém quantitativo diferente.",
                        "impacto": "O dimensionamento e a estimativa do escopo podem ser inconsistentes.",
                        "tipo_solucao": "Plano de Ação Estruturado", "proprietario": "Engenharia de Requisitos / Planejamento",
                    })
    return findings


def diagram_labels_without_textual_counterpart(documents: list[dict]) -> list[dict]:
    """Registra somente rótulos técnicos estruturados de SVG/DrawIO sem afirmar conflito visual."""
    findings = []
    visuals = [doc for doc in documents if doc.get("ext") in (".svg", ".drawio")]
    textual = " ".join(doc.get("text", "") for doc in documents if doc.get("ext") not in (".svg", ".drawio"))
    for visual in visuals:
        labels = set(re.findall(r"\b(?:VLAN\s*\d+|\d+(?:\.\d+)?\s*(?:GbE|Gbps|Mbps|Gb/s))\b", visual.get("text", ""), re.I))
        unmatched = sorted(label for label in labels if label.lower() not in textual.lower())
        if unmatched:
            findings.append({
                "rule_id": "DIA-ROTULO", "title": "Rótulos técnicos do diagrama sem contraparte textual localizada",
                "doc_origem": visual["name"], "doc_path": visual["relative_path"], "loc": "Rótulos extraídos de SVG/DrawIO",
                "cat": "Diagrama/Imagem", "tipo": "Lacuna", "evid": "E1 (rótulo estruturado extraído)", "crit": "Média", "prio": "P2",
                "citacao": ", ".join(unmatched),
                "fato": "Foram extraídos rótulos técnicos do diagrama sem menção correspondente no texto do lote.",
                "impacto": "A especificação textual não permite confirmar a semântica dos rótulos visuais.",
                "tipo_solucao": "Plano de Ação Estruturado", "proprietario": "Arquitetura / Engenharia",
            })
    return findings


def run(documents: list[dict], skills: list[str]) -> list[dict]:
    findings = []
    if "analisar-planilha" in skills:
        findings.extend(spreadsheet_text_conflicts(documents))
    if "analisar-diagramas" in skills:
        findings.extend(diagram_labels_without_textual_counterpart(documents))
    return findings
