"""
Módulo de Extração e Triangulação Pericial de Comentários e Anotações (FCA-ENG-001)

Suporta nativamente:
1. Documentos Microsoft Word (.docx):
   - Comentários de revisores (word/comments.xml) com mapeamento exato do texto âncora (w:commentRangeStart/End).
   - Revisões de texto / Track Changes (w:ins e w:del).
2. Documentos PDF (.pdf):
   - Anotações de página (/Annots): Highlights, Sticky Notes, FreeText, Underline, etc. via pypdf.

Metodologia de Triangulação Pericial (RTI):
- Comentários humanos NÃO são ground truth absoluto; são vetores heurísticos de investigação.
- Status possíveis: PENDENTE, PROCEDENTE, IMPROCEDENTE, DUVIDA.
"""

from __future__ import annotations

import os
import re
import csv
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Any, Optional

# Namespaces padrão do OpenXML para WordprocessingML
NS_WORD = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
}


def parse_iso_or_pdf_date(date_str: str) -> str:
    """Normaliza datas de PDF ('D:20261009143025-03\'00\'') ou ISO 8601 para formato padronizado."""
    if not date_str:
        return ""
    clean = re.sub(r"[^0-9]", "", str(date_str))
    if len(clean) >= 14:
        return f"{clean[0:4]}-{clean[4:6]}-{clean[6:8]} {clean[8:10]}:{clean[10:12]}:{clean[12:14]}"
    elif len(clean) >= 8:
        return f"{clean[0:4]}-{clean[4:6]}-{clean[6:8]}"
    return str(date_str)


