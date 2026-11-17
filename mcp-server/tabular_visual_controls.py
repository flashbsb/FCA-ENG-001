"""Correlações conservadoras para planilhas e diagramas estruturados."""
from __future__ import annotations

import re

from audit_pipeline import strip_non_normative_comments

SPREADSHEET_EXTS = (".xlsx", ".xls", ".ods", ".csv", ".tsv")
VISUAL_NON_TEXT_EXTS = (".png", ".jpg", ".jpeg", ".svg", ".drawio", ".vsdx", ".bmp", ".gif", ".webp", ".tif", ".tiff")


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
    sheets = [doc for doc in documents if doc.get("ext") in SPREADSHEET_EXTS]
    texts = [doc for doc in documents if doc.get("ext") not in SPREADSHEET_EXTS + VISUAL_NON_TEXT_EXTS]
    seen = set()
    for sheet in sheets:
        sheet_norm = {**sheet, "text": strip_non_normative_comments(sheet.get("text", ""))}
        for label, quantity, row in _sheet_rows(sheet_norm):
            label_tokens = _tokens(label)
            for text_doc in texts:
                body = strip_non_normative_comments(text_doc.get("text", ""))
                lower = body.lower()
                if not label_tokens or not all(token in lower for token in label_tokens):
                    continue
                position = min(lower.find(token) for token in label_tokens)
                context = re.sub(r"\s+", " ", body[max(0, position - 120):position + 320]).strip()
                numbers = {value.replace(",", ".") for value in re.findall(r"\b\d+(?:[.,]\d+)?\b", context)}
                if numbers and quantity not in numbers:
                    key = (sheet["relative_path"], text_doc["relative_path"], _clean(label), quantity)
                    if key in seen:
                        continue
                    seen.add(key)
                    sheet_text = sheet.get("text", "")
                    row_pos = sheet_text.find(row)
                    sheet_line = (sheet_text[:row_pos].count("\n") + 1) if row_pos >= 0 else 1
                    text_line = body[:position].count("\n") + 1
                    sheet_loc = f"Linha {sheet_line}"
                    text_loc = f"Linha {text_line}"
                    findings.append({
                        "rule_id": "XREF-QTD", "title": "Quantitativo divergente entre planilha e documento textual",
                        "doc_origem": sheet["name"], "doc_path": sheet["relative_path"],
                        "loc": f"{sheet_loc} (confronto com {text_doc['name']} {text_loc})", "cat": "Planilha / Quantitativo",
                        "tipo": "Inconsistência", "evid": "E3 (confronto direto entre planilha e texto)", "crit": "Alta", "prio": "P1",
                        "citacao": f"{sheet['name']}: {row} | {text_doc['name']}: {context}",
                        "fato": f"A planilha informa {quantity} para '{label}', mas o trecho correlacionado contém quantitativo diferente.",
                        "impacto": "O dimensionamento e a estimativa do escopo podem ser inconsistentes.",
                        "tipo_solucao": "Plano de Ação Estruturado", "proprietario": "Engenharia de Requisitos / Planejamento",
                        "evidence_sources": [
                            {
                                "document_path": sheet["relative_path"],
                                "document_name": sheet["name"],
                                "location": sheet_loc,
                                "quote": row,
                                "sha256": sheet.get("sha256", ""),
                            },
                            {
                                "document_path": text_doc["relative_path"],
                                "document_name": text_doc["name"],
                                "location": text_loc,
                                "quote": context,
                                "sha256": text_doc.get("sha256", ""),
                            },
                        ],
                    })
    return findings


def diagram_labels_without_textual_counterpart(documents: list[dict]) -> list[dict]:
    """Registra somente rótulos técnicos estruturados de SVG/DrawIO/VSDX sem afirmar conflito visual."""
    findings = []
    visuals = [doc for doc in documents if doc.get("ext") in (".svg", ".drawio", ".vsdx")]
    textual = " ".join(strip_non_normative_comments(doc.get("text", "")) for doc in documents if doc.get("ext") not in (".svg", ".drawio", ".vsdx"))
    for visual in visuals:
        labels = set(re.findall(r"\b(?:VLAN\s*\d+|\d+(?:\.\d+)?\s*(?:GbE|Gbps|Mbps|Gb/s))\b", visual.get("text", ""), re.I))
        unmatched = sorted(label for label in labels if label.lower() not in textual.lower())
        if unmatched:
            findings.append({
                "rule_id": "DIA-ROTULO", "title": "Rótulos técnicos do diagrama sem contraparte textual localizada",
                "doc_origem": visual["name"], "doc_path": visual["relative_path"], "loc": "Rótulos extraídos de diagrama estruturado",
                "cat": "Diagrama/Imagem", "tipo": "Lacuna", "evid": "E1 (rótulo estruturado extraído)", "crit": "Média", "prio": "P2",
                "citacao": ", ".join(unmatched),
                "fato": "Foram extraídos rótulos técnicos do diagrama sem menção correspondente no texto do lote.",
                "impacto": "A especificação textual não permite confirmar a semântica dos rótulos visuais.",
                "tipo_solucao": "Plano de Ação Estruturado", "proprietario": "Arquitetura / Engenharia",
            })
    return findings


