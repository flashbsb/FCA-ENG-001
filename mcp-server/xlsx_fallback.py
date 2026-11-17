"""Leitura mínima de XLSX com a biblioteca padrão quando openpyxl não está disponível."""
from __future__ import annotations

import re
import zipfile
import xml.etree.ElementTree as ET


NS = {
    "x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def _column_number(reference: str) -> int:
    letters = re.match(r"([A-Z]+)", reference or "")
    if not letters:
        return 0
    value = 0
    for letter in letters.group(1):
        value = value * 26 + ord(letter) - 64
    return value


def extract_xlsx_data(path: str) -> dict:
    try:
        with zipfile.ZipFile(path) as zf:
            shared = []
            if "xl/sharedStrings.xml" in zf.namelist():
                root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                shared = ["".join(node.itertext()) for node in root.findall("x:si", NS)]
            workbook = ET.fromstring(zf.read("xl/workbook.xml"))
            rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            relationship_map = {rel.attrib.get("Id"): rel.attrib.get("Target") for rel in rels.findall("rel:Relationship", NS)}
            output = {}
            for sheet in workbook.findall("x:sheets/x:sheet", NS):
                rid = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                target = relationship_map.get(rid, "")
                target = target.lstrip("/")
                member = target if target.startswith("xl/") else f"xl/{target}"
                if member not in zf.namelist():
                    continue
                root = ET.fromstring(zf.read(member))
                rows = []
                for row in root.findall(".//x:sheetData/x:row", NS):
                    cells = {}
                    max_column = 0
                    for cell in row.findall("x:c", NS):
                        column = _column_number(cell.attrib.get("r", ""))
                        max_column = max(max_column, column)
                        value_node = cell.find("x:v", NS)
                        value = value_node.text if value_node is not None and value_node.text is not None else ""
                        if cell.attrib.get("t") == "s" and value.isdigit() and int(value) < len(shared):
                            value = shared[int(value)]
                        elif cell.attrib.get("t") == "inlineStr":
                            value = "".join(cell.itertext())
                        cells[column] = value
                    if max_column:
                        values = [str(cells.get(i, "")) for i in range(1, max_column + 1)]
                        if any(value.strip() for value in values):
                            rows.append(values)
                if rows:
                    output[sheet.attrib.get("name", "Planilha")] = rows
            return output
    except Exception:
        return {}


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def extract_xlsx_comments(path: str) -> list[str]:
    """Extrai comentários tradicionais e encadeados (threadedComments) de .xlsx como contexto não-normativo."""
    comments: list[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
            names = sorted(zf.namelist())
            for member in names:
                if re.fullmatch(r"xl/comments\d*\.xml", member):
                    try:
                        root = ET.fromstring(zf.read(member))
                        authors = [
                            "".join(el.itertext()).strip()
                            for el in root.iter()
                            if _local_tag(el.tag) == "author"
                        ]
                        for cm in root.iter():
                            if _local_tag(cm.tag) != "comment":
                                continue
                            ref = (cm.attrib.get("ref") or "?").strip()
                            aid_raw = cm.attrib.get("authorId", "")
                            author = (
                                authors[int(aid_raw)]
                                if aid_raw.isdigit() and int(aid_raw) < len(authors) and authors[int(aid_raw)]
                                else "Revisor"
                            )
                            text_nodes = [
                                "".join(child.itertext())
                                for child in cm
                                if _local_tag(child.tag) == "text"
                            ]
                            txt = re.sub(r"\s+", " ", " ".join(text_nodes) or "".join(cm.itertext())).strip()
                            if txt:
                                comments.append(
                                    f"[COMENTÁRIO DE REVISÃO — NÃO FONTE DE VERDADE | Planilha XLSX · Célula {ref} ({author})] {txt}"
                                )
                    except Exception:
                        continue
                elif re.fullmatch(r"xl/threadedComments/threadedComment\d*\.xml", member):
                    try:
                        root = ET.fromstring(zf.read(member))
                        for tc in root.iter():
                            if _local_tag(tc.tag) != "threadedComment":
                                continue
                            ref = (tc.attrib.get("ref") or "?").strip()
                            text_nodes = [
                                "".join(child.itertext())
                                for child in tc
                                if _local_tag(child.tag) == "text"
                            ]
                            txt = re.sub(r"\s+", " ", " ".join(text_nodes) or "".join(tc.itertext())).strip()
                            if txt:
                                comments.append(
                                    f"[COMENTÁRIO DE REVISÃO — NÃO FONTE DE VERDADE | Planilha XLSX · Célula {ref} (Threaded Comment)] {txt}"
                                )
                    except Exception:
                        continue
    except Exception:
        return []
    return comments