def extract_docx_comments(docx_path: str) -> List[Dict[str, Any]]:
    """
    Extrai comentários e marcas de revisão de um arquivo .docx usando exclusivamente
    bibliotecas padrão do Python (zipfile + xml.etree.ElementTree).
    Vincula o comentário ao trecho exato de texto marcado no documento.
    """
    if not os.path.isfile(docx_path):
        return []

    comments_list: List[Dict[str, Any]] = []

    try:
        with zipfile.ZipFile(docx_path, "r") as z:
            names = z.namelist()
            
            # 1. Mapeia os textos âncoras em word/document.xml
            anchors_by_id: Dict[str, str] = {}
            track_changes: List[Dict[str, Any]] = []

            if "word/document.xml" in names:
                doc_xml_bytes = z.read("word/document.xml")
                root_doc = ET.fromstring(doc_xml_bytes)

                # Busca ranges de comentários ativos
                active_comments: Dict[str, List[str]] = {}

                # Varredura sequencial do documento
                for elem in root_doc.iter():
                    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                    
                    if tag == "commentRangeStart":
                        c_id = elem.attrib.get(f"{{{NS_WORD['w']}}}id") or elem.attrib.get("id")
                        if c_id:
                            active_comments[c_id] = []
                    
                    elif tag == "t" and elem.text:
                        # Adiciona o texto a todos os comentários ativos naquele ponto
                        for c_id in active_comments:
                            active_comments[c_id].append(elem.text)
                    
                    elif tag == "commentRangeEnd":
                        c_id = elem.attrib.get(f"{{{NS_WORD['w']}}}id") or elem.attrib.get("id")
                        if c_id and c_id in active_comments:
                            anchors_by_id[c_id] = "".join(active_comments.pop(c_id)).strip()

                    # Rastreamento de alterações (Track Changes)
                    elif tag in ("ins", "del"):
                        tc_id = elem.attrib.get(f"{{{NS_WORD['w']}}}id") or elem.attrib.get("id", "")
                        tc_author = elem.attrib.get(f"{{{NS_WORD['w']}}}author") or elem.attrib.get("author", "Autor Desconhecido")
                        tc_date = elem.attrib.get(f"{{{NS_WORD['w']}}}date") or elem.attrib.get("date", "")
                        
                        tc_text = "".join(elem.itertext()).strip()
                        if tc_text:
                            track_changes.append({
                                "id": tc_id,
                                "author": tc_author,
                                "date": tc_date,
                                "type": "Inserção (Track Changes)" if tag == "ins" else "Exclusão (Track Changes)",
                                "text": tc_text
                            })

            # 2. Lê comentários formais em word/comments.xml
            if "word/comments.xml" in names:
                comm_xml_bytes = z.read("word/comments.xml")
                root_comm = ET.fromstring(comm_xml_bytes)

                for c_elem in root_comm.findall(".//w:comment", NS_WORD):
                    c_id = c_elem.attrib.get(f"{{{NS_WORD['w']}}}id") or c_elem.attrib.get("id", "")
                    author = c_elem.attrib.get(f"{{{NS_WORD['w']}}}author") or c_elem.attrib.get("author", "Revisor Desconhecido")
                    date = c_elem.attrib.get(f"{{{NS_WORD['w']}}}date") or c_elem.attrib.get("date", "")
                    
                    # Concatena os parágrafos de texto do comentário
                    text_parts = []
                    for t_elem in c_elem.findall(".//w:t", NS_WORD):
                        if t_elem.text:
                            text_parts.append(t_elem.text)
                    
                    full_comment = " ".join(text_parts).strip()
                    if full_comment:
                        anchor_text = anchors_by_id.get(c_id, "")
                        comments_list.append({
                            "id_interno": c_id,
                            "tipo_anotacao": "Comentário Word",
                            "autor": author,
                            "data_hora": parse_iso_or_pdf_date(date),
                            "pagina_ou_secao": "Corpo do Documento",
                            "item_referenciado": anchor_text,
                            "comentario": full_comment,
                            "status_triangulacao": "PENDENTE",
                            "parecer_triangulacao": "",
                            "achado_id_associado": None
                        })

            # 3. Adiciona as marcas de revisão como anotações relevantes se houverem
            for tc in track_changes[:50]:  # Limita para não inflar desmedidamente
                comments_list.append({
                    "id_interno": tc["id"],
                    "tipo_anotacao": tc["type"],
                    "autor": tc["author"],
                    "data_hora": parse_iso_or_pdf_date(tc["date"]),
                    "pagina_ou_secao": "Revisão no Texto",
                    "item_referenciado": tc["text"],
                    "comentario": f"Alteração proposta: {tc['text']}",
                    "status_triangulacao": "PENDENTE",
                    "parecer_triangulacao": "",
                    "achado_id_associado": None
                })

    except Exception as e:
        # Erro de parsing em docx corrompido é tratado graciosamente
        return []

    return comments_list