def spreadsheet_formula_or_error_cells(documents: list[dict]) -> list[dict]:
    """Detecta erros literais de fórmula/referência (#REF!, #DIV/0!, #VALUE!, #NAME?, #NUM!, #NULL!, Err:5) em planilhas."""
    findings = []
    sheets = [doc for doc in documents if doc.get("ext") in SPREADSHEET_EXTS]
    error_rx = re.compile(r"(?:#REF!|#DIV/0!|#VALUE!|#NAME\?|#NUM!|#NULL!|\bErr:5\d*)")
    seen = set()

    for sheet in sheets:
        body = strip_non_normative_comments(sheet.get("text", ""))
        for line_no, raw_line in enumerate(body.splitlines(), 1):
            m = error_rx.search(raw_line)
            if not m:
                continue
            token = m.group(0)
            key = (sheet.get("relative_path", sheet.get("name")), line_no, token)
            if key in seen:
                continue
            seen.add(key)
            line_clean = raw_line.strip()
            if len(line_clean) > 360:
                start = max(0, m.start() - 100)
                quote = raw_line[start:start + 360].strip()
            else:
                quote = line_clean
            loc_str = f"Linha {line_no}"
            findings.append({
                "rule_id": "XLS-ERR-001",
                "title": "Célula com erro de fórmula ou referência quebrada na planilha",
                "doc_origem": sheet["name"],
                "doc_path": sheet["relative_path"],
                "loc": loc_str,
                "cat": "Planilha / Quantitativo",
                "tipo": "Erro",
                "evid": "E2 (célula com erro literal extraída da planilha)",
                "crit": "Alta",
                "prio": "P1",
                "citacao": quote,
                "fato": f"A planilha exibe erro literal de fórmula ({token}) na {loc_str}.",
                "impacto": "Totais, quantitativos ou precificações dependentes dessa célula tornam-se inválidos ou não auditáveis.",
                "solucao": "Corrigir a fórmula ou referência quebrada na planilha de origem e reexportar a baseline.",
                "tipo_solucao": "Plano de Ação Estruturado",
                "proprietario": "Engenharia de Requisitos / Orçamentação",
                "evidence_sources": [{
                    "document_path": sheet["relative_path"],
                    "document_name": sheet["name"],
                    "location": loc_str,
                    "quote": quote,
                    "sha256": sheet.get("sha256", ""),
                }],
                "referencias": [{
                    "titulo": "FCA-ENG-001 — Controle Tabular de Fórmulas (XLS-ERR-001)",
                    "url": "",
                    "nota": f"Token literal '{token}' extraído da planilha na {loc_str}.",
                }],
            })
    return findings


def _parse_spreadsheet_number(cell: str) -> float | None:
    """Converte representação numérica PT-BR ou EN-US de célula em float, rejeitando strings não numéricas."""
    s = re.sub(r"^(?:R\$|US\$|\$|€)\s*", "", (cell or "").strip(), flags=re.I)
    if not s or not re.fullmatch(r"-?\d+(?:[.,]\d+)*", s):
        return None
    try:
        if "." in s and "," in s:
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "," in s:
            if s.count(",") > 1:
                s = s.replace(",", "")
            else:
                s = s.replace(",", ".")
        elif s.count(".") > 1:
            s = s.replace(".", "")
        return float(s)
    except ValueError:
        return None


def spreadsheet_total_sum_mismatches(documents: list[dict]) -> list[dict]:
    """Compara linhas explícitas de Total/Soma com a soma aritmética das parcelas do mesmo bloco."""
    findings = []
    sheets = [doc for doc in documents if doc.get("ext") in SPREADSHEET_EXTS]
    numeric_header_rx = re.compile(
        r"\b(?:quantidade|qtd|valor|total|subtotal|pre[çc]o|custo|capex|opex|mensal|anual)\b",
        re.I,
    )
    subtotal_rx = re.compile(r"^\s*subtotal\b", re.I)
    total_rx = re.compile(r"^\s*(?:total(?:\s+geral)?|soma|somatório|somatorio)\b", re.I)
    cell_error_rx = re.compile(r"(?:#REF!|#DIV/0!|#VALUE!|#NAME\?|#NUM!|#NULL!|\bErr:5\d*)")

    for sheet in sheets:
        body = strip_non_normative_comments(sheet.get("text", ""))
        headers = None
        numeric_cols: list[int] = []
        parcel_rows: list[tuple[int, str, list[str]]] = []

        for line_no, raw_line in enumerate(body.splitlines(), 1):
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("[ABA:"):
                headers = None
                numeric_cols = []
                parcel_rows = []
                continue

            sep = "|" if "|" in raw_line else (";" if ";" in raw_line else None)
            if not sep:
                headers = None
                numeric_cols = []
                parcel_rows = []
                continue

            cells = [c.strip() for c in raw_line.split(sep)]
            if headers is None:
                cols = [idx for idx, h in enumerate(cells) if numeric_header_rx.search(h)]
                if cols:
                    headers = cells
                    numeric_cols = cols
                    parcel_rows = []
                continue

            if cells == headers:
                parcel_rows = []
                continue

            first_label = cells[0] if cells else ""
            if not first_label and len(cells) > 1:
                first_label = cells[1]

            if subtotal_rx.match(first_label):
                parcel_rows = []
                continue

            if total_rx.match(first_label):
                if len(parcel_rows) >= 2:
                    for col_idx in numeric_cols:
                        if col_idx >= len(cells):
                            continue
                        declared = _parse_spreadsheet_number(cells[col_idx])
                        if declared is None:
                            continue
                        parcel_vals = []
                        has_cell_error = False
                        for p_line_no, p_raw, p_cells in parcel_rows:
                            if col_idx >= len(p_cells):
                                continue
                            cell_txt = p_cells[col_idx]
                            if cell_error_rx.search(cell_txt):
                                has_cell_error = True
                                break
                            num = _parse_spreadsheet_number(cell_txt)
                            if num is not None:
                                parcel_vals.append((p_line_no, p_raw.strip(), num))
                        if has_cell_error or len(parcel_vals) < 2:
                            continue
                        calc_sum = round(sum(v[2] for v in parcel_vals), 6)
                        if abs(declared - calc_sum) > 0.05:
                            first_p_line, first_p_quote, _ = parcel_vals[0]
                            total_quote = stripped
                            col_name = headers[col_idx] if col_idx < len(headers) else f"Coluna {col_idx + 1}"
                            loc_str = f"Linha {line_no} (confronto com Linha {first_p_line})"
                            findings.append({
                                "rule_id": "XLS-SUM-001",
                                "title": "Divergência aritmética em linha de totalização da planilha",
                                "doc_origem": sheet["name"],
                                "doc_path": sheet["relative_path"],
                                "loc": loc_str,
                                "cat": "Planilha / Quantitativo",
                                "tipo": "Erro",
                                "evid": "E3 (confronto aritmético direto entre parcelas e total na planilha)",
                                "crit": "Alta",
                                "prio": "P1",
                                "citacao": f"{first_p_quote} | {total_quote}",
                                "fato": (
                                    f"Na coluna '{col_name}', a linha de totalização declara {declared:g}, "
                                    f"enquanto a soma das {len(parcel_vals)} parcelas anteriores totaliza {calc_sum:g}."
                                ),
                                "impacto": "Quantitativos ou valores financeiros consolidados estão em desacordo com as parcelas discriminadas.",
                                "solucao": "Revisar a fórmula de totalização da coluna indicada na planilha e republicar a baseline.",
                                "tipo_solucao": "Plano de Ação Estruturado",
                                "proprietario": "Engenharia de Requisitos / Orçamentação",
                                "evidence_sources": [
                                    {
                                        "document_path": sheet["relative_path"],
                                        "document_name": sheet["name"],
                                        "location": f"Linha {first_p_line}",
                                        "quote": first_p_quote,
                                        "sha256": sheet.get("sha256", ""),
                                    },
                                    {
                                        "document_path": sheet["relative_path"],
                                        "document_name": sheet["name"],
                                        "location": f"Linha {line_no}",
                                        "quote": total_quote,
                                        "sha256": sheet.get("sha256", ""),
                                    },
                                ],
                                "referencias": [{
                                    "titulo": "FCA-ENG-001 — Controle Aritmético Tabular (XLS-SUM-001)",
                                    "url": "",
                                    "nota": f"Soma apurada ({calc_sum:g}) difere do total declarado ({declared:g}) na coluna '{col_name}'.",
                                }],
                            })
                parcel_rows = []
                continue

            parcel_rows.append((line_no, raw_line, cells))
    return findings


def run(documents: list[dict], skills: list[str]) -> list[dict]:
    findings = []
    if "analisar-planilha" in skills:
        findings.extend(spreadsheet_text_conflicts(documents))
        findings.extend(spreadsheet_formula_or_error_cells(documents))
        findings.extend(spreadsheet_total_sum_mismatches(documents))
    if "analisar-diagramas" in skills:
        findings.extend(diagram_labels_without_textual_counterpart(documents))
    return findings