def extract_pdf_annotations(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Extrai comentários, marcações de texto e sticky notes de arquivos PDF.
    Usa pypdf com fallback gracioso caso a biblioteca não esteja disponível.
    """
    if not os.path.isfile(pdf_path):
        return []

    try:
        import pypdf
    except ImportError:
        return []

    annotations: List[Dict[str, Any]] = []

    try:
        reader = pypdf.PdfReader(pdf_path)
        for page_idx, page in enumerate(reader.pages, start=1):
            page_annots = page.get("/Annots")
            if not page_annots:
                continue

            for annot_ref in page_annots:
                try:
                    annot = annot_ref.get_object()
                except Exception:
                    continue

                if not annot:
                    continue

                subtype = str(annot.get("/Subtype", "")).replace("/", "").strip()
                contents = annot.get("/Contents")
                author = annot.get("/T") or annot.get("/Title") or "Revisor Desconhecido"
                mod_date = annot.get("/M") or annot.get("/CreationDate") or ""
                rect = annot.get("/Rect")

                # Suporte a Rich Content (/RC)
                if not contents and "/RC" in annot:
                    raw_rc = str(annot.get("/RC", ""))
                    contents = re.sub(r"<[^>]+>", "", raw_rc)

                # Ignora widgets, campos de formulário e links vazios
                if subtype in ("Link", "Widget") and not contents:
                    continue

                text_comment = str(contents).strip() if contents else ""

                # Se houver comentário ou destaque
                if text_comment or subtype in ("Highlight", "Underline", "StrikeOut"):
                    rect_str = f"[{', '.join(str(round(float(x), 1)) for x in rect)}]" if rect else ""
                    
                    # Se for marcação sem texto explícito, registra indicação visual
                    if not text_comment:
                        text_comment = f"[Destaque visual {subtype} na página {page_idx}]"

                    annotations.append({
                        "id_interno": "",
                        "tipo_anotacao": f"PDF {subtype}",
                        "autor": str(author).strip(),
                        "data_hora": parse_iso_or_pdf_date(str(mod_date)),
                        "pagina_ou_secao": f"Pág. {page_idx}",
                        "coordenadas_rect": rect_str,
                        "item_referenciado": "",
                        "comentario": text_comment,
                        "status_triangulacao": "PENDENTE",
                        "parecer_triangulacao": "",
                        "achado_id_associado": None
                    })

    except Exception:
        return []

    return annotations


def extract_comments_from_file(filepath: str, relative_path: str = "") -> List[Dict[str, Any]]:
    """Extrai anotações de um arquivo suportado (.docx ou .pdf)."""
    ext = os.path.splitext(filepath)[1].lower()
    doc_name = os.path.basename(filepath)
    rel_path = relative_path or doc_name
    
    extracted: List[Dict[str, Any]] = []
    if ext == ".docx":
        extracted = extract_docx_comments(filepath)
    elif ext == ".pdf":
        extracted = extract_pdf_annotations(filepath)

    for item in extracted:
        item["documento"] = doc_name
        item["doc_path"] = rel_path

    return extracted


def extract_all_comments_from_lote(lote_dir: str) -> List[Dict[str, Any]]:
    """
    Varre todos os arquivos de um lote e extrai de forma unificada todos os comentários
    e notas adesivas, atribuindo IDs unívocos COM-001, COM-002, etc.
    """
    if not os.path.exists(lote_dir):
        return []

    all_comments: List[Dict[str, Any]] = []
    
    for dirpath, _, filenames in os.walk(lote_dir):
        for fname in sorted(filenames):
            if fname.startswith(".") or fname in ("README.md", "decisoes.yaml"):
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext in (".docx", ".pdf"):
                fpath = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(fpath, lote_dir)
                items = extract_comments_from_file(fpath, relative_path=rel_path)
                all_comments.extend(items)

    # Atribui IDs sequenciais padronizados
    for idx, c in enumerate(all_comments, 1):
        c["id_anotacao"] = f"COM-{idx:03d}"

    return all_comments


def export_comments_artifacts(comments: List[Dict[str, Any]], target_dir: str, base_name: str = "comentarios") -> Dict[str, str]:
    """
    Exporta comentários para a pasta de relatórios canônica (analise/.../relatorios/).
    NUNCA grava na pasta entrada/ para respeitar o princípio de baseline imutável.
    """
    os.makedirs(target_dir, exist_ok=True)
    paths = {}

    # 1. Exporta JSON
    json_path = os.path.join(target_dir, f"{base_name}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(comments, f, indent=2, ensure_ascii=False)
    paths["json"] = json_path

    # 2. Exporta CSV estruturado (delimitador ';' e UTF-8 com BOM para Excel)
    csv_path = os.path.join(target_dir, f"{base_name}.csv")
    fieldnames = [
        "id_anotacao",
        "documento",
        "pagina_ou_secao",
        "autor",
        "data_hora",
        "tipo_anotacao",
        "item_referenciado",
        "comentario",
        "status_triangulacao",
        "parecer_triangulacao",
        "achado_id_associado"
    ]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        if comments:
            writer.writerows(comments)
    paths["csv"] = csv_path

    return paths
