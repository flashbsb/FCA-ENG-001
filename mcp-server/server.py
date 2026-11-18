#!/usr/bin/env python3
"""
Servidor MCP (Model Context Protocol) — Framework FCA-ENG-001 (Revisão Técnica Independente)
Protocolo MCP JSON-RPC 2.0 sobre stdio — zero dependências externas obrigatórias (Python 3.9+).
Suporta: .docx, .pdf, .xlsx, .csv, .md, .txt, .json, .yaml, .png, .jpg, .svg
Analisa lotes aninhados: subpastas de 1º nível em entrada/ = um lote completo.
"""

import os
import sys
import json
import html
import shutil
import hashlib
import zipfile
import datetime
import re
import subprocess
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from functools import lru_cache

_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

import html_compiler
import audit_pipeline
from audit_pipeline import (
    sanitize_batch_isolation,
    clean_unicode_text,
    strip_non_normative_comments,
    REVIEW_COMMENT_PREFIX,
)
import specialized_controls
import cross_document
import tabular_visual_controls
import advanced_specialized_controls
import visual_pipeline
import semantic_pipeline
import comments_extractor
import schemas
from xlsx_fallback import (
    extract_xlsx_data as extract_xlsx_data_fallback,
    extract_xlsx_comments,
)



# ─────────────────────────────────────────────
# Utilitários Gerais
# ─────────────────────────────────────────────

def calculate_file_hash(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def _extract_value(text: str, pattern: str, fallback: str = "—") -> str:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1).strip() if m else fallback


def get_workspace_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _is_valid_analysis_identifier(ident: str) -> bool:
    """Valida se o identificador ou caminho relativo de análise é seguro e válido."""
    if not ident or not isinstance(ident, str):
        return False
    clean = ident.replace('\\', '/').strip('/')
    parts = clean.split('/')
    if not parts or len(parts) > 5:
        return False
    for p in parts:
        if (
            not p
            or p != p.strip()
            or p in ('.', '..')
            or any(ord(ch) < 32 for ch in p)
            or not re.fullmatch(r"[\w .()\-]+", p, flags=re.UNICODE)
        ):
            return False
    return True


def _extract_batch_name(timestamp: str, rel_path: str = None) -> str:
    """Extrai o nome do lote a partir do caminho relativo ou do sufixo do timestamp."""
    ref = (rel_path or timestamp or "").strip().replace('\\', '/').strip('/')
    parts = [p for p in ref.split('/') if p]
    if len(parts) >= 2:
        return parts[0]
    leaf = parts[-1] if parts else ""
    sub = leaf.split("_", 2)
    return sub[2] if len(sub) > 2 else leaf


def _resolve_analysis_dirs(root: str, timestamp_or_path: str = None) -> tuple:
    """
    Resolve os diretórios da análise com suporte a múltiplas profundidades:
    1. analise/<lote>/<version>/<timestamp>/
    2. analise/<lote>/<timestamp>/
    3. analise/<timestamp>/
    Ou via busca recursiva pelo timestamp puro da folha.
    Retorna: (analysis_dir, relatorios_dir, entrada_dir, rel_path)
    """
    analise_root = os.path.join(root, 'analise')
    if timestamp_or_path:
        clean = timestamp_or_path.strip().replace('\\', '/')
        direct_path = os.path.join(analise_root, clean)
        direct_rel = os.path.join(direct_path, 'relatorios')
        if os.path.isdir(direct_rel):
            return direct_path, direct_rel, os.path.join(direct_path, 'entrada'), clean
        
        # Busca recursiva se fornecido apenas o timestamp da folha ou caminho parcial
        target_leaf = clean.split('/')[-1]
        for dirpath, dirnames, _ in os.walk(analise_root):
            if os.path.basename(dirpath) == target_leaf and 'relatorios' in dirnames:
                candidate_rel = os.path.join(dirpath, 'relatorios')
                if os.path.isdir(candidate_rel):
                    rel_p = os.path.relpath(dirpath, analise_root).replace('\\', '/')
                    return dirpath, candidate_rel, os.path.join(dirpath, 'entrada'), rel_p

        # Fallback para o caminho direto esperado
        return direct_path, direct_rel, os.path.join(direct_path, 'entrada'), clean

    # Se nenhum timestamp fornecido, encontra o mais recente
    found = []
    if os.path.exists(analise_root):
        for dirpath, dirnames, filenames in os.walk(analise_root):
            if os.path.basename(dirpath) == 'relatorios' and ('dados_analise.json' in filenames or 'index.html' in filenames):
                run_dir = os.path.dirname(dirpath)
                rel_p = os.path.relpath(run_dir, analise_root).replace('\\', '/')
                mtime = os.path.getmtime(dirpath)
                found.append((mtime, run_dir, dirpath, os.path.join(run_dir, 'entrada'), rel_p))
    if found:
        found.sort(key=lambda x: x[0], reverse=True)
        return found[0][1], found[0][2], found[0][3], found[0][4]

    def_dir = os.path.join(analise_root, 'default')
    return def_dir, os.path.join(def_dir, 'relatorios'), os.path.join(def_dir, 'entrada'), 'default'


def ensure_infrastructure(root: str = None):
    """Garante que entrada/ e analise/ existam com README e .gitkeep."""
    if root is None:
        root = get_workspace_root()

    for folder, readme_content in [
        ('entrada', "# Pasta de Entrada (`entrada/`)\n\nInsira aqui as subpastas de lotes para análise técnica.\n\n"
                    "## Estrutura esperada\n```\nentrada/\n  01_Nome_do_Lote/\n    documento.docx\n    anexo.pdf\n    planilha.xlsx\n```\n"),
        ('analise', "# Pasta de Análise (`analise/`)\n\nHistórico local de análises técnicas por timestamp.\n\n"
                    "> **Nota de Segurança:** Esta pasta é ignorada pelo `.gitignore`.\n")
    ]:
        path = os.path.join(root, folder)
        os.makedirs(path, exist_ok=True)
        readme = os.path.join(path, 'README.md')
        gitkeep = os.path.join(path, '.gitkeep')
        if not os.path.exists(readme):
            with open(readme, 'w', encoding='utf-8') as f:
                f.write(readme_content)
        if not os.path.exists(gitkeep):
            with open(gitkeep, 'w') as f:
                f.write('')


# ─────────────────────────────────────────────
# Extratores de Conteúdo por Formato
# ─────────────────────────────────────────────

def _read_text_with_fallback(fpath: str, max_chars: int = None) -> str:
    """Lê arquivo textual tentando UTF-8 e fazendo fallback para cp1252/latin-1."""
    try:
        with open(fpath, 'rb') as f:
            raw = f.read(max_chars * 4 if max_chars else -1)
    except Exception:
        return ''
    for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            text = raw.decode(enc)
            return text[:max_chars] if max_chars else text
        except UnicodeDecodeError:
            continue
    text = raw.decode('utf-8', errors='replace')
    return text[:max_chars] if max_chars else text


def _extract_docx_lines(fpath: str) -> tuple[list[str], list[str]]:
    """Extrai linhas de .docx (parágrafos, tabelas, listas e cabeçalhos/rodapés)."""
    w_ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    ns = {'w': w_ns}
    plain_lines = []
    located_lines = []

    with zipfile.ZipFile(fpath) as z:
        abstract_fmts = {}
        num_map = {}
        if 'word/numbering.xml' in z.namelist():
            try:
                num_tree = ET.fromstring(z.read('word/numbering.xml'))
                for abs_el in num_tree.findall('w:abstractNum', ns):
                    abs_id = abs_el.get(f'{{{w_ns}}}abstractNumId', '')
                    lvls = {}
                    for lvl_el in abs_el.findall('w:lvl', ns):
                        ilvl_str = lvl_el.get(f'{{{w_ns}}}ilvl', '')
                        fmt_el = lvl_el.find('w:numFmt', ns)
                        if ilvl_str.isdigit() and fmt_el is not None:
                            lvls[int(ilvl_str)] = fmt_el.get(f'{{{w_ns}}}val', '')
                    if abs_id:
                        abstract_fmts[abs_id] = lvls
                for num_el in num_tree.findall('w:num', ns):
                    nid = num_el.get(f'{{{w_ns}}}numId', '')
                    abs_ref = num_el.find('w:abstractNumId', ns)
                    if nid and abs_ref is not None:
                        num_map[nid] = abs_ref.get(f'{{{w_ns}}}val', '')
            except Exception:
                pass

        counters = {}
        para_idx = 0
        tbl_idx = 0

        def _para_text(p_el) -> str:
            txt = ''.join(r.text or '' for r in p_el.findall('.//w:t', ns)).strip()
            if not txt:
                return ''
            num_pr = p_el.find('./w:pPr/w:numPr', ns)
            if num_pr is not None:
                nid_el = num_pr.find('w:numId', ns)
                ilvl_el = num_pr.find('w:ilvl', ns)
                nid = nid_el.get(f'{{{w_ns}}}val', '') if nid_el is not None else ''
                ilvl_raw = ilvl_el.get(f'{{{w_ns}}}val', '0') if ilvl_el is not None else '0'
                ilvl = int(ilvl_raw) if ilvl_raw.isdigit() else 0
                if nid and nid != '0':
                    fmt = abstract_fmts.get(num_map.get(nid, ''), {}).get(ilvl, '')
                    if fmt == 'bullet' and not txt.startswith(('-', '•', '*')):
                        txt = f'- {txt}'
                    elif fmt == 'decimal':
                        counters[(nid, ilvl)] = counters.get((nid, ilvl), 0) + 1
                        for k in [k for k in counters if k[0] == nid and k[1] > ilvl]:
                            del counters[k]
                        prefix = '.'.join(str(counters.get((nid, lvl), 1)) for lvl in range(ilvl + 1))
                        if not re.match(r'^\d+(?:\.\d+)*[\.\s)]', txt):
                            txt = f'{prefix} {txt}'
            return txt

        def _walk_container(container, section_tag: str = None):
            nonlocal para_idx, tbl_idx
            for child in list(container):
                if child.tag == f'{{{w_ns}}}p':
                    txt = _para_text(child)
                    if txt:
                        if section_tag:
                            plain_lines.append(txt)
                            located_lines.append(f'[{section_tag}] {txt}')
                        else:
                            para_idx += 1
                            plain_lines.append(txt)
                            located_lines.append(f'[Parágrafo {para_idx}] {txt}')
                elif child.tag == f'{{{w_ns}}}tbl':
                    tbl_idx += 1
                    for row_idx, tr in enumerate(child.findall('./w:tr', ns), 1):
                        cells = []
                        for tc in tr.findall('./w:tc', ns):
                            c_parts = [''.join(r.text or '' for r in p.findall('.//w:t', ns)).strip() for p in tc.findall('.//w:p', ns)]
                            cells.append(' '.join(cp for cp in c_parts if cp))
                        if any(c.strip() for c in cells):
                            row_line = ' | '.join(cells)
                            plain_lines.append(row_line)
                            tag = section_tag or f'Tabela {tbl_idx} · linha {row_idx}'
                            located_lines.append(f'[{tag}] {row_line}')
                else:
                    _walk_container(child, section_tag=section_tag)

        doc_xml = z.read('word/document.xml').decode('utf-8', errors='ignore')
        tree = ET.fromstring(doc_xml)
        body = tree.find('w:body', ns)
        _walk_container(body if body is not None else tree)

        hf_names = sorted(n for n in z.namelist() if re.fullmatch(r'word/(?:header|footer)\d+\.xml', n))
        for hf_name in hf_names:
            try:
                hf_xml = z.read(hf_name).decode('utf-8', errors='ignore')
                hf_tree = ET.fromstring(hf_xml)
                _walk_container(hf_tree, section_tag=f'Cabeçalho/Rodapé {os.path.basename(hf_name)}')
            except Exception:
                continue

        # Extrai alterações rastreadas (Track Changes w:ins / w:del) como contexto não-normativo
        for tag_local, label_tc, text_tag in (('ins', 'Inserção', 't'), ('del', 'Exclusão', 'delText')):
            for tc_el in tree.findall(f'.//w:{tag_local}', ns):
                tc_txt = ' '.join((t.text or '').strip() for t in tc_el.findall(f'.//w:{text_tag}', ns) if (t.text or '').strip())
                tc_txt = re.sub(r'\s+', ' ', tc_txt).strip()
                if not tc_txt:
                    continue
                author = tc_el.get(f'{{{w_ns}}}author', '') or 'Autor não informado'
                date_val = tc_el.get(f'{{{w_ns}}}date', '')
                who = f'{author}, {date_val[:10]}' if date_val else author
                comment_line = f'{REVIEW_COMMENT_PREFIX} | Track Changes DOCX ({label_tc} por {who})] {tc_txt}'
                plain_lines.append(comment_line)
                located_lines.append(comment_line)

        # Extrai balões de comentários (word/comments.xml) como contexto não-normativo
        if 'word/comments.xml' in z.namelist():
            try:
                c_xml = z.read('word/comments.xml').decode('utf-8', errors='ignore')
                c_tree = ET.fromstring(c_xml)
                for c_el in c_tree.findall('.//w:comment', ns):
                    cid = c_el.get(f'{{{w_ns}}}id', '') or '?'
                    author = c_el.get(f'{{{w_ns}}}author', '') or 'Revisor'
                    date_val = c_el.get(f'{{{w_ns}}}date', '')
                    who = f'{author}, {date_val[:10]}' if date_val else author
                    p_texts = [''.join(t.text or '' for t in p.findall('.//w:t', ns)).strip() for p in c_el.findall('.//w:p', ns)]
                    c_txt = ' '.join(pt for pt in p_texts if pt) or ''.join(t.text or '' for t in c_el.findall('.//w:t', ns)).strip()
                    c_txt = re.sub(r'\s+', ' ', c_txt).strip()
                    if c_txt:
                        comment_line = f'{REVIEW_COMMENT_PREFIX} | Comentário DOCX #{cid} ({who})] {c_txt}'
                        plain_lines.append(comment_line)
                        located_lines.append(comment_line)
            except Exception:
                pass

    return plain_lines, located_lines


def extract_docx_text(fpath: str) -> str:
    """Extrai texto de .docx preservando estrutura de parágrafos, tabelas e cabeçalhos/rodapés."""
    try:
        plain_lines, _ = _extract_docx_lines(fpath)
        return '\n'.join(plain_lines)
    except Exception:
        # Fallback: strip all XML tags
        try:
            with zipfile.ZipFile(fpath) as z:
                doc_xml = z.read('word/document.xml').decode('utf-8', errors='ignore')
            return re.sub(r'<[^>]+>', ' ', doc_xml)
        except Exception:
            return ''


def _extract_pdf_annotations(page, page_num: int) -> list[str]:
    """Extrai comentários e anotações de revisão (/Annots) de uma página PDF sem tratá-los como norma."""
    notes = []
    try:
        annots = page.get('/Annots') or getattr(page, 'annotations', None) or []
        for ref in annots:
            try:
                obj = ref.get_object() if hasattr(ref, 'get_object') else ref
                if not isinstance(obj, dict):
                    continue
                subtype = str(obj.get('/Subtype', ''))
                if subtype not in ('/Text', '/FreeText', '/Highlight', '/Underline', '/StrikeOut', '/Squiggly', '/Popup', ''):
                    continue
                contents = re.sub(r'\s+', ' ', str(obj.get('/Contents', '') or '')).strip()
                if not contents:
                    continue
                author = re.sub(r'\s+', ' ', str(obj.get('/T', '') or '')).strip() or 'Revisor'
                notes.append(f'{REVIEW_COMMENT_PREFIX} | Anotação PDF Página {page_num} ({author})] {contents}')
            except Exception:
                continue
    except Exception:
        pass
    return notes


def extract_pdf_text(fpath: str) -> str:
    """Extrai texto e anotações de revisão de .pdf usando pypdf se disponível."""
    try:
        import pypdf
        reader = pypdf.PdfReader(fpath)
        pages = []
        for page_num, page in enumerate(reader.pages, 1):
            text = page.extract_text()
            if text:
                pages.append(text)
            pages.extend(_extract_pdf_annotations(page, page_num))
        return '\n'.join(pages)
    except ImportError:
        return ''
    except Exception:
        return ''


def _read_xls_legacy(fpath: str) -> dict:
    """Tenta ler .xls legado via xlrd ou conversão headless pelo LibreOffice quando disponível."""
    try:
        import xlrd
        wb = xlrd.open_workbook(fpath)
        sheets = {}
        for name in wb.sheet_names():
            ws = wb.sheet_by_name(name)
            rows = []
            for r_idx in range(min(ws.nrows, 1000)):
                row_data = [str(ws.cell_value(r_idx, c_idx)) if ws.cell_value(r_idx, c_idx) is not None else '' for c_idx in range(ws.ncols)]
                if any(c.strip() for c in row_data):
                    rows.append(row_data)
            if rows:
                sheets[name] = rows
        return sheets
    except Exception:
        pass
    soffice = shutil.which('libreoffice') or shutil.which('soffice')
    if soffice:
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                res = subprocess.run(
                    [soffice, '--headless', '--convert-to', 'xlsx', '--outdir', tmp_dir, fpath],
                    capture_output=True, text=True, timeout=30, check=False,
                )
                if res.returncode == 0:
                    converted = next((os.path.join(tmp_dir, fn) for fn in os.listdir(tmp_dir) if fn.lower().endswith('.xlsx')), None)
                    if converted:
                        return extract_xlsx_data(converted)
        except Exception:
            pass
    return {}


def extract_xlsx_data(fpath: str) -> dict:
    """Extrai dados de .xlsx (ou .xls via xlrd/LibreOffice) usando openpyxl ou fallback XML."""
    if os.path.splitext(fpath)[1].lower() == '.xls':
        return _read_xls_legacy(fpath)
    try:
        import openpyxl
        wb = openpyxl.load_workbook(fpath, read_only=True, data_only=True)
        sheets = {}
        for name in wb.sheetnames:
            ws = wb[name]
            rows = []
            for row in ws.iter_rows(max_row=1000, values_only=True):
                row_data = [str(c) if c is not None else '' for c in row]
                if any(c.strip() for c in row_data):
                    rows.append(row_data)
            if rows:
                sheets[name] = rows
        wb.close()
        return sheets
    except ImportError:
        return extract_xlsx_data_fallback(fpath)
    except Exception:
        return extract_xlsx_data_fallback(fpath)


def extract_csv_text(fpath: str) -> str:
    """Lê CSV como texto com fallback de codificação para cp1252/latin-1."""
    return _read_text_with_fallback(fpath, max_chars=200000)


def extract_tsv_text(fpath: str) -> str:
    """Lê TSV com fallback de codificação convertendo tabulações em separador tabular '|'."""
    raw = _read_text_with_fallback(fpath, max_chars=200000)
    return '\n'.join(' | '.join(col.strip() for col in line.split('\t')) for line in raw.splitlines())


def extract_text_file(fpath: str) -> str:
    """Lê .md, .txt, .json, .yaml como texto com fallback de codificação."""
    return _read_text_with_fallback(fpath, max_chars=200000)


def _xml_local(tag: str) -> str:
    return tag.rsplit('}', 1)[-1] if '}' in tag else tag


def extract_pptx_text(fpath: str) -> str:
    """Extrai texto de slides, tabelas, notas de apresentador e comentários em arquivos .pptx."""
    lines = []
    comment_lines = []
    try:
        with zipfile.ZipFile(fpath) as z:
            names = z.namelist()
            slides = sorted(
                (n for n in names if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)),
                key=lambda n: int(re.search(r'(\d+)\.xml$', n).group(1)),
            )
            authors_map = {}
            if 'ppt/commentAuthors.xml' in names:
                try:
                    au_root = ET.fromstring(z.read('ppt/commentAuthors.xml'))
                    for au in au_root.iter():
                        if _xml_local(au.tag) == 'cmAuthor':
                            aid = au.attrib.get('id', '')
                            aname = au.attrib.get('name', '').strip()
                            if aid and aname:
                                authors_map[aid] = aname
                except Exception:
                    pass

            matched_notes = set()
            for s_name in slides:
                s_num = re.search(r'(\d+)\.xml$', s_name).group(1)
                try:
                    s_root = ET.fromstring(z.read(s_name))
                except Exception:
                    continue
                tbl_nodes = {id(tbl) for tbl in s_root.iter() if _xml_local(tbl.tag) == 'tbl'}
                tbl_descendants = set()
                for el in s_root.iter():
                    if _xml_local(el.tag) == 'tbl':
                        for desc in el.iter():
                            tbl_descendants.add(id(desc))
                        for tr in el:
                            if _xml_local(tr.tag) != 'tr':
                                continue
                            row_cells = []
                            for tc in tr:
                                if _xml_local(tc.tag) != 'tc':
                                    continue
                                cell_ps = [
                                    ''.join(t.text or '' for t in p.iter() if _xml_local(t.tag) == 't').strip()
                                    for p in tc.iter() if _xml_local(p.tag) == 'p'
                                ]
                                row_cells.append(' '.join(cp for cp in cell_ps if cp))
                            if any(c.strip() for c in row_cells):
                                lines.append(f'[Slide {s_num}] ' + ' | '.join(row_cells))
                for p in s_root.iter():
                    if _xml_local(p.tag) == 'p' and id(p) not in tbl_descendants and id(p) not in tbl_nodes:
                        p_txt = ''.join(t.text or '' for t in p.iter() if _xml_local(t.tag) == 't').strip()
                        p_txt = re.sub(r'\s+', ' ', p_txt).strip()
                        if p_txt:
                            lines.append(f'[Slide {s_num}] {p_txt}')

                note_target = None
                rels_name = f'ppt/slides/_rels/slide{s_num}.xml.rels'
                if rels_name in names:
                    try:
                        rels_root = ET.fromstring(z.read(rels_name))
                        for rel in rels_root.iter():
                            target = rel.attrib.get('Target', '')
                            if 'notesSlide' in target:
                                norm_t = os.path.normpath(os.path.join('ppt/slides', target)).replace('\\', '/')
                                if norm_t in names:
                                    note_target = norm_t
                                    break
                    except Exception:
                        pass
                if not note_target and f'ppt/notesSlides/notesSlide{s_num}.xml' in names:
                    note_target = f'ppt/notesSlides/notesSlide{s_num}.xml'
                if note_target and note_target not in matched_notes:
                    matched_notes.add(note_target)
                    try:
                        n_root = ET.fromstring(z.read(note_target))
                        for p in n_root.iter():
                            if _xml_local(p.tag) == 'p':
                                n_txt = ''.join(t.text or '' for t in p.iter() if _xml_local(t.tag) == 't').strip()
                                n_txt = re.sub(r'\s+', ' ', n_txt).strip()
                                if n_txt and not n_txt.isdigit():
                                    lines.append(f'[Nota do Apresentador — Slide {s_num}] {n_txt}')
                    except Exception:
                        pass

            for cm_file in sorted(n for n in names if re.fullmatch(r'ppt/comments/(?:comment|modernComment)\d*\.xml', n)):
                try:
                    cm_root = ET.fromstring(z.read(cm_file))
                    for cm in cm_root.iter():
                        if _xml_local(cm.tag) in ('cm', 'threadedComment'):
                            aid = cm.attrib.get('authorId', '')
                            author = authors_map.get(aid, 'Revisor')
                            t_parts = [''.join(el.itertext()).strip() for el in cm if _xml_local(el.tag) == 'text']
                            txt = re.sub(r'\s+', ' ', ' '.join(t_parts)).strip()
                            if txt:
                                comment_lines.append(f'{REVIEW_COMMENT_PREFIX} | Comentário PPTX ({author})] {txt}')
                except Exception:
                    continue
    except Exception:
        return ''
    return '\n'.join(lines + comment_lines)


def extract_vsdx_text(fpath: str) -> str:
    """Extrai textos de formas (Shapes) e conexões em arquivos Microsoft Visio .vsdx."""
    lines = []
    try:
        with zipfile.ZipFile(fpath) as z:
            pages = sorted(
                (n for n in z.namelist() if re.fullmatch(r'visio/pages/page\d+\.xml', n)),
                key=lambda n: int(re.search(r'(\d+)\.xml$', n).group(1)),
            )
            for p_name in pages:
                p_num = re.search(r'(\d+)\.xml$', p_name).group(1)
                try:
                    root = ET.fromstring(z.read(p_name))
                except Exception:
                    continue
                id_to_label = {}
                for sh in root.iter():
                    if _xml_local(sh.tag) == 'Shape':
                        sh_id = sh.attrib.get('ID', '')
                        t_parts = []
                        for child in sh:
                            if _xml_local(child.tag) == 'Text':
                                t_parts.append(re.sub(r'\s+', ' ', ''.join(child.itertext())).strip())
                        label = ' '.join(tp for tp in t_parts if tp).strip()
                        if label:
                            if sh_id:
                                id_to_label[sh_id] = label
                            lines.append(f'[Página Visio {p_num}] {label}')
                conns = []
                for conn in root.iter():
                    if _xml_local(conn.tag) == 'Connect':
                        frm = conn.attrib.get('FromSheet', '')
                        to = conn.attrib.get('ToSheet', '')
                        if frm and to and frm != to:
                            conns.append(f"{id_to_label.get(frm, f'Shape#{frm}')} -> {id_to_label.get(to, f'Shape#{to}')}")
                if conns:
                    lines.append(f'[Página Visio {p_num}] Conexões: ' + '; '.join(list(dict.fromkeys(conns))[:200]))
    except Exception:
        return ''
    return '\n'.join(lines)


def extract_opendocument_text(fpath: str) -> str:
    """Extrai texto, tabelas e anotações de revisão de documentos OpenDocument (.odt e .ods)."""
    lines = []
    annotations = []
    ext = os.path.splitext(fpath)[1].lower()
    try:
        with zipfile.ZipFile(fpath) as z:
            if 'content.xml' not in z.namelist():
                return ''
            root = ET.fromstring(z.read('content.xml'))
    except Exception:
        return ''

    ann_descendants = set()
    for el in root.iter():
        if _xml_local(el.tag) == 'annotation':
            for desc in el.iter():
                ann_descendants.add(id(desc))
            creator = 'Revisor'
            p_texts = []
            for child in el:
                clocal = _xml_local(child.tag)
                if clocal == 'creator':
                    creator = ''.join(child.itertext()).strip() or 'Revisor'
                elif clocal in ('p', 'h'):
                    pt = re.sub(r'\s+', ' ', ''.join(child.itertext())).strip()
                    if pt:
                        p_texts.append(pt)
            ann_txt = ' '.join(p_texts).strip()
            if ann_txt:
                annotations.append(f'{REVIEW_COMMENT_PREFIX} | Anotação OpenDocument ({creator})] {ann_txt}')

    tbl_descendants = set()
    for el in root.iter():
        if _xml_local(el.tag) == 'table':
            for desc in el.iter():
                tbl_descendants.add(id(desc))

    if ext == '.ods':
        for tbl in root.iter():
            if _xml_local(tbl.tag) != 'table':
                continue
            tname = next((v for k, v in tbl.attrib.items() if k.endswith('}name') or k == 'name'), 'Planilha')
            t_rows = []
            for row in tbl:
                if _xml_local(row.tag) != 'table-row':
                    continue
                rep_row = next((int(v) for k, v in row.attrib.items() if k.endswith('}number-rows-repeated') and v.isdigit()), 1)
                if rep_row > 50:
                    continue
                cells = []
                for cell in row:
                    if _xml_local(cell.tag) not in ('table-cell', 'covered-table-cell'):
                        continue
                    rep_col = next((int(v) for k, v in cell.attrib.items() if k.endswith('}number-columns-repeated') and v.isdigit()), 1)
                    cell_txt = ' '.join(
                        re.sub(r'\s+', ' ', ''.join(p.itertext())).strip()
                        for p in cell if _xml_local(p.tag) in ('p', 'h') and id(p) not in ann_descendants
                    ).strip()
                    if rep_col > 30 and not cell_txt:
                        break
                    cells.extend([cell_txt] * min(rep_col, 20))
                while cells and not cells[-1].strip():
                    cells.pop()
                if any(c.strip() for c in cells):
                    t_rows.append(' | '.join(cells))
            if t_rows:
                lines.append(f'[ABA: {tname}]')
                lines.extend(t_rows)
    else:
        for el in root.iter():
            local = _xml_local(el.tag)
            if id(el) in ann_descendants:
                continue
            if local == 'table':
                for row in el:
                    if _xml_local(row.tag) != 'table-row':
                        continue
                    cells = []
                    for cell in row:
                        if _xml_local(cell.tag) not in ('table-cell', 'covered-table-cell'):
                            continue
                        cell_txt = ' '.join(
                            re.sub(r'\s+', ' ', ''.join(p.itertext())).strip()
                            for p in cell if _xml_local(p.tag) in ('p', 'h') and id(p) not in ann_descendants
                        ).strip()
                        cells.append(cell_txt)
                    if any(c.strip() for c in cells):
                        lines.append(' | '.join(cells))
            elif local in ('p', 'h') and id(el) not in tbl_descendants:
                txt = re.sub(r'\s+', ' ', ''.join(el.itertext())).strip()
                if txt:
                    lines.append(txt)

    return '\n'.join(lines + annotations)


def extract_html_or_xml_text(fpath: str) -> str:
    """Extrai texto visível e comentários <!-- ... --> de .html/.htm/.xml como contexto não-normativo."""
    import html as html_mod
    raw = _read_text_with_fallback(fpath, max_chars=200000)
    if not raw:
        return ''
    comment_lines = []
    for raw_c in re.findall(r'<!--(.*?)-->', raw, re.S):
        c_txt = re.sub(r'\s+', ' ', raw_c).strip()
        if c_txt:
            comment_lines.append(f'{REVIEW_COMMENT_PREFIX} | Comentário HTML/XML] {c_txt}')
    cleaned = re.sub(r'<!--.*?-->', '', raw, flags=re.S)
    cleaned = re.sub(r'<(script|style)\b[^>]*>.*?</\1>', '', cleaned, flags=re.S | re.I)
    cleaned = re.sub(r'</(?:td|th)\s*>\s*<(?:td|th)\b[^>]*>', ' | ', cleaned, flags=re.I)
    cleaned = re.sub(r'<(?:br|/?p|/?div|/?li|/?tr|/?h[1-6]|/?section|/?article)\b[^>]*>', '\n', cleaned, flags=re.I)
    cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
    cleaned = html_mod.unescape(cleaned)
    text_lines = [re.sub(r'[ \t]+', ' ', ln).strip() for ln in cleaned.splitlines()]
    text_lines = [ln for ln in text_lines if ln]
    return '\n'.join(text_lines + comment_lines)


def get_file_text(fpath: str) -> str:
    """Roteador principal — extrai texto de qualquer formato suportado."""
    ext = os.path.splitext(fpath)[1].lower()
    if ext == '.docx':
        return extract_docx_text(fpath)
    elif ext == '.pdf':
        return extract_pdf_text(fpath)
    elif ext == '.pptx':
        return extract_pptx_text(fpath)
    elif ext == '.vsdx':
        return extract_vsdx_text(fpath)
    elif ext in ('.odt', '.ods'):
        return extract_opendocument_text(fpath)
    elif ext in ('.html', '.htm', '.xml'):
        return extract_html_or_xml_text(fpath)
    elif ext == '.tsv':
        return extract_tsv_text(fpath)
    elif ext in ('.md', '.txt', '.json', '.yaml', '.yml'):
        return extract_text_file(fpath)
    elif ext == '.csv':
        return extract_csv_text(fpath)
    elif ext in ('.xlsx', '.xls'):
        sheets = extract_xlsx_data(fpath)
        body = '\n'.join(
            f'[ABA: {sheet}]\n' + '\n'.join(' | '.join(row) for row in rows)
            for sheet, rows in sheets.items()
        )
        comments = extract_xlsx_comments(fpath) if ext == '.xlsx' else []
        return (body + ('\n' if body and comments else '') + '\n'.join(comments)) if (body or comments) else ''
    return ''


# ─────────────────────────────────────────────
# Palavras-chave para detecção de domínio
# ─────────────────────────────────────────────
# Palavras-chave para detecção de domínio
# ─────────────────────────────────────────────

DOMAIN_KEYWORDS = {
    # Documento/tipo
    "rfp":         ["rfp", "request for proposal", "request for information", "rfi", "edital", "pregão", "concorrência", "licitação", "contratação", "termo de referência", "tr", "especificação técnica", "et"],
    "hld":         ["high level design", "hld", "arquitetura de solução", "arquitetura de alto nível", "solução técnica", "ntp", "nota técnica", "nota técnica de planejamento", "plano de engenharia"],
    "lld":         ["low level design", "lld", "detalhamento técnico", "parametrização", "configuração detalhada", "runbook", "especificação técnica", "et"],
    "contrato":    ["contrato", "penalidade", "sla", "multa", "rescisão", "minuta", "cláusula", "obrigação", "aceite", "entregável", "glosa"],
    "lgpd":        ["lgpd", "privacidade", "dados pessoais", "anpd", "dpo", "consentimento", "titular", "tratamento de dados", "base legal"],
    # Domínios técnicos
    "oss":         ["oss", "gerência de rede", "nms", "fault management", "inventory", "snmp", "netconf", "yang"],
    "bss":         ["bss", "billing", "faturamento", "tarifação", "crm", "arpu", "revenue assurance"],
    "seguranca":   ["segurança", "siem", "soc", "firewall", "vulnerabilidade", "controle de acesso", "cibersegurança", "iso 27001", "nist"],
    "cloud":       ["cloud", "aws", "azure", "gcp", "nuvem", "kubernetes", "saas", "paas", "iaas", "openstack"],
    "datacenter":  ["datacenter", "tier iii", "tier iv", "ups", "nobreak", "climatização", "rack", "gerador", "pdu", "cabling"],
    "integracoes": ["integração", "api", "rest", "soap", "kafka", "barramento", "esb", "middleware", "webhook"],
    "tm_forum":    ["tm forum", "frameworx", "tmf", "sid", "etom", "tam", "open api"],
    "arquitetura": ["arquitetura", "redundância", "alta disponibilidade", "ha", "2n", "n+1", "topologia", "resiliência", "failover", "rto", "rpo"],
    "carrier":     ["carrier", "telecom", "operadora", "mpls", "bgp", "ospf", "isis", "dwdm", "olt", "pon", "sd-wan", "sdwan", "l2vpn", "l3vpn", "p2p", "fibra apagada", "dark fiber", "peering", "ixp", "ptt", "pni", "route reflector", "srv6"],
    "dwdm":        ["dwdm", "oadm", "roadm", "ots", "osnr", "amplificador", "transponder", "mux", "demux", "c-band", "otn"],
    "dcn":         ["dcn", "data communication network", "spine-leaf", "evpn-vxlan", "vxlan", "oob", "out-of-band", "gnmi", "grpc", "break-glass", "pam", "openconfig"],
}

CHECKLIST_DOMAIN_MAP = {
    "rfp":         ["rfp.md", "contratos.md", "oss.md", "bss.md", "arquitetura.md", "integracoes.md", "editorial.md", "estrutura_e_referencias.md"],
    "hld":         ["hld.md", "arquitetura.md", "datacenter.md", "cloud.md", "seguranca.md", "integracoes.md", "diagramas.md", "imagens.md"],
    "lld":         ["lld.md", "arquitetura.md", "integracoes.md", "seguranca.md", "editorial.md"],
    "contrato":    ["contratos.md", "editorial.md", "estrutura_e_referencias.md", "iso.md", "itil.md"],
    "lgpd":        ["lgpd.md", "seguranca.md", "iso.md"],
    "planilha":    ["planilha.md", "tabelas.md", "editorial.md"],
    "oss":         ["oss.md", "bss.md", "integracoes.md", "tm_forum.md"],
    "bss":         ["bss.md", "oss.md", "integracoes.md"],
    "seguranca":   ["seguranca.md", "arquitetura.md", "iso.md"],
    "cloud":       ["cloud.md", "arquitetura.md", "seguranca.md", "iso.md"],
    "datacenter":  ["datacenter.md", "arquitetura.md", "seguranca.md"],
    "integracoes": ["integracoes.md", "tm_forum.md", "arquitetura.md", "rfc.md"],
    "tm_forum":    ["tm_forum.md", "integracoes.md", "oss.md"],
    "arquitetura": ["arquitetura.md", "integracoes.md", "seguranca.md", "ieee.md"],
    "carrier":     ["carrier.md", "mef.md", "rfc.md", "arquitetura.md", "integracoes.md"],
    "dwdm":        ["carrier.md", "arquitetura.md"],
    "dcn":         ["carrier.md", "arquitetura.md", "seguranca.md", "datacenter.md"],
}

ALL_CHECKLISTS = [
    "oss.md", "bss.md", "seguranca.md", "contratos.md", "arquitetura.md",
    "cloud.md", "datacenter.md", "integracoes.md", "tm_forum.md", "imagens.md",
    "diagramas.md", "editorial.md", "estrutura_e_referencias.md", "carrier.md",
    "tabelas.md", "fluxogramas.md", "ieee.md", "iso.md", "itil.md", "mef.md", "rfc.md",
    "rfp.md", "hld.md", "lld.md", "lgpd.md", "planilha.md"
]


# Domínios de tipo de documento requerem evidência mais forte
# para evitar falsos positivos de menções incidentais em outros documentos.
DOC_TYPE_DOMAINS = {"hld", "lld", "rfp"}  # Exigem 2+ hits ou presença no filename


def has_embedded_images(fpath: str, ext: str) -> bool:
    """Verifica se um arquivo (.docx, .pptx, .vsdx, .odt, .ods ou .pdf) contém imagens embutidas."""
    zip_media_prefixes = {
        '.docx': 'word/media/',
        '.pptx': 'ppt/media/',
        '.vsdx': 'visio/media/',
        '.odt': 'Pictures/',
        '.ods': 'Pictures/',
    }
    if ext in zip_media_prefixes:
        prefix = zip_media_prefixes[ext]
        try:
            with zipfile.ZipFile(fpath) as z:
                for name in z.namelist():
                    if name.startswith(prefix):
                        return True
        except Exception:
            pass
    elif ext == '.pdf':
        try:
            import pypdf
            reader = pypdf.PdfReader(fpath)
            for page in reader.pages:
                if len(page.images) > 0:
                    return True
        except Exception:
            pass
        # Fallback regex para identificação de stream de imagem em PDF
        try:
            with open(fpath, 'rb') as f:
                content = f.read(200000)
                if b'/Subtype /Image' in content or b'/Image' in content:
                    return True
        except Exception:
            pass
    return False


def extract_text_from_file(fpath: str) -> str:
    """Extrai o texto legível e comentários não-normativos de qualquer formato suportado."""
    ext = os.path.splitext(fpath)[1].lower()
    if ext in ('.svg', '.drawio'):
        return _read_text_with_fallback(fpath)
    return get_file_text(fpath)


def _line_snippet(text: str, pos: int, limit: int = 360) -> str:
    """Extrai trecho literal de uma única linha ao redor da posição informada."""
    line_start = text.rfind('\n', 0, pos) + 1
    line_end = text.find('\n', pos)
    if line_end == -1:
        line_end = len(text)
    line = re.sub(r'\s+', ' ', text[line_start:line_end]).strip()
    if len(line) <= limit:
        return line
    rel_pos = max(0, pos - line_start)
    start = max(0, rel_pos - 100)
    return line[start:start + limit].strip()


def analyze_document_structure(fpath: str) -> list:
    """Realiza a varredura não-técnica dos 7 pilares de integridade redacional e estrutural."""
    filename = os.path.basename(fpath)
    raw_text = extract_text_from_file(fpath)
    if not raw_text:
        return []
    text = strip_non_normative_comments(raw_text)

    findings = []

    # Controle de Comentários de Revisão / Alterações Rastreadas Pendentes (EDIT-010)
    if REVIEW_COMMENT_PREFIX in raw_text:
        comment_lines_found = [
            (idx, ln.strip())
            for idx, ln in enumerate(raw_text.splitlines(), 1)
            if ln.strip().startswith(REVIEW_COMMENT_PREFIX)
        ]
        if comment_lines_found:
            first_line, first_quote = comment_lines_found[0]
            loc_str = f'Linha {first_line}'
            findings.append({
                'id': 'EDIT-010',
                'title': f'Comentários de revisão ou alterações rastreadas pendentes em {filename}',
                'doc_origem': filename,
                'loc': loc_str,
                'localizacao_exata': loc_str,
                'cat': 'Integridade Redacional e Estrutural',
                'tipo': 'Risco',
                'evid': 'E2 (Corroborado)',
                'citacao': first_quote[:360],
                'evidencia_literal': first_quote[:360],
                'crit': 'Média',
                'prio': 'P2',
                'fato': (
                    f'Foram extraídos {len(comment_lines_found)} comentário(s) ou marcações de revisão pendentes '
                    'no artefato. Esses apontamentos servem como insumo de verificação, mas não constituem texto normativo aprovado.'
                ),
                'impacto': 'Publicar ou contratar com comentários e alterações em aberto gera incerteza sobre qual redação ou requisito vigora oficialmente.',
                'tipo_solucao': 'Plano de Ação Estruturado',
                'texto_atual': first_quote[:240],
                'texto_sugerido': 'Deliberar todos os comentários e alterações rastreadas, incorporando os pontos pertinentes no texto principal e limpando os balões antes da emissão final.',
                'proprietario': 'Área Emissora / Autor Técnico',
                'id_acao': 'ACT-EDIT-010',
                'referencias': [{'titulo': 'FCA-ENG-001 — Controle de Comentários e Rascunhos (EDIT-010)', 'url': '', 'nota': 'Comentários de revisão e Track Changes não constituem fonte normativa de verdade e devem ser saneados.'}]
            })

    # Pilar 6: Marcadores de Rascunho / Campos em Branco
    m_draft = re.search(r'\[(?:Preenchido por|Inserir|A definir|TBD|XXX|\?\?\?)[^\]]*\]|Preenchido por Compras', text, re.IGNORECASE)
    if m_draft:
        line_no = text[:m_draft.start()].count('\n') + 1
        quote = _line_snippet(text, m_draft.start())
        loc_str = f'Linha {line_no}'
        findings.append({
            'id': 'EDIT-001',
            'title': f'Campos de rascunho/template não preenchidos em {filename}',
            'doc_origem': filename,
            'loc': loc_str,
            'localizacao_exata': loc_str,
            'cat': 'Integridade Redacional e Estrutural',
            'tipo': 'Errata/Estrutura',
            'evid': 'E2 (Corroborado)',
            'citacao': quote,
            'evidencia_literal': quote,
            'crit': 'Média',
            'prio': 'P2',
            'fato': 'O documento contém marcações de rascunho/template não preenchidas (ex: "[Preenchido por Compras]" ou marcas de placeholder).',
            'impacto': 'Publicação de documento com marcas de rascunho prejudica a imagem institucional e dificulta a comunicação formal.',
            'tipo_solucao': 'De → Para (Minuta)',
            'texto_atual': m_draft.group(0),
            'texto_sugerido': 'Preencher formalmente todos os campos cadastrais antes da publicação.',
            'proprietario': 'Área Emissora do Documento',
            'id_acao': 'ACT-EDIT-001',
            'referencias': [{'titulo': 'FCA-ENG-001 — Pilar 6 (Marcadores de Rascunho)', 'url': '', 'nota': 'Marcador de template não preenchido na baseline.'}]
        })

    # Pilar 4: Erros de codificação / OCR (ex: An?lise, Especifica??o)
    encoding_bugs = re.findall(r'\b[A-Za-z]+\?[A-Za-z]+\b', text)
    if encoding_bugs:
        m_enc = re.search(r'\b[A-Za-z]+\?[A-Za-z]+\b', text)
        line_no = text[:m_enc.start()].count('\n') + 1
        quote = _line_snippet(text, m_enc.start())
        loc_str = f'Linha {line_no}'
        sample_bugs = ', '.join(list(dict.fromkeys(encoding_bugs))[:5])
        findings.append({
            'id': 'EDIT-002',
            'title': f'Artefatos de conversão de codificação/OCR em palavras de {filename}',
            'doc_origem': filename,
            'loc': loc_str,
            'localizacao_exata': loc_str,
            'cat': 'Integridade Redacional e Estrutural',
            'tipo': 'Errata/Estrutura',
            'evid': 'E2 (Corroborado)',
            'citacao': quote,
            'evidencia_literal': quote,
            'crit': 'Baixa',
            'prio': 'P3',
            'fato': f'Foram identificadas palavras com erro de caracter acentuado (ex: {sample_bugs}).',
            'impacto': 'Prejuízo à legibilidade e apresentação gráfica do documento.',
            'tipo_solucao': 'De → Para (Minuta)',
            'texto_atual': f'Exemplo de termos com erro: {sample_bugs}',
            'texto_sugerido': 'Corrigir a codificação de caracteres para UTF-8 sem perdas de acentuação.',
            'proprietario': 'Revisão Editorial / Autor',
            'id_acao': 'ACT-EDIT-002',
            'referencias': [{'titulo': 'FCA-ENG-001 — Pilar 4 (Codificação UTF-8 e PT-BR)', 'url': '', 'nota': 'Artefato de codificação/OCR detectado no texto.'}]
        })

    # Pilar 4: Vocabulário PT-PT proibido pela regra 8 do AGENTS.md
    pt_pt_rx = r'\b(ficheiro|ficheiros|equipa|equipas|ecrã|ecrãs|facto|factos|planeamento)\b'
    pt_pt_terms = re.findall(pt_pt_rx, text, re.IGNORECASE)
    if pt_pt_terms:
        m_pt = re.search(pt_pt_rx, text, re.IGNORECASE)
        line_no = text[:m_pt.start()].count('\n') + 1
        quote = _line_snippet(text, m_pt.start())
        loc_str = f'Linha {line_no}'
        unique_terms = ', '.join(list(dict.fromkeys(t.lower() for t in pt_pt_terms))[:5])
        findings.append({
            'id': 'EDIT-003',
            'title': f'Uso de vocabulário de Português de Portugal (PT-PT) em {filename}',
            'doc_origem': filename,
            'loc': loc_str,
            'localizacao_exata': loc_str,
            'cat': 'Integridade Redacional e Estrutural',
            'tipo': 'Errata/Estrutura',
            'evid': 'E2 (Corroborado)',
            'citacao': quote,
            'evidencia_literal': quote,
            'crit': 'Baixa',
            'prio': 'P3',
            'fato': f'O documento utiliza termos do Português de Portugal (ex: {unique_terms}), contrariando a norma FCA-ENG-001.',
            'impacto': 'Desalinhamento com as diretrizes corporativas de redação oficial em PT-BR.',
            'tipo_solucao': 'De → Para (Minuta)',
            'texto_atual': f'Termos identificados: {unique_terms}',
            'texto_sugerido': 'Substituir por equivalente PT-BR: "arquivo", "equipe", "tela", "fato", "planejamento".',
            'proprietario': 'Revisão Editorial',
            'id_acao': 'ACT-EDIT-003',
            'referencias': [{'titulo': 'FCA-ENG-001 — Diretriz 8 (PT-BR obrigatório)', 'url': '', 'nota': 'Vocabulário PT-PT proscrito pela norma corporativa.'}]
        })

    # Pilar 7 (RFC 2119 / RFC 8174): Termos Fracos e Ambíguos em Requisitos Mandatórios
    weak_rx = r'\b(em princípio|desejável|preferencialmente|quando conveniente|na medida do possível|se conveniente|se possível)\b'
    weak_terms = re.findall(weak_rx, text, re.IGNORECASE)
    if weak_terms:
        m_weak = re.search(weak_rx, text, re.IGNORECASE)
        line_no = text[:m_weak.start()].count('\n') + 1
        quote = _line_snippet(text, m_weak.start())
        loc_str = f'Linha {line_no}'
        unique_weak = ', '.join(list(dict.fromkeys(w.lower() for w in weak_terms))[:5])
        findings.append({
            'id': 'EDIT-004',
            'title': f'Termos fracos e ambíguos em cláusulas normativas de {filename} (RFC 2119 / RFC 8174)',
            'doc_origem': filename,
            'loc': loc_str,
            'localizacao_exata': loc_str,
            'cat': 'Conformidade RFC 2119/8174',
            'tipo': 'Ambiguidade',
            'evid': 'E2 (Corroborado)',
            'citacao': quote,
            'evidencia_literal': quote,
            'crit': 'Média',
            'prio': 'P2',
            'fato': f'O documento utiliza linguagem de descompromisso ou ambígua em especificações técnicas (ex: "{unique_weak}").',
            'impacto': 'Reduz a força coercitiva contratual e impede a exigência de cumprimento estrito no aceite.',
            'tipo_solucao': 'De → Para (Minuta)',
            'texto_atual': f'Expressões ambíguas encontradas: {unique_weak}',
            'texto_sugerido': 'Substituir por verbos estritos da RFC 2119 em caixa alta: DEVE (mandatório), RECOMENDA-SE (opção justificada) ou PODE (opcional).',
            'proprietario': 'Engenharia de Requisitos / Jurídico',
            'id_acao': 'ACT-EDIT-004',
            'referencias': [{'titulo': 'IETF RFC 2119 / RFC 8174', 'url': '', 'nota': 'Uso de expressões ambíguas em vez de verbos normativos estritos.'}]
        })

    # Pilar 7 (ISO/IEC/IEEE 29148): Requisitos Subjetivos e Não Mensuráveis
    subj_rx = r'\b(altíssima velocidade|sistema rápido|alta performance|interface amigável|super seguro|resposta instantânea)\b'
    subjective_terms = re.findall(subj_rx, text, re.IGNORECASE)
    if subjective_terms:
        m_subj = re.search(subj_rx, text, re.IGNORECASE)
        line_no = text[:m_subj.start()].count('\n') + 1
        quote = _line_snippet(text, m_subj.start())
        loc_str = f'Linha {line_no}'
        unique_subj = ', '.join(list(dict.fromkeys(s.lower() for s in subjective_terms))[:5])
        findings.append({
            'id': 'EDIT-005',
            'title': f'Requisitos subjetivos e não mensuráveis em {filename} (ISO/IEC/IEEE 29148)',
            'doc_origem': filename,
            'loc': loc_str,
            'localizacao_exata': loc_str,
            'cat': 'Engenharia de Requisitos (ISO 29148)',
            'tipo': 'Ambiguidade',
            'evid': 'E2 (Corroborado)',
            'citacao': quote,
            'evidencia_literal': quote,
            'crit': 'Média',
            'prio': 'P2',
            'fato': f'O documento contém adjetivos subjetivos sem métricas numéricas objetivas de teste (ex: "{unique_subj}").',
            'impacto': 'Violou o critério de Testabilidade da ISO 29148, gerando margem para contestação em homologação.',
            'tipo_solucao': 'Plano de Ação Estruturado',
            'texto_atual': f'Adjetivos subjetivos: {unique_subj}',
            'texto_sugerido': 'Especificar KPI numérico quantitativo de aceite (ex: latência < 50ms, vazão > 10 Gbps, SLA 99,99%).',
            'proprietario': 'Comissão Técnica de Engenharia',
            'id_acao': 'ACT-EDIT-005',
            'referencias': [{'titulo': 'ISO/IEC/IEEE 29148', 'url': '', 'nota': 'Critério de verificabilidade e testabilidade quantitativa de requisitos.'}]
        })

    # Pilar 7 (ISO 8601): SLAs e Janelas de Manutenção sem Fuso Horário
    m_tz = re.search(r'\b(24x7|horário comercial|janela de manutenção)\b', text, re.IGNORECASE)
    if m_tz and not re.search(r'\b(UTC|BRT|UTC-3)\b', text):
        line_no = text[:m_tz.start()].count('\n') + 1
        quote = _line_snippet(text, m_tz.start())
        loc_str = f'Linha {line_no}'
        findings.append({
            'id': 'EDIT-006',
            'title': f'Janelas de SLA / Manutenção sem indicação de fuso horário em {filename} (ISO 8601)',
            'doc_origem': filename,
            'loc': loc_str,
            'localizacao_exata': loc_str,
            'cat': 'Integridade Redacional e Estrutural',
            'tipo': 'Lacuna',
            'evid': 'E2 (Corroborado)',
            'citacao': quote,
            'evidencia_literal': quote,
            'crit': 'Baixa',
            'prio': 'P3',
            'fato': 'O documento referencia janelas de atendimento/SLA ("24x7" ou "horário comercial") sem especificar o fuso horário oficial (BRT / UTC-3).',
            'impacto': 'Possibilidade de divergência na contagem de prazos em operações multi-região ou suporte remoto internacional.',
            'tipo_solucao': 'De → Para (Minuta)',
            'texto_atual': 'Período sem fuso horário explicitado.',
            'texto_sugerido': 'Explicitar o fuso horário oficial em todos os prazos: ex. "24x7x365 no fuso horário de Brasília (BRT / UTC-3)".',
            'proprietario': 'Gestão de Operações / Contratos',
            'id_acao': 'ACT-EDIT-006',
            'referencias': [{'titulo': 'ISO 8601', 'url': '', 'nota': 'Especificação explícita de fuso horário em janelas operacionais e SLAs.'}]
        })

    # Pilar 1: Sequência Numeral e Hierarquia (Saltos de numeração em títulos/seções)
    sec_numbers = []
    for line_no, line in enumerate(text.splitlines(), 1):
        m_sec = re.match(r'^\s*(?:#+\s*)?(\d+)\.(\d+)(?!\.\d)\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]', line)
        if m_sec:
            sec_numbers.append((int(m_sec.group(1)), int(m_sec.group(2)), line.strip(), line_no))
    jumps = []
    first_jump_line = 1
    first_jump_quote = ''
    for idx in range(1, len(sec_numbers)):
        prev_maj, prev_min, _, _ = sec_numbers[idx - 1]
        cur_maj, cur_min, cur_txt, cur_line_no = sec_numbers[idx]
        if cur_maj == prev_maj and cur_min > prev_min + 1:
            jumps.append(f"{prev_maj}.{prev_min} → {cur_maj}.{cur_min}")
            if not first_jump_quote:
                first_jump_line = cur_line_no
                first_jump_quote = cur_txt[:360]
    if jumps:
        sample_jumps = ', '.join(jumps[:3])
        loc_str = f'Linha {first_jump_line} ({sample_jumps})'
        findings.append({
            'id': 'EDIT-007',
            'title': f'Quebra de sequência numeral de seções em {filename}',
            'doc_origem': filename,
            'loc': loc_str,
            'localizacao_exata': loc_str,
            'cat': 'Integridade Redacional e Estrutural',
            'tipo': 'Errata/Estrutura',
            'evid': 'E2 (Corroborado)',
            'citacao': first_jump_quote,
            'evidencia_literal': first_jump_quote,
            'crit': 'Baixa',
            'prio': 'P3',
            'fato': f'Foram identificados saltos na numeração sequencial de subseções ({sample_jumps}).',
            'impacto': 'Dificulta a referência cruzada contratual e sugere supressão acidental de cláusulas ou seções.',
            'tipo_solucao': 'De → Para (Minuta)',
            'texto_atual': f'Sequência com salto: {sample_jumps}',
            'texto_sugerido': 'Renumerar sequencialmente todas as seções e atualizar o sumário executivo.',
            'proprietario': 'Revisão Editorial / Autor',
            'id_acao': 'ACT-EDIT-007',
            'referencias': [{'titulo': 'FCA-ENG-001 — Pilar 1 (Sequência Numeral)', 'url': '', 'nota': 'Salto detectado na numeração sequencial de seções.'}]
        })

    # Pilar 3: Referências Cruzadas Órfãs (menção "ver Tabela X" / "conforme Figura Y" sem legenda correspondente)
    orphan_refs = []
    first_orphan_pos = None
    for m_ref in re.finditer(r'\b(?:ver|conforme|vide|na|da)\s+(Tabela|Figura|Quadro)\s+(\d+)\b', text, re.IGNORECASE):
        ref_kind, ref_num = m_ref.group(1), m_ref.group(2)
        label_pat = re.compile(rf'\b{re.escape(ref_kind)}\s+{re.escape(ref_num)}\b', re.IGNORECASE)
        if len(label_pat.findall(text)) <= 1:
            tag = f"{ref_kind.capitalize()} {ref_num}"
            if tag not in orphan_refs:
                orphan_refs.append(tag)
                if first_orphan_pos is None:
                    first_orphan_pos = m_ref.start()
    if orphan_refs and first_orphan_pos is not None:
        sample_orphans = ', '.join(orphan_refs[:4])
        line_no = text[:first_orphan_pos].count('\n') + 1
        quote = _line_snippet(text, first_orphan_pos)
        loc_str = f'Linha {line_no}'
        findings.append({
            'id': 'EDIT-008',
            'title': f'Referências cruzadas órfãs a elementos visuais/tabulares em {filename}',
            'doc_origem': filename,
            'loc': loc_str,
            'localizacao_exata': loc_str,
            'cat': 'Integridade Redacional e Estrutural',
            'tipo': 'Errata/Estrutura',
            'evid': 'E2 (Corroborado)',
            'citacao': quote,
            'evidencia_literal': quote,
            'crit': 'Média',
            'prio': 'P2',
            'fato': f'O texto cita elementos ({sample_orphans}) que ocorrem apenas na chamada referencial, sem legenda ou título correspondente no corpo do documento.',
            'impacto': 'Quebra de rastreabilidade interna e possível ausência de tabela ou figura obrigatória.',
            'tipo_solucao': 'Plano de Ação Estruturado',
            'texto_atual': f'Referências sem destino localizado: {sample_orphans}',
            'texto_sugerido': 'Inserir o elemento ausente com a respectiva legenda numerada ou corrigir o número referenciado.',
            'proprietario': 'Autor Técnico / Revisão Editorial',
            'id_acao': 'ACT-EDIT-008',
            'referencias': [{'titulo': 'FCA-ENG-001 — Pilar 3 (Referências Cruzadas)', 'url': '', 'nota': 'Chamada referencial sem legenda/tabela correspondente.'}]
        })

    # Pilar 7 (ISO 80000): Mistura ambígua de unidades de transmissão (Gbps vs GB/s)
    m_gbps = re.search(r'\b\d+\s*Gbps\b', text)
    m_gbs = re.search(r'\b\d+\s*GB/s\b', text)
    if m_gbps and m_gbs:
        line_no = text[:m_gbps.start()].count('\n') + 1
        quote = _line_snippet(text, m_gbps.start())
        loc_str = f'Linha {line_no}'
        findings.append({
            'id': 'EDIT-009',
            'title': f'Mistura ambígua de unidades de taxa de transmissão (Gbps vs GB/s) em {filename} (ISO 80000)',
            'doc_origem': filename,
            'loc': loc_str,
            'localizacao_exata': loc_str,
            'cat': 'Integridade Redacional e Estrutural',
            'tipo': 'Ambiguidade',
            'evid': 'E2 (Corroborado)',
            'citacao': quote,
            'evidencia_literal': quote,
            'crit': 'Média',
            'prio': 'P2',
            'fato': 'O documento mistura no mesmo texto unidades em Gigabits por segundo (Gbps) e Gigabytes por segundo (GB/s), que diferem por fator de 8x.',
            'impacto': 'Risco de dimensionamento incorreto de interfaces de rede ou barramentos de armazenamento.',
            'tipo_solucao': 'De → Para (Minuta)',
            'texto_atual': 'Uso simultâneo de Gbps e GB/s.',
            'texto_sugerido': 'Padronizar taxas de rede em Gbps (bits/s) e taxas de disco/I/O em GB/s (Bytes/s) conforme ISO 80000.',
            'proprietario': 'Engenharia de Sistemas / Redes',
            'id_acao': 'ACT-EDIT-009',
            'referencias': [{'titulo': 'ISO 80000 / SI', 'url': '', 'nota': 'Coexistência de unidades em bits/s e Bytes/s no mesmo documento.'}]
        })

    return findings


def analyze_document_domain_technical(fpath: str, skills_ativas: list = None) -> list:
    """
    Executa controles complementares de domínio com base nas skills ativas no lote,
    evitando sobreposição com specialized_controls.py e advanced_specialized_controls.py.
    """
    filename = os.path.basename(fpath)
    raw_text = extract_text_from_file(fpath)
    if not raw_text:
        return []
    text = strip_non_normative_comments(raw_text)

    text_lower = text.lower()
    findings = []
    skills = [s.lower() for s in (skills_ativas or [])]

    # --- SKILL: analisar-carrier (Carrier Telecom & DCN) ---
    if not skills or 'analisar-carrier' in skills:
        m_car2 = re.search(r'\b(bgp|mpls|isis|srv6)\b', text, re.IGNORECASE)
        if m_car2 and not re.search(r'\b(bfd|frr|fast reroute)\b', text_lower):
            line_no = text[:m_car2.start()].count('\n') + 1
            quote = _line_snippet(text, m_car2.start())
            loc_str = f'Linha {line_no}'
            findings.append({
                'id': 'CARRIER-002',
                'title': f'Mecanismos de convergência ultra-rápida (BFD e SR-FRR < 50ms) não especificados no Core IP em {filename}',
                'doc_origem': filename,
                'loc': loc_str,
                'localizacao_exata': loc_str,
                'cat': 'Carrier Telecom & DCN',
                'tipo': 'Inconsistência',
                'evid': 'E2 (Corroborado)',
                'citacao': quote,
                'evidencia_literal': quote,
                'crit': 'Alta',
                'prio': 'P1',
                'fato': 'O documento descreve protocolos de roteamento de backbone (BGP/IS-IS/SRv6) sem exigir explicitamente a ativação de BFD (Bidirectional Forwarding Detection) e Fast Reroute (FRR sub-50ms).',
                'impacto': 'Tempo de convergência em queda de enlace pode subir de milissegundos para segundos, derrubando sessões L2/L3VPN e voip.',
                'tipo_solucao': 'De → Para (Minuta)',
                'texto_atual': 'Roteamento IP sem especificação de BFD / FRR.',
                'texto_sugerido': 'DEVE ser ativado BFD com timer de detecção ≤ 50ms e SR-FRR Topology-Independent LFA (TI-LFA) em todas as adjacências de Core.',
                'proprietario': 'Engenharia de Roteamento IP',
                'id_acao': 'ACT-CARRIER-002',
                'referencias': [{'titulo': 'IETF RFC 5880 (BFD) / TI-LFA', 'url': '', 'nota': 'Convergência rápida em roteamento IP/MPLS de backbone.'}]
            })

    # --- SKILL: analisar-rfp (Requests for Proposal / RFIs) ---
    if not skills or 'analisar-rfp' in skills:
        m_rfp1 = re.search(r'\b(sla|penalidade)\b', text, re.IGNORECASE)
        if m_rfp1 and not re.search(r'\b(raci|matriz de responsabilidades)\b', text_lower):
            line_no = text[:m_rfp1.start()].count('\n') + 1
            quote = _line_snippet(text, m_rfp1.start())
            loc_str = f'Linha {line_no}'
            findings.append({
                'id': 'RFP-001',
                'title': f'Ausência de Matriz RACI explicita para obrigações contratuais e SLAs em {filename}',
                'doc_origem': filename,
                'loc': loc_str,
                'localizacao_exata': loc_str,
                'cat': 'Requests for Proposal (RFP)',
                'tipo': 'Lacuna',
                'evid': 'E2 (Corroborado)',
                'citacao': quote,
                'evidencia_literal': quote,
                'crit': 'Alta',
                'prio': 'P1',
                'fato': 'O documento estabelece metas de SLA e penalidades mas não define formalmente a Matriz RACI (Responsible, Accountable, Consulted, Informed) para cada evento operacional.',
                'impacto': 'Risco de omissão em incidentes graves por indefinição de quem deve executar o chamado ou autorizar a janela de manutenção.',
                'tipo_solucao': 'De → Para (Minuta)',
                'texto_atual': 'Obrigações operacionais em voz passiva sem responsável atribuído.',
                'texto_sugerido': 'Incluir anexo normativo com a Matriz RACI detalhando a responsabilidade da Contratada e da Contratante para cada SLA.',
                'proprietario': 'Comissão Licitante / Gestão de Contratos',
                'id_acao': 'ACT-RFP-001',
                'referencias': [{'titulo': 'FCA-ENG-001 / ITIL v4 — Matriz RACI', 'url': '', 'nota': 'Definição explícita de papéis e responsabilidades em SLAs.'}]
            })

    # --- SKILL: analisar-hld (High Level Design) ---
    if not skills or 'analisar-hld' in skills:
        m_hld1 = re.search(r'\b(cluster|redundância|ha)\b', text, re.IGNORECASE)
        if m_hld1 and not re.search(r'\b(quorum|split-brain|witness|fencing)\b', text_lower):
            line_no = text[:m_hld1.start()].count('\n') + 1
            quote = _line_snippet(text, m_hld1.start())
            loc_str = f'Linha {line_no}'
            findings.append({
                'id': 'HLD-001',
                'title': f'Mecanismo de Quorum e proteção contra Split-Brain não especificado no cluster de {filename}',
                'doc_origem': filename,
                'loc': loc_str,
                'localizacao_exata': loc_str,
                'cat': 'High Level Design (HLD)',
                'tipo': 'Lacuna',
                'evid': 'E2 (Corroborado)',
                'citacao': quote,
                'evidencia_literal': quote,
                'crit': 'Alta',
                'prio': 'P1',
                'fato': 'O HLD prevê arquitetura em cluster de alta disponibilidade (HA) mas não detalha o mecanismo de Quorum, nó Witness ou protocolo de Fencing para prevenção de Split-Brain.',
                'impacto': 'Em caso de partição de rede, ambos os nós podem assumir papel primário simultaneamente, causando corrupção de dados.',
                'tipo_solucao': 'Plano de Ação Estruturado',
                'texto_atual': 'Cluster HA descrito sem especificação de Quorum / Witness.',
                'texto_sugerido': 'Especificar o mecanismo de Quorum (ex: Majority Node Set ou Witness em 3º site) e a política de fencing automático.',
                'proprietario': 'Arquitetura de Soluções / Datacenter',
                'id_acao': 'ACT-HLD-001',
                'referencias': [{'titulo': 'FCA-ENG-001 — HLD / Alta Disponibilidade', 'url': '', 'nota': 'Prevenção de split-brain e controle de quorum em clusters HA.'}]
            })

    return findings


def _contains_domain_keyword(corpus: str, keyword: str) -> bool:
    """Evita que siglas curtas, como TR ou ET, casem dentro de palavras."""
    if len(keyword) <= 3 and keyword.isalpha():
        return bool(re.search(rf"\b{re.escape(keyword)}\b", corpus, re.I))
    return keyword.lower() in corpus.lower()


def detect_domains(text_corpus: str, filename_corpus: str) -> list:
    """Detecção semântica de domínios por frequência e contexto.

    Domínios de tipo de documento (hld, lld, rfp) são ativados somente se:
    - Aparecem no nome do arquivo/pasta (sinal forte), OU
    - Têm 2+ hits de palavras-chave distintas no texto.
    Demais domínios técnicos: 1 hit já ativa.
    """
    combined = (text_corpus + " " + filename_corpus).lower()
    fname_lower = filename_corpus.lower()
    detected = []
    for domain, keywords in DOMAIN_KEYWORDS.items():
        hits = sum(1 for kw in keywords if _contains_domain_keyword(combined, kw))
        if hits == 0:
            continue
        if domain in DOC_TYPE_DOMAINS:
            # Tipo documental exige nome do arquivo/pasta ou título/capa no início do corpus.
            # Menções no corpo (ex.: HLD, LLD e RFP) não ativam uma skill por si só.
            in_filename = any(_contains_domain_keyword(fname_lower, kw) for kw in keywords)
            in_header = any(_contains_domain_keyword(text_corpus[:4000], kw) for kw in keywords)
            if in_filename or in_header:
                detected.append((domain, hits + (5 if in_filename else 0) + (3 if in_header else 0)))
        else:
            detected.append((domain, hits))
    detected.sort(key=lambda x: -x[1])
    return [d[0] for d in detected]


def get_active_checklists(domains: list, has_images: bool, has_xlsx: bool) -> tuple:
    """Retorna (checklists_ativos, checklists_inaplicaveis) com base nos domínios."""
    active = set()
    active.add("editorial.md")
    active.add("estrutura_e_referencias.md")

    for domain in domains:
        for chk in CHECKLIST_DOMAIN_MAP.get(domain, []):
            active.add(chk)

    if has_images:
        active.add("imagens.md")
        active.add("diagramas.md")
        active.add("fluxogramas.md")
    if has_xlsx:
        active.add("tabelas.md")
        active.add("planilha.md")

    inactive = [c for c in ALL_CHECKLISTS if c not in active]
    return sorted(list(active)), sorted(inactive)


def get_skills_recommendation(domains: list, has_images: bool, has_xlsx: bool) -> list:
    """Retorna lista de skills recomendadas com justificativa."""
    skills = [{"skill": "analisar-documento", "motivo": "Skill base — sempre ativa para qualquer lote de documentos."}]

    # RFP é um tipo documental: cláusulas contratuais isoladas não o caracterizam.
    if "rfp" in domains:
        skills.append({"skill": "analisar-rfp", "motivo": "Detectado: RFP/RFI/Edital/Concorrência/Termo de Referência no nome ou conteúdo."})

    if "hld" in domains:
        skills.append({"skill": "analisar-hld", "motivo": "Detectado: High Level Design / Nota Técnica (NTP) no nome do arquivo ou conteúdo."})
    if "lld" in domains:
        skills.append({"skill": "analisar-lld", "motivo": "Detectado: Low Level Design / Especificação Técnica (ET) no nome do arquivo ou conteúdo."})

    # Cláusulas contratuais são tratadas pela skill própria, não como RFP implícita.
    if "contrato" in domains and "rfp" not in domains:
        skills.append({"skill": "analisar-contrato", "motivo": "Detectado: cláusulas contratuais sem RFP — documento contratual dedicado."})

    if any(d in domains for d in ("carrier", "dwdm", "dcn")):
        skills.append({"skill": "analisar-carrier", "motivo": "Detectado: perfil de Operadora de Transporte (Carrier Telecom, Fibra Apagada, DWDM, REDIP Core/Edge/Metro, SD-WAN, L2/L3VPN, BGP Peering/RRs ou DCN Fabric)."})
    if "datacenter" in domains:
        skills.append({"skill": "analisar-datacenter", "motivo": "Detectado: infraestrutura de Datacenter (Tier III/IV, UPS, Climatização, Cabling)."})
    if "cloud" in domains:
        skills.append({"skill": "analisar-cloud", "motivo": "Detectado: infraestrutura Cloud/Nuvem (AWS/Azure/GCP/OpenStack/Kubernetes)."})
    if "integracoes" in domains or "tm_forum" in domains:
        skills.append({"skill": "analisar-integracoes", "motivo": "Detectado: arquitetura de integrações, APIs, ESB ou TM Forum."})
    if has_images:
        skills.append({"skill": "analisar-diagramas", "motivo": "Detectado: imagens soltas (PNG/JPG/SVG) ou diagramas/esquemas embutidos em .docx/.pdf."})
    if has_xlsx:
        skills.append({"skill": "analisar-planilha", "motivo": "Detectado: planilhas .xlsx/.csv no lote."})
    if "lgpd" in domains:
        skills.append({"skill": "analisar-lgpd", "motivo": "Detectado: referências a LGPD, dados pessoais ou privacidade."})

    return skills


# ─────────────────────────────────────────────
# Ferramentas MCP
# ─────────────────────────────────────────────

def tool_freeze_baseline(lote_path: str = None) -> str:
    """Calcula SHA-256 de todos os arquivos de um lote (busca recursiva)."""
    root = get_workspace_root()
    ensure_infrastructure(root)

    if lote_path:
        scan_dir = os.path.join(root, lote_path) if not os.path.isabs(lote_path) else lote_path
    else:
        scan_dir = os.path.join(root, 'entrada')

    if not os.path.exists(scan_dir):
        return json.dumps({"status": "error", "message": f"Caminho não encontrado: {scan_dir}"}, ensure_ascii=False)

    files = []
    for dirpath, _, filenames in os.walk(scan_dir):
        for fname in sorted(filenames):
            if fname.startswith('.') or fname in ('README.md', 'decisoes.yaml'):
                continue
            fpath = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(fpath, root)
            try:
                file_hash = calculate_file_hash(fpath)
                files.append({
                    "filename": fname,
                    "relative_path": rel_path,
                    "extension": os.path.splitext(fname)[1].lower(),
                    "sha256": file_hash,
                    "size_bytes": os.path.getsize(fpath)
                })
            except Exception as e:
                files.append({"filename": fname, "relative_path": rel_path, "error": str(e)})

    return json.dumps({"status": "success", "scan_path": scan_dir, "files": files}, indent=2, ensure_ascii=False)


DOMAIN_SKILL_MAP = {
    "datacenter": ("analisar-datacenter", "Skill especializada para Revisão Técnica de Datacenters (Infraestrutura Tier III/IV, UPS, Climatização, Redundância 2N/N+1, Cabling Passivo).", "datacenter.md"),
    "cloud": ("analisar-cloud", "Skill especializada para Revisão Técnica de Arquiteturas em Nuvem (Multi-Cloud AWS/Azure/GCP, OpenStack, Kubernetes, Serverless).", "cloud.md"),
    "integracoes": ("analisar-integracoes", "Skill especializada para Revisão Técnica de Integrações, Barramentos ESB, REST/SOAP APIs e TM Forum Open APIs.", "integracoes.md"),
}


def auto_scaffold_missing_skills(profiles: list):
    """Detecta domínios sem skill especializada em .agents/skills/ e cria o rascunho automaticamente."""
    root = get_workspace_root()
    skills_root = os.path.join(root, '.agents', 'skills')
    agents_md_path = os.path.join(root, '.agents', 'AGENTS.md')

    for p in profiles:
        for domain in p.get("detected_domains", []):
            if domain in DOMAIN_SKILL_MAP:
                skill_name, desc, chk_file = DOMAIN_SKILL_MAP[domain]
                skill_dir = os.path.join(skills_root, skill_name)
                if not os.path.exists(skill_dir):
                    tool_scaffold_skill(skill_name, description=desc, domain=domain, checklist_file=chk_file)
                    if os.path.exists(agents_md_path):
                        try:
                            with open(agents_md_path, 'r', encoding='utf-8') as af:
                                content = af.read()
                            if skill_name not in content:
                                new_entry = f"- [{skill_name}](.agents/skills/{skill_name}/SKILL.md): {desc}\n"
                                if "### Skills Especializadas por Tipo de Documento" in content:
                                    content = content.replace("### Skills Especializadas por Tipo de Documento\n", f"### Skills Especializadas por Tipo de Documento\n{new_entry}")
                                    with open(agents_md_path, 'w', encoding='utf-8') as af:
                                        af.write(content)
                        except Exception:
                            pass


def check_environment_capabilities() -> dict:
    """Verifica proativamente pacotes Python e utilitários do SO para potencializar as análises do framework."""
    python_caps = {}

    # openpyxl
    try:
        import openpyxl
        python_caps["openpyxl"] = {
            "installed": True,
            "version": getattr(openpyxl, "__version__", "detectado"),
            "status": "ativo",
            "capability": "Extração precisa de células, fórmulas, abas e planilhas .xlsx/.xls"
        }
    except ImportError:
        python_caps["openpyxl"] = {
            "installed": False,
            "status": "fallback ativo (leitura nativa via XML)",
            "capability": "Extração precisa de planilhas",
            "install_cmd": "pip install openpyxl"
        }

    # pypdf
    try:
        import pypdf
        python_caps["pypdf"] = {
            "installed": True,
            "version": getattr(pypdf, "__version__", "detectado"),
            "status": "ativo",
            "capability": "Extração de fluxos de texto e imagens embutidas em documentos .pdf"
        }
    except ImportError:
        python_caps["pypdf"] = {
            "installed": False,
            "status": "inativo (documentos PDF serão extraídos via fallback)",
            "capability": "Extração de texto e imagens em PDF",
            "install_cmd": "pip install pypdf"
        }

    # Pillow (PIL)
    try:
        from PIL import Image
        import PIL
        python_caps["Pillow"] = {
            "installed": True,
            "version": getattr(PIL, "__version__", "detectado"),
            "status": "ativo",
            "capability": "Inspeção de dimensões, formato e conversão de diagramas/imagens"
        }
    except ImportError:
        python_caps["Pillow"] = {
            "installed": False,
            "status": "inativo",
            "capability": "Processamento avançado de imagens e diagramas",
            "install_cmd": "pip install Pillow"
        }

    # Utilitários do SO (Linux)
    so_caps = {}
    pdftoppm_bin = os.environ.get("FCA_PDFTOPPM") or shutil.which("pdftoppm")
    if pdftoppm_bin:
        so_caps["poppler-utils (pdftoppm)"] = {
            "installed": True,
            "path": pdftoppm_bin,
            "status": "ativo",
            "capability": "Renderização de páginas inteiras de PDF contendo diagramas, arquiteturas e topologias"
        }
    else:
        so_caps["poppler-utils (pdftoppm)"] = {
            "installed": False,
            "status": "inativo (páginas de PDF com diagramas complexos não serão renderizadas como imagens)",
            "capability": "Renderização visual de páginas PDF",
            "install_cmd": "sudo apt install -y poppler-utils"
        }

    tesseract_bin = os.environ.get("FCA_TESSERACT") or shutil.which("tesseract")
    if tesseract_bin:
        langs = []
        try:
            res = subprocess.run([tesseract_bin, "--list-langs"], capture_output=True, text=True, timeout=5, check=False)
            if res.returncode == 0:
                langs = [l.strip() for l in res.stdout.splitlines()[1:] if l.strip()]
        except Exception:
            pass
        so_caps["tesseract-ocr"] = {
            "installed": True,
            "path": tesseract_bin,
            "languages": langs,
            "has_portuguese": "por" in langs,
            "status": "ativo" if "por" in langs else "alerta: suporte ao idioma português ('por') não instalado",
            "capability": "OCR de rótulos de rede, tabelas e textos em diagramas/imagens (PNG, JPG)"
        }
    else:
        so_caps["tesseract-ocr"] = {
            "installed": False,
            "status": "inativo (OCR de imagens desabilitado)",
            "capability": "Reconhecimento óptico de caracteres em diagramas",
            "install_cmd": "sudo apt install -y tesseract-ocr tesseract-ocr-por"
        }

    # Recomendações agregadas
    missing_so = [k for k, v in so_caps.items() if not v["installed"]]
    missing_py = [k for k, v in python_caps.items() if not v["installed"]]

    quick_fix = []
    if missing_so:
        apt_pkgs = []
        if not so_caps["poppler-utils (pdftoppm)"]["installed"]:
            apt_pkgs.append("poppler-utils")
        if not so_caps["tesseract-ocr"]["installed"]:
            apt_pkgs.extend(["tesseract-ocr", "tesseract-ocr-por"])
        if apt_pkgs:
            quick_fix.append(f"sudo apt update && sudo apt install -y {' '.join(apt_pkgs)}")

    if missing_py:
        quick_fix.append(f"pip install {' '.join(missing_py)}")

    full_multimodal_ready = len(missing_so) == 0 and len(missing_py) == 0

    return {
        "python_environment": {
            "version": sys.version.split()[0],
            "packages": python_caps
        },
        "system_tools": so_caps,
        "full_multimodal_ready": full_multimodal_ready,
        "recommendations": quick_fix if quick_fix else ["Ambiente 100% potencializado para análises textuais, tabulares e multimodais."]
    }


def tool_check_environment() -> str:
    """Audita dependências do SO e Python e retorna matriz de capacidades e comandos de instalação."""
    caps = check_environment_capabilities()
    return json.dumps({
        "status": "success",
        "capabilities": caps
    }, indent=2, ensure_ascii=False)


def tool_profile_baseline(lote_path: str = None, primary_files: list[str] = None) -> str:
    """
    Triagem adaptativa do lote: detecta domínios semanticamente, mapeia checklists,
    recomenda skills e gera decisoes.yaml. Suporta subpastas aninhadas.
    """
    root = get_workspace_root()
    ensure_infrastructure(root)

    entrada_dir = os.path.join(root, 'entrada')

    # Se lote específico foi passado, analisar só ele
    if lote_path:
        target = os.path.join(root, lote_path) if not os.path.isabs(lote_path) else lote_path
        lotes = [target] if os.path.isdir(target) else []
        mode = "single_batch"
    else:
        # Detectar subpastas numeradas no 1º nível de entrada/
        entries = [e for e in sorted(os.listdir(entrada_dir))
                   if not e.startswith('.') and e not in ('README.md', 'decisoes.yaml')]
        subdirs = [e for e in entries if os.path.isdir(os.path.join(entrada_dir, e))]
        lotes = [os.path.join(entrada_dir, d) for d in subdirs]
        mode = "batch" if lotes else "single"

    if not lotes:
        # Modo single: arquivos direto em entrada/
        lotes = [entrada_dir]
        mode = "single"

    IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.svg', '.drawio', '.vsdx', '.bmp', '.gif', '.webp', '.tif', '.tiff'}
    XLSX_EXTS = {'.xlsx', '.xls', '.ods', '.csv', '.tsv'}
    DOC_EXTS = {'.docx', '.pdf', '.pptx', '.odt', '.txt', '.md', '.json', '.yaml', '.yml', '.html', '.htm', '.xml'}

    def profile_lote(lote_dir: str) -> dict:
        text_corpus = ""
        filename_corpus = ""
        files_found = []
        images = []
        xlsx_files = []
        doc_files = []

        raw_entries = []
        for dirpath, _, filenames in os.walk(lote_dir):
            for fname in sorted(filenames):
                if fname.startswith('.') or fname in ('README.md', 'decisoes.yaml'):
                    continue
                fpath = os.path.join(dirpath, fname)
                ext = os.path.splitext(fname)[1].lower()
                rel = os.path.relpath(fpath, lote_dir)
                size = os.path.getsize(fpath)
                raw_entries.append((fpath, fname, rel, ext, size))

        lote_name = os.path.basename(lote_dir)
        roles_map = _classify_batch_document_roles(lote_name, [e[2] for e in raw_entries], primary_files=primary_files)

        has_embedded = False
        for fpath, fname, rel, ext, size in raw_entries:
            role = roles_map.get(rel, "alvo_principal")
            files_found.append({"name": fname, "path": rel, "ext": ext, "size_bytes": size, "role": role})
            if role == "insumo_externo":
                continue

            filename_corpus += " " + fname.lower() + " " + rel.lower()

            if ext in IMAGE_EXTS:
                images.append(fname)
                if ext in ('.vsdx', '.svg', '.drawio'):
                    text_corpus += " " + get_file_text(fpath)[:100000].lower()
            elif ext in XLSX_EXTS:
                xlsx_files.append(fname)
                text_corpus += " " + get_file_text(fpath)[:100000].lower()
                if ext == '.ods' and not has_embedded and has_embedded_images(fpath, ext):
                    has_embedded = True
            elif ext in DOC_EXTS:
                doc_files.append(fname)
                text = get_file_text(fpath)
                text_corpus += " " + text[:100000].lower()
                if not has_embedded and has_embedded_images(fpath, ext):
                    has_embedded = True

        domains = detect_domains(text_corpus, filename_corpus)
        has_images = (len(images) > 0) or has_embedded
        has_xlsx = len(xlsx_files) > 0
        active_chk, inactive_chk = get_active_checklists(domains, has_images, has_xlsx)
        skills = get_skills_recommendation(domains, has_images, has_xlsx)

        # Detecção de séries temporais de versões dentro do lote
        import audit_engine
        version_groups = audit_engine.detect_document_versions([os.path.basename(f) for f in doc_files])
        has_version_series = any(len(v) > 1 for v in version_groups.values())

        return {
            "lote_dir": lote_dir,
            "lote_name": lote_name,
            "files": files_found,
            "docs_count": len(doc_files),
            "images_count": len(images),
            "xlsx_count": len(xlsx_files),
            "detected_domains": domains,
            "active_checklists": active_chk,
            "inactive_checklists": inactive_chk,
            "skills_recommendation": skills,
            "has_images": has_images,
            "has_xlsx": has_xlsx,
            "has_version_series": has_version_series,
            "version_groups": version_groups
        }

    profiles = [profile_lote(l) for l in lotes]
    auto_scaffold_missing_skills(profiles)

    # Gera decisoes.yaml
    decisoes_path = os.path.join(entrada_dir, 'decisoes.yaml')
    _dump_decisoes_yaml(profiles, decisoes_path, mode)

    return json.dumps({
        "status": "success",
        "mode": mode,
        "total_lotes": len(profiles),
        "environment_capabilities": check_environment_capabilities(),
        "profiles": profiles,
        "decisoes_yaml": "entrada/decisoes.yaml"
    }, indent=2, ensure_ascii=False)


def _dump_decisoes_yaml(profiles: list, output_path: str, mode: str):
    lines = [
        '# Manifesto de Triagem Adaptativa (FCA-ENG-001)',
        '# Gerado automaticamente pelo profile_baseline.',
        '# Revise e confirme antes de prosseguir com a análise.',
        '',
        f'modo_execucao: "{mode}"',
        'autorizado_pelo_usuario: true  # Autônomo — ativado por padrão',
        '',
        'lotes:',
    ]
    for p in profiles:
        lines.append(f'  - id: "{p["lote_name"]}"')
        lines.append(f'    pasta: "{p["lote_dir"]}"')
        lines.append(f'    autorizar: true  # Autônomo — ativado por padrão')
        lines.append(f'    domínios_detectados:')
        for d in p["detected_domains"]:
            lines.append(f'      - {d}')
        lines.append(f'    skills_recomendadas:')
        for s in p["skills_recommendation"]:
            lines.append(f'      - skill: {s["skill"]}')
            lines.append(f'        motivo: "{s["motivo"]}"')
        lines.append(f'    checklists_ativos:')
        for c in p["active_checklists"]:
            lines.append(f'      - {c}')
        lines.append('')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def tool_analyze_structural_integrity(lote_path: str = "entrada") -> str:
    """Executa a verificação automatizada dos 7 pilares de integridade estrutural e redacional sobre todos os arquivos do lote."""
    root = get_workspace_root()
    base_dir = os.path.join(root, lote_path) if not os.path.isabs(lote_path) else lote_path
    if not os.path.exists(base_dir):
        return json.dumps({"status": "error", "message": f"Caminho não encontrado: {base_dir}"}, ensure_ascii=False)

    all_findings = []
    for root_dir, _, files in os.walk(base_dir):
        for f in files:
            fpath = os.path.join(root_dir, f)
            findings = analyze_document_structure(fpath)
            all_findings.extend(findings)

    return json.dumps({
        "status": "success",
        "lote": lote_path,
        "total_structural_findings": len(all_findings),
        "findings": all_findings
    }, indent=2, ensure_ascii=False)


def tool_scaffold_skill(skill_name: str, description: str = "", domain: str = "", checklist_file: str = "") -> str:
    """Gera rascunho de nova skill em .agents/skills/<skill_name>/SKILL.md."""
    root = get_workspace_root()
    if not skill_name:
        return json.dumps({"status": "error", "message": "Parâmetro skill_name é obrigatório."}, ensure_ascii=False)

    skill_dir = os.path.join(root, '.agents', 'skills', skill_name)
    skill_file = os.path.join(skill_dir, 'SKILL.md')
    template_path = os.path.join(root, 'framework', 'templates', 'modelo_skill.md')

    os.makedirs(skill_dir, exist_ok=True)

    title = skill_name.replace('-', ' ').title()
    domain_name = domain or title
    desc = description or f"Executa a revisão técnica especializada no domínio {domain_name}."
    chk_raw = checklist_file or f"{skill_name.replace('analisar-', '')}.md"
    chk = chk_raw if chk_raw.endswith('.md') else f"{chk_raw}.md"

    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as tf:
            content = tf.read()
        content = content.replace('{{SKILL_NAME}}', skill_name)
        content = content.replace('{{SKILL_DESCRIPTION}}', desc)
        content = content.replace('{{SKILL_TITLE}}', title)
        content = content.replace('{{SKILL_DOMAIN}}', domain_name)
        content = content.replace('{{CHECKLIST_FILE}}.md', chk)
        content = content.replace('{{CHECKLIST_FILE}}', chk)
    else:
        content = f"""---
name: {skill_name}
description: {desc}
---

# Skill: {title}

## Propósito
{desc}

## Domínio Principal
{domain_name}

## Checklists Associados
- `framework/checklists/{chk}`

## Workflow
1. Identificar seções relevantes ao domínio {domain_name} no lote em `entrada/`.
2. Aplicar checklist `framework/checklists/{chk}`.
3. Registrar achados na base `dados_analise.json` (SSOT) via `record_semantic_analysis` e recompilar `index.html`.
"""

    with open(skill_file, 'w', encoding='utf-8') as sf:
        sf.write(content)

    return json.dumps({
        "status": "success",
        "message": f"Rascunho da skill {skill_name} criado para validação.",
        "skill_file": skill_file
    }, indent=2, ensure_ascii=False)


def _detect_primary_batch_version(lote_name: str, files_info: list[dict]) -> str:
    """Detecta a versão do documento principal do lote pela sobreposição semântica com lote_name."""
    normative_files = [
        item for item in (files_info or [])
        if str(item.get("role", "alvo_principal")) != "insumo_externo"
    ]
    primary_candidates = [
        item for item in normative_files
        if str(item.get("role", "")) == "alvo_principal"
    ]
    pool = primary_candidates or normative_files or (files_info or [])
    lote_tokens = set(re.findall(r"[a-z0-9]+", (lote_name or "").casefold()))
    best_score = (-1, -1)
    best_version = "v1.0"
    for item in sorted(pool, key=lambda x: str(x.get("name", ""))):
        fname = str(item.get("name") or os.path.basename(str(item.get("path", "")))).strip()
        if not fname:
            continue
        stem = os.path.splitext(fname)[0]
        clean_stem = re.sub(r"(?:[._\-\s]+rev(?:gptc|isao|iew)?[a-z0-9._\-]*)+$", "", stem, flags=re.IGNORECASE)
        matches = re.findall(r"\b(v?\d+(?:\.\d+)+)\b", clean_stem or stem, flags=re.IGNORECASE)
        if not matches:
            continue
        ver_raw = matches[-1].lstrip("vV")
        ver_norm = f"v{ver_raw}"
        file_tokens = set(re.findall(r"[a-z0-9]+", (clean_stem or stem).casefold()))
        overlap = len(lote_tokens & file_tokens)
        score = (overlap, len(file_tokens))
        if overlap > best_score[0] or (overlap == best_score[0] and best_score[0] >= 0 and score > best_score):
            best_score = score
            best_version = ver_norm
    return best_version if best_score[0] >= 0 else "v1.0"


def _classify_batch_document_roles(
    lote_name: str,
    file_paths: list[str],
    primary_files: list[str] = None,
) -> dict[str, str]:
    """Classifica cada arquivo do lote como alvo_principal, apoio_cruzamento ou insumo_externo."""
    stopwords = {
        "01", "02", "03", "04", "05", "lote", "hld", "lld", "rfp", "rfi",
        "et", "ntp", "pdf", "docx", "xlsx",
    }

    def _ascii_lower(txt: str) -> str:
        norm = unicodedata.normalize("NFKD", txt or "")
        return "".join(ch for ch in norm if not unicodedata.combining(ch)).casefold()

    def _sig_tokens(txt: str) -> set[str]:
        tokens = re.findall(r"[a-z0-9]+", _ascii_lower(txt))
        return {tok for tok in tokens if tok not in stopwords and not re.fullmatch(r"v?\d+", tok)}

    roles: dict[str, str] = {}
    normative_paths: list[str] = []
    for orig_path in file_paths or []:
        norm_p = str(orig_path).replace("\\", "/").lstrip("./")
        norm_low = _ascii_lower(norm_p)
        fname_low = _ascii_lower(os.path.basename(norm_p))
        if (
            norm_low.startswith(("insumos_externos/", "input/"))
            or "/insumos_externos/" in norm_low
            or "/input/" in norm_low
            or "relatorio_analise" in fname_low
            or "relatorio_complementar" in fname_low
            or bool(re.search(r"(?:^|[._\-\s])revgptc(?:[._\-\s]|\d|$)", fname_low))
        ):
            roles[orig_path] = "insumo_externo"
        else:
            normative_paths.append(orig_path)

    if not normative_paths:
        return roles

    if primary_files:
        explicit = {
            str(p).strip().replace("\\", "/").lstrip("./").casefold()
            for p in primary_files
            if str(p).strip()
        }
        matched_any = False
        for orig_path in normative_paths:
            norm_p = str(orig_path).replace("\\", "/").lstrip("./").casefold()
            base_p = os.path.basename(norm_p).casefold()
            if norm_p in explicit or base_p in explicit:
                roles[orig_path] = "alvo_principal"
                matched_any = True
            else:
                roles[orig_path] = "apoio_cruzamento"
        if matched_any:
            return roles

    lote_tokens = _sig_tokens(lote_name)
    scored: list[tuple[str, int]] = []
    for orig_path in normative_paths:
        stem = os.path.splitext(os.path.basename(str(orig_path)))[0]
        overlap = len(lote_tokens & _sig_tokens(stem))
        scored.append((orig_path, overlap))

    max_overlap = max((score for _, score in scored), default=0)
    has_lower = any(score < max_overlap for _, score in scored)
    if max_overlap > 0 and has_lower:
        for orig_path, score in scored:
            roles[orig_path] = "alvo_principal" if score == max_overlap else "apoio_cruzamento"
    else:
        for orig_path in normative_paths:
            roles[orig_path] = "alvo_principal"
    return roles


def tool_run_full_audit(lote_path: str = None, primary_files: list[str] = None) -> str:
    """
    Executa o pipeline nativo e 100% dinâmico de auditoria RTI sobre os lotes em entrada/.
    Triagem adaptativa -> Extração ao vivo -> 7 Pilares -> Checklists -> JSON SSOT + HTML -> Central Master.
    """
    root = get_workspace_root()
    raw_profile = tool_profile_baseline(lote_path, primary_files=primary_files)
    profile_res = json.loads(raw_profile)

    if profile_res.get("status") != "success":
        return json.dumps(profile_res, ensure_ascii=False)

    profiles = profile_res.get("profiles", [])
    if not profiles:
        return json.dumps({"status": "error", "message": "Nenhum lote encontrado para processamento."}, ensure_ascii=False)

    results = []
    import audit_engine
    import html_compiler
    from datetime import datetime

    for p in profiles:
        lote_dir = p["lote_dir"]
        lote_name = p["lote_name"]

        now_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        ts_leaf = f"{now_str}_{lote_name}"
        detected_version = _detect_primary_batch_version(lote_name, p.get("files", []))
        ts = f"{lote_name}/{detected_version}/{ts_leaf}"

        rel_dir = os.path.join(root, 'analise', lote_name, detected_version, ts_leaf, 'relatorios')
        ent_dir = os.path.join(root, 'analise', lote_name, detected_version, ts_leaf, 'entrada')
        os.makedirs(rel_dir, exist_ok=True)
        os.makedirs(ent_dir, exist_ok=True)

        raw_files = []
        if os.path.exists(lote_dir):
            for dirpath, _, filenames in os.walk(lote_dir):
                for fname in sorted(filenames):
                    if fname.startswith('.') or fname in ('README.md', 'decisoes.yaml'):
                        continue
                    fpath = os.path.join(dirpath, fname)
                    relative_path = os.path.relpath(fpath, lote_dir)
                    raw_files.append((fpath, fname, relative_path))

        roles_map = _classify_batch_document_roles(
            lote_name, [r[2] for r in raw_files], primary_files=primary_files
        )

        baseline_files = []
        external_inputs = []
        documents = []
        fpath_by_rel = {}
        for fpath, fname, relative_path in raw_files:
            h = calculate_file_hash(fpath)
            sz = os.path.getsize(fpath)
            role = roles_map.get(relative_path, "alvo_principal")
            if role == "insumo_externo":
                external_inputs.append({
                    "name": clean_unicode_text(fname),
                    "path": relative_path,
                    "sha256": h,
                    "size_bytes": sz,
                    "role": "insumo_externo",
                })
                continue
            baseline_files.append({
                "name": clean_unicode_text(fname),
                "path": relative_path,
                "sha256": h,
                "size_bytes": sz,
                "role": role,
            })
            extracted = extract_text_from_file(fpath)
            documents.append({
                "name": clean_unicode_text(fname),
                "relative_path": relative_path,
                "ext": os.path.splitext(fname)[1].lower(),
                "text": extracted,
                "sha256": h,
                "role": role,
                "warning": "" if extracted.strip() else "Extracao sem texto retornado.",
            })
            fpath_by_rel[relative_path] = fpath

        target_docs = [d for d in documents if d.get("role") == "alvo_principal"] or documents
        has_supporting_docs = any(d.get("role") == "apoio_cruzamento" for d in documents)

        visual_inventory = visual_pipeline.extract_visual_inventory(
            lote_dir, os.path.join(rel_dir, "visuais"), target_docs)

        skills_ativas = [s["skill"] for s in p.get("skills_recommendation", [])]
        semantic_state = semantic_pipeline.initialize_semantic_state(documents, skills_ativas)

        all_findings = []
        for doc in target_docs:
            fpath = fpath_by_rel.get(doc["relative_path"])
            if not fpath:
                continue
            sf = analyze_document_structure(fpath)
            tf = analyze_document_domain_technical(fpath, skills_ativas)
            all_findings.extend(sf)
            all_findings.extend(tf)

        # Controles individuais executam apenas sobre o(s) documento(s)-alvo principal(is).
        all_findings.extend(specialized_controls.run_specialized_controls(target_docs, skills_ativas))
        all_findings.extend(advanced_specialized_controls.run(target_docs, skills_ativas))
        all_findings.extend(tabular_visual_controls.run(target_docs, skills_ativas))

        # Correlação cruzada usa todo o lote normativo, mas ancora doc_origem no alvo_principal.
        cross_findings = []
        cross_findings.extend(cross_document.run(documents, skills_ativas))
        cross_findings.extend(audit_pipeline.find_cross_document_conflicts(documents))
        if has_supporting_docs and target_docs:
            target_paths = {d["relative_path"] for d in target_docs}
            target_names = {d["name"] for d in target_docs}
            default_target = target_docs[0]
            for cf in cross_findings:
                if cf.get("doc_path") in target_paths or cf.get("doc_origem") in target_names:
                    continue
                matched_src = next(
                    (
                        src for src in (cf.get("evidence_sources") or [])
                        if src.get("document_path") in target_paths or src.get("document_name") in target_names
                    ),
                    None,
                )
                cf["doc_path"] = matched_src["document_path"] if matched_src else default_target["relative_path"]
                cf["doc_origem"] = matched_src["document_name"] if matched_src else default_target["name"]
        all_findings.extend(cross_findings)
        all_findings = audit_pipeline.normalize_findings(lote_name, all_findings, documents)
        coverage = audit_pipeline.build_extraction_coverage(documents)
        # Separa achados por tipo/categoria para enriquecimento dos relatórios
        achados_list = [f for f in all_findings if f.get('tipo') in ('Inconsistência', 'Erro', 'Errata/Estrutura', 'Ambiguidade')]
        lacunas_list = [f for f in all_findings if f.get('tipo') == 'Lacuna']
        riscos_list = [f for f in all_findings if f.get('tipo') == 'Risco']

        # Gera perguntas formais para lacunas e riscos de prioridade P0/P1
        esclarecimentos_list = []
        for idx, item in enumerate(lacunas_list + riscos_list, 1):
            qid = f'Q-{idx:03d}'
            esclarecimentos_list.append({
                'id': qid,
                'id_pergunta': f'PERG-{idx:03d}',
                'finding_id': item.get('id', ''),
                'doc': item.get('doc_origem', lote_name),
                'doc_ref': item.get('doc_origem', lote_name),
                'secao_ref': item.get('loc', 'Geral'),
                'pergunta': f"Favor esclarecer a seguinte pendência identificada no documento: {item.get('title')} ({item.get('fato')})",
                'impacto': item.get('impacto', 'Mitigação de risco operacional e normativo.'),
                'justificativa': item.get('impacto', 'Mitigação de risco operacional e normativo.'),
                'destinatario': item.get('proprietario', 'Comissão Técnica / Gestor do Processo')
            })

        review_comments = comments_extractor.extract_all_comments_from_lote(lote_dir)
        if review_comments:
            comments_extractor.export_comments_artifacts(review_comments, rel_dir)

        data = {
            'title': f"{lote_name.replace('_', ' ')}",
            'timestamp': ts,
            'metadata': {
                'lote': lote_name,
                'versao_documento': detected_version,
                'timestamp': ts_leaf,
            },
            'baseline_files': baseline_files,
            'external_inputs': external_inputs,
            'review_comments': review_comments,
            'achados': all_findings,
            'lacunas': lacunas_list,
            'riscos': riscos_list,
            'redacoes': [],
            'erratas': [],
            'esclarecimentos': esclarecimentos_list,
            'checklists_status': audit_pipeline.build_checklist_status(p.get('active_checklists', []), all_findings, coverage),
            'skills_ativas': skills_ativas,
            'iqd_denominador': audit_engine.compute_checklist_denominator(root, p.get('active_checklists', []), len(target_docs)),
            'schema_version': audit_pipeline.SCHEMA_VERSION,
            'cobertura_extracao': coverage,
            'visual_inventory': visual_inventory,
            'visual_analysis': {'status': visual_inventory['visual_analysis_status'], 'findings_recorded': 0},
            'semantic_analysis': semantic_state,
            'execucao_skills': [{'skill': skill, 'status': (
                ('ativos_visuais_extraidos_aguardando_interpretacao' if visual_inventory['asset_count'] else 'executada_sem_ativos_visuais')
                if skill == 'analisar-diagramas' else
                ('executada_com_controles' if skill in ('analisar-documento', 'analisar-rfp', 'analisar-hld', 'analisar-carrier', 'analisar-lld', 'analisar-contrato', 'analisar-planilha', 'analisar-integracoes', 'analisar-lgpd', 'analisar-cloud', 'analisar-datacenter') else 'selecionada_sem_regra_automatica')
            ), 'semantic_status': (
                'canal_visual_separado' if skill == 'analisar-diagramas' else
                ('pendente' if any(scope.startswith(f'{skill}::') for scope in semantic_state.get('required_scopes', [])) else 'sem_escopo_textual')
            )} for skill in skills_ativas],
        }

        parecer = audit_engine.generate_6_reports(rel_dir, data)
        html_compiler.compile_timestamp_html(ts, root_dir=root)
        results.append({"lote": lote_name, "timestamp": ts, "parecer": parecer,
                        "files_count": len(baseline_files),
                        "visual_assets_count": visual_inventory["asset_count"],
                        "visual_analysis_status": visual_inventory["visual_analysis_status"]})

    master_res = json.loads(tool_build_master_index())

    return json.dumps({
        "status": "success",
        "total_processed": len(results),
        "lotes_processed": results,
        "master_html": master_res.get("master_html")
    }, indent=2, ensure_ascii=False)


def tool_get_visual_assets(timestamp: str, offset: int = 0, limit: int = 6) -> list[dict]:
    """Entrega imagens do inventário ao cliente MCP como conteúdo multimodal."""
    if not _is_valid_analysis_identifier(timestamp):
        raise ValueError("Timestamp de análise inválido.")
    limit = max(1, min(int(limit), 8))
    offset = max(0, int(offset))
    root = get_workspace_root()
    _, report_dir, _, _ = _resolve_analysis_dirs(root, timestamp)
    inventory_path = os.path.join(report_dir, "inventario_visual.json")
    if not os.path.isfile(inventory_path):
        raise FileNotFoundError("Inventário visual não encontrado para essa análise.")
    with open(inventory_path, "r", encoding="utf-8") as stream:
        inventory = json.load(stream)
    assets = inventory.get("assets", [])
    selected = assets[offset:offset + limit]
    content = [{"type": "text", "text": json.dumps({
        "status": "success", "analysis_timestamp": timestamp,
        "offset": offset, "limit": limit, "total_assets": len(assets),
        "has_more": offset + len(selected) < len(assets),
        "instruction": "Inspecione cada imagem visualmente. Descreva elementos observáveis e compare com o texto do documento. Só registre contradição E3 quando houver trecho textual literal de confronto.",
        "assets": [{k: asset.get(k) for k in ("asset_id", "source_document", "kind", "page", "file", "sha256", "width", "height", "ocr_status", "ocr_text")} for asset in selected]
    }, ensure_ascii=False, indent=2)}]
    for asset in selected:
        relative = asset.get("file", "")
        path = os.path.abspath(os.path.join(report_dir, relative))
        if os.path.commonpath([os.path.abspath(report_dir), path]) != os.path.abspath(report_dir):
            raise ValueError("Caminho de ativo visual inválido.")
        try:
            encoded, mime = visual_pipeline.make_mcp_image(path)
            content.append({"type": "image", "data": encoded, "mimeType": mime})
        except ValueError as exc:
            content.append({"type": "text", "text": f"{asset.get('asset_id')}: pré-visualização não disponível ({exc}). Metadados e texto estruturado permanecem no inventário."})
    return content


def tool_record_visual_analysis(timestamp: str, reviewed_asset_ids: list[str], findings: list[dict]) -> str:
    """Persiste achados multimodais vinculados a imagens e recompila o HTML."""
    if not _is_valid_analysis_identifier(timestamp):
        raise ValueError("Timestamp de análise inválido.")
    if not isinstance(findings, list) or len(findings) > 100:
        raise ValueError("Informe uma lista de até 100 achados visuais.")
    root = get_workspace_root()
    _, rel_dir, ent_dir, rel_path = _resolve_analysis_dirs(root, timestamp)
    json_path = os.path.join(rel_dir, "dados_analise.json")
    inventory_path = os.path.join(rel_dir, "inventario_visual.json")
    if not os.path.isfile(json_path) or not os.path.isfile(inventory_path):
        raise FileNotFoundError("Dados SSOT ou inventário visual não encontrados.")
    with open(json_path, "r", encoding="utf-8") as stream:
        data = json.load(stream)
    with open(inventory_path, "r", encoding="utf-8") as stream:
        inventory = json.load(stream)
    assets = {asset["asset_id"]: asset for asset in inventory.get("assets", [])}
    if not isinstance(reviewed_asset_ids, list):
        raise ValueError("reviewed_asset_ids deve ser uma lista de ativos efetivamente inspecionados.")
    unknown_reviewed = set(reviewed_asset_ids) - set(assets)
    if unknown_reviewed:
        raise ValueError("Ativos marcados como revisados não existem no inventário: " + ", ".join(sorted(unknown_reviewed)))
    accepted_types = {"Lacuna", "Inconsistência", "Risco", "Ambiguidade", "Erro", "Errata/Estrutura"}
    accepted_crit = {"Crítica", "Alta", "Média", "Baixa", "Informativa"}
    accepted_prio = {"P0", "P1", "P2", "P3"}
    existing = data.get("findings", [])
    known_ids = {item.get("id") for item in existing}
    added = []
    import hashlib as _hashlib
    for ordinal, raw in enumerate(findings, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"Achado visual #{ordinal} não é um objeto.")
        asset_id = str(raw.get("asset_id", ""))
        asset = assets.get(asset_id)
        if not asset:
            raise ValueError(f"Ativo visual desconhecido no achado #{ordinal}: {asset_id}")
        if asset_id not in set(reviewed_asset_ids) | set(data.get("visual_analysis", {}).get("assets_reviewed", [])):
            raise ValueError(f"Achado visual #{ordinal} referencia imagem que não foi marcada como revisada.")
        title = str(raw.get("title", "")).strip()
        fact = str(raw.get("fato", "")).strip()
        visual_observation = str(raw.get("observacao_visual", "")).strip()
        finding_type = str(raw.get("tipo", "Lacuna"))
        crit = str(raw.get("criticidade", "Média"))
        prio = str(raw.get("prioridade", "P2"))
        evidence = str(raw.get("evidencia", "E1 (indicação visual)"))
        text_quote = str(raw.get("trecho_textual_correlacionado", "")).strip()
        text_doc_path = str(raw.get("documento_textual_correlacionado", asset.get("source_document", ""))).strip() if asset else ""
        if not title or not fact or not visual_observation:
            raise ValueError(f"Achado visual #{ordinal} precisa de título, fato e observação visual.")
        if finding_type not in accepted_types or crit not in accepted_crit or prio not in accepted_prio:
            raise ValueError(f"Tipo, criticidade ou prioridade inválidos no achado visual #{ordinal}.")
        if evidence.startswith("E3"):
            if not text_quote:
                raise ValueError(f"Achado E3 #{ordinal} exige trecho textual literal para confronto direto.")
            baseline_paths = {str(item.get("path", "")) for item in data.get("baseline_files", [])}
            if text_doc_path not in baseline_paths:
                raise ValueError(f"Documento de confronto do achado E3 #{ordinal} não pertence à baseline.")
            lote_name = _extract_batch_name(timestamp, rel_path)
            candidates = [
                os.path.join(root, "entrada", lote_name, text_doc_path),
                os.path.join(ent_dir, text_doc_path),
                os.path.join(root, "analise", timestamp, "entrada", text_doc_path),
                os.path.join(root, "entrada", text_doc_path),
            ]
            source_path = next((path for path in candidates if os.path.isfile(path)), None)
            if not source_path:
                raise ValueError(f"Documento textual do achado E3 #{ordinal} não está acessível para conferir a citação.")
            source_text = extract_text_from_file(source_path)
            normalized_source = re.sub(r"\s+", " ", source_text).strip().casefold()
            normalized_quote = re.sub(r"\s+", " ", text_quote).strip().casefold()
            if not normalized_quote or normalized_quote not in normalized_source:
                raise ValueError(f"Trecho textual do achado E3 #{ordinal} não foi localizado literalmente no documento informado.")
        source = asset.get("source_document", "")
        page = asset.get("page")
        location = f"Imagem {asset_id}" + (f", página {page}" if page else "")
        citation = f"Observação visual: {visual_observation}. Arquivo de evidência: {asset.get('file')}; SHA-256: {asset.get('sha256')}."
        if text_quote:
            citation += f" Trecho textual correlacionado ({text_doc_path}): {text_quote}"
        material = "|".join((timestamp, asset_id, title, visual_observation, text_quote))
        fid = "VIS-" + _hashlib.sha256(material.encode("utf-8")).hexdigest()[:8].upper()
        if fid in known_ids:
            continue
        finding = {
            "id": fid, "title": title, "doc_origem": source, "loc": location,
            "categoria": "Diagrama/Imagem", "tipo": finding_type, "evidencia": evidence,
            "citacao": citation, "evidencia_literal": citation, "localizacao_exata": location,
            "doc_path": source, "rule_id": str(raw.get("rule_id", "VISUAL-001")),
            "criticidade": crit, "prioridade": prio, "fato": fact,
            "impacto": str(raw.get("impacto", "A topologia ou semântica do fluxo precisa ser esclarecida.")),
            "solucao": str(raw.get("solucao", "")), "de": "", "para": "", "is_direct": False,
            "proprietario": str(raw.get("proprietario", "Arquitetura / Engenharia")),
            "visual_asset_id": asset_id, "visual_file": asset.get("file"),
            "visual_sha256": asset.get("sha256"), "visual_page": page,
            "texto_afirmado": str(raw.get("texto_afirmado", "")).strip(),
            "diagrama_demonstrado": str(raw.get("diagrama_demonstrado", "")).strip(),
        }
        added.append(finding)
        known_ids.add(fid)

    all_findings = existing + added
    data["findings"] = all_findings
    prior_reviewed = set(data.get("visual_analysis", {}).get("assets_reviewed", []))
    reviewed = sorted(prior_reviewed | set(reviewed_asset_ids))
    visual_status = "concluída" if set(assets).issubset(reviewed) else "parcial"
    total_visual_findings = sum(bool(item.get("visual_asset_id")) for item in all_findings)
    data["visual_analysis"] = {"status": visual_status, "findings_recorded": total_visual_findings,
                               "assets_reviewed": reviewed}
    for skill in data.get("execucao_skills", []):
        if skill.get("skill") == "analisar-diagramas":
            skill["status"] = "interpretação visual concluída" if visual_status == "concluída" else "interpretação visual parcial"
    inventory["visual_analysis_status"] = visual_status
    inventory["visual_findings_recorded"] = total_visual_findings
    inventory["assets_reviewed"] = reviewed
    data["visual_inventory"] = inventory
    with open(inventory_path, "w", encoding="utf-8") as stream:
        json.dump(inventory, stream, ensure_ascii=False, indent=2)
    master = _refresh_analysis_outputs(data, timestamp, root)
    return json.dumps({"status": "success", "timestamp": timestamp,
                       "visual_findings_added": len(added), "total_findings": len(all_findings),
                       "assets_reviewed": len(reviewed), "assets_total": len(assets),
                       "visual_analysis_status": visual_status,
                       "parecer": data["parecer"], "master_html": master.get("master_html")},
                      ensure_ascii=False, indent=2)


def _safe_baseline_path(base_dir: str, relative_path: str) -> str:
    """Resolve um arquivo relativo e impede saída da pasta de baseline."""
    if not relative_path or os.path.isabs(relative_path):
        raise ValueError("Caminho de documento deve ser relativo à baseline.")
    base = os.path.realpath(base_dir)
    candidate = os.path.realpath(os.path.join(base, relative_path))
    try:
        if os.path.commonpath([base, candidate]) != base:
            raise ValueError("Caminho de documento fora da baseline.")
    except ValueError as exc:
        raise ValueError("Caminho de documento fora da baseline.") from exc
    return candidate


def _resolve_baseline_document(root: str, timestamp: str, baseline_entry: dict) -> tuple[str, str]:
    """Localiza a cópia que ainda corresponde ao SHA-256 congelado."""
    _, _, ent_dir, rel_path = _resolve_analysis_dirs(root, timestamp)
    batch_name = _extract_batch_name(timestamp, rel_path)
    relative_path = str(baseline_entry.get("path", ""))
    expected_hash = str(baseline_entry.get("sha256", ""))
    bases = [
        os.path.join(root, "entrada", batch_name),
        ent_dir,
        os.path.join(root, "analise", timestamp, "entrada"),
        os.path.join(root, "entrada"),
    ]
    mismatched = []
    for base in bases:
        candidate = _safe_baseline_path(base, relative_path)
        if not os.path.isfile(candidate):
            continue
        actual_hash = calculate_file_hash(candidate)
        if actual_hash == expected_hash:
            return candidate, actual_hash
        mismatched.append(candidate)
    if mismatched:
        raise ValueError(f"Integridade da baseline divergente para {relative_path}; nenhuma cópia corresponde ao hash congelado.")
    raise FileNotFoundError(f"Arquivo da baseline não acessível: {relative_path}.")


def _extract_semantic_review_text(fpath: str) -> str:
    """Extrai texto com marcadores de página/parágrafo/linha para orientar a localização."""
    ext = os.path.splitext(fpath)[1].lower()
    if ext == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(fpath)
            parts = []
            for index, page in enumerate(reader.pages, 1):
                page_text = (page.extract_text() or "").strip()
                if page_text:
                    parts.append(f"[Página PDF {index}]\n{page_text}")
                annots = _extract_pdf_annotations(page, index)
                if annots:
                    parts.append("\n".join(annots))
            return "\n\n".join(parts)
        except Exception:
            return ""
    if ext == ".docx":
        try:
            _, located_lines = _extract_docx_lines(fpath)
            return "\n".join(located_lines)
        except Exception:
            return ""
    if ext in (".xlsx", ".xls"):
        try:
            sheets = extract_xlsx_data(fpath)
            parts = []
            for sheet_name, rows in sheets.items():
                for row_index, row in enumerate(rows, 1):
                    parts.append(f"[Planilha {sheet_name} · linha {row_index}] " + " | ".join(row))
            if ext == ".xlsx":
                parts.extend(extract_xlsx_comments(fpath))
            return "\n".join(parts)
        except Exception:
            return ""
    return extract_text_from_file(fpath)


@lru_cache(maxsize=8)
def _cached_semantic_text(fpath: str, digest: str) -> tuple[str, str]:
    """Evita reprocessar documentos grandes a cada cursor do mesmo hash congelado."""
    return extract_text_from_file(fpath), _extract_semantic_review_text(fpath)


def _load_baseline_document(root: str, timestamp: str, baseline_entry: dict) -> dict:
    source_path, digest = _resolve_baseline_document(root, timestamp, baseline_entry)
    relative_path = str(baseline_entry.get("path", ""))
    raw_text, located_text = _cached_semantic_text(source_path, digest)
    return {
        "name": str(baseline_entry.get("name") or os.path.basename(relative_path)),
        "relative_path": relative_path,
        "ext": os.path.splitext(relative_path)[1].lower(),
        "sha256": digest,
        "role": str(baseline_entry.get("role") or "alvo_principal"),
        "text": raw_text,
        "located_text": located_text,
    }


def _semantic_state_from_report(data: dict) -> dict:
    state = data.get("semantic_analysis")
    if isinstance(state, dict) and isinstance(state.get("required_scopes"), list):
        return state
    coverage_rows = {str(row.get("arquivo", "")): row for row in data.get("cobertura_extracao", {}).get("arquivos", [])}
    documents = []
    for item in data.get("baseline_files", []):
        relative_path = str(item.get("path", ""))
        coverage = coverage_rows.get(relative_path, {})
        ext = os.path.splitext(relative_path)[1].lower()
        documents.append({
            "relative_path": relative_path,
            "ext": ext,
            "role": str(item.get("role") or "alvo_principal"),
            "text": "texto extraído" if coverage.get("status") == "extraido" else "",
        })
    state = semantic_pipeline.initialize_semantic_state(documents, data.get("skills_ativas", []))
    data["semantic_analysis"] = state
    return state


def tool_get_semantic_review_manifest(timestamp: str) -> str:
    """Lista escopos de leitura semântica, baseline e achados existentes para o agente."""
    if not _is_valid_analysis_identifier(timestamp):
        raise ValueError("Timestamp de análise inválido.")
    root = get_workspace_root()
    _, rel_dir, _, _ = _resolve_analysis_dirs(root, timestamp)
    json_path = os.path.join(rel_dir, "dados_analise.json")
    if not os.path.isfile(json_path):
        raise FileNotFoundError("Dados SSOT não encontrados para essa análise.")
    with open(json_path, "r", encoding="utf-8") as stream:
        data = json.load(stream)
    state = _semantic_state_from_report(data)
    required = set(state.get("required_scopes", []))
    reviewed = set(state.get("reviewed_scopes", []))
    scope_results = state.get("scope_results", {})
    grouped = {}
    for key in sorted(required):
        skill, document_path = key.split("::", 1)
        grouped.setdefault(skill, []).append({
            "document_path": document_path,
            "status": scope_results.get(key, {}).get("status", "revisado" if key in reviewed else "pendente"),
            "justificativa": scope_results.get(key, {}).get("justificativa", ""),
        })
    existing = [{
        "id": item.get("id", ""), "title": item.get("title", ""),
        "doc_path": item.get("doc_path", ""), "rule_id": item.get("rule_id", ""),
        "semantic_skill": item.get("semantic_skill", ""),
        "adjudication_status": _finding_adjudication_status(item),
        "adjudication_rationale": (item.get("adjudication") or {}).get("rationale", ""),
    } for item in data.get("findings", [])]
    adjudication = _finding_adjudication_summary(data.get("findings", []))
    result = {
        "status": "success",
        "timestamp": timestamp,
        "semantic_status": state.get("status", "pendente"),
        "required_scope_count": len(required),
        "reviewed_scope_count": len(required & reviewed),
        "pending_scope_count": len(required - reviewed),
        "skills": grouped,
        "baseline_files": [
            {
                "name": str(item.get("name") or os.path.basename(str(item.get("path", "")))),
                "path": str(item.get("path", "")),
                "role": str(item.get("role") or "alvo_principal"),
            }
            for item in data.get("baseline_files", [])
        ],
        "unreadable_documents": state.get("unreadable_documents", []),
        "existing_findings": existing,
        "adjudication_counts": adjudication["counts"],
        "pending_adjudication_count": adjudication["pending"],
        "instruction": "Leia integralmente cada documento por blocos; aplique cada skill ativa como revisão independente; registre somente fatos sustentados por citação literal; adjudique os achados existentes e não trate candidatos pendentes como confirmados.",
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


def tool_get_semantic_document_chunk(timestamp: str, document_path: str, start_char: int = 0,
                                     max_chars: int = 12000) -> str:
    """Retorna um bloco textual de um documento da baseline, com hash e cursor verificáveis."""
    if not _is_valid_analysis_identifier(timestamp):
        raise ValueError("Timestamp de análise inválido.")
    root = get_workspace_root()
    _, rel_dir, _, _ = _resolve_analysis_dirs(root, timestamp)
    json_path = os.path.join(rel_dir, "dados_analise.json")
    if not os.path.isfile(json_path):
        raise FileNotFoundError("Dados SSOT não encontrados para essa análise.")
    with open(json_path, "r", encoding="utf-8") as stream:
        data = json.load(stream)
    entry = next((item for item in data.get("baseline_files", []) if item.get("path") == document_path), None)
    if not entry:
        raise ValueError("document_path não pertence à baseline desta análise.")
    document = _load_baseline_document(root, timestamp, entry)
    if not document["text"].strip():
        return json.dumps({
            "status": "warning", "timestamp": timestamp, "document_path": document_path,
            "sha256": document["sha256"], "message": "Nenhum texto extraível; use o canal visual quando houver ativos visuais e registre a limitação.",
        }, ensure_ascii=False, indent=2)
    chunk = semantic_pipeline.split_text(document["located_text"] or document["text"], start_char, max_chars)
    chunk.update({
        "status": "success", "timestamp": timestamp,
        "document_path": document_path, "document_name": document["name"],
        "extension": document["ext"], "sha256": document["sha256"],
        "citation_rule": "As citações registradas devem ser literais do documento. A localização indicada deve usar a página, parágrafo, planilha/linha ou posição disponibilizada neste bloco.",
    })
    return json.dumps(chunk, ensure_ascii=False, indent=2)


FINDING_ADJUDICATION_STATUSES = {
    "pendente", "confirmado", "falso_positivo", "fora_de_escopo",
    "evidencia_insuficiente", "duplicado",
}
ACTIVE_FINDING_STATUS = "confirmado"


def _finding_adjudication_status(finding: dict) -> str:
    adjudication = finding.get("adjudication")
    status = adjudication.get("status") if isinstance(adjudication, dict) else finding.get("adjudication_status")
    return status if isinstance(status, str) and status in FINDING_ADJUDICATION_STATUSES else "pendente"


def _finding_adjudication_summary(findings: list[dict]) -> dict:
    counts = {status: 0 for status in FINDING_ADJUDICATION_STATUSES}
    for finding in findings:
        counts[_finding_adjudication_status(finding)] += 1
    pending = counts["pendente"] + counts["evidencia_insuficiente"]
    excluded = counts["falso_positivo"] + counts["fora_de_escopo"] + counts["duplicado"]
    return {
        "counts": counts,
        "confirmed": counts["confirmado"],
        "pending": pending,
        "excluded": excluded,
    }


def _refresh_analysis_outputs(data: dict, timestamp: str, root: str, build_master: bool = True) -> dict:
    """Recalcula os derivados SSOT e recompila o relatório individual e o índice mestre."""
    import audit_engine
    findings = data.get("findings", [])
    for finding in findings:
        if _finding_adjudication_status(finding) == "pendente" and not isinstance(finding.get("adjudication"), dict):
            finding["adjudication_status"] = "pendente"
    adjudication = _finding_adjudication_summary(findings)
    confirmed = [item for item in findings if _finding_adjudication_status(item) == ACTIVE_FINDING_STATUS]
    data["adjudication_summary"] = adjudication["counts"]
    data["lacunas"] = [item for item in confirmed if "lacuna" in str(item.get("tipo", "")).lower()]
    data["riscos"] = [item for item in confirmed if "risco" in str(item.get("tipo", "")).lower()]
    questions = data.setdefault("esclarecimentos", [])
    unconfirmed_ids = {
        str(item.get("id", "")) for item in findings
        if _finding_adjudication_status(item) != ACTIVE_FINDING_STATUS
    }
    questions[:] = [
        question for question in questions
        if not (
            str(question.get("finding_id", "")) in unconfirmed_ids
            and (
                str(question.get("pergunta", "")).startswith("Favor esclarecer a seguinte pendência documental:")
                or str(question.get("pergunta", "")).startswith("Favor esclarecer a seguinte pendência identificada no documento:")
            )
        )
    ]
    question_signatures = {
        (str(item.get("finding_id", "")), str(item.get("doc_ref", "")), str(item.get("secao_ref", "")))
        for item in questions
    }
    for finding in data["lacunas"] + data["riscos"]:
        signature = (str(finding.get("id", "")), str(finding.get("doc_origem", "")), str(finding.get("loc", "")))
        if signature in question_signatures or any(
            str(question.get("doc_ref", "")) == signature[1]
            and signature[2] == str(question.get("secao_ref", ""))
            and str(finding.get("title", "")) in str(question.get("pergunta", ""))
            for question in questions
        ):
            continue
        questions.append({
            "id_pergunta": f"PERG-{len(questions) + 1:03d}",
            "finding_id": signature[0],
            "doc_ref": signature[1] or data.get("title", "Lote"),
            "secao_ref": signature[2] or "Localização a confirmar",
            "pergunta": f"Favor esclarecer a seguinte pendência documental: {finding.get('title', '')} ({finding.get('fato', '')})",
            "justificativa": finding.get("impacto", "Mitigação de risco técnico/operacional."),
            "destinatario": finding.get("proprietario", "Engenharia / Arquitetura"),
        })
    kpis = data.setdefault("kpis", {})
    kpis["total_achados"] = len(findings)
    kpis["achados_confirmados"] = adjudication["confirmed"]
    kpis["achados_pendentes_adjudicacao"] = adjudication["pending"]
    kpis["achados_excluidos"] = adjudication["excluded"]
    kpis["lacunas"] = len(data["lacunas"])
    kpis["riscos"] = len(data["riscos"])
    kpis["criticos"] = sum(str(item.get("criticidade", item.get("crit", ""))).upper() == "CRÍTICA" for item in confirmed)
    kpis["altos"] = sum(str(item.get("criticidade", item.get("crit", ""))).upper() == "ALTA" for item in confirmed)
    kpis["medios"] = sum(str(item.get("criticidade", item.get("crit", ""))).upper() == "MÉDIA" for item in confirmed)
    kpis["baixos"] = sum(str(item.get("criticidade", item.get("crit", ""))).upper() in ("BAIXA", "INFORMATIVA") for item in confirmed)
    kpis["estruturais"] = sum(
        1 for item in confirmed
        if any(
            kw in (str(item.get("tipo", "")) + " " + str(item.get("categoria", item.get("cat", "")))).casefold()
            for kw in ("estrutur", "redacional", "rfc 2119", "iso 29148")
        )
    )
    kpis["perguntas"] = len(questions)
    raw_for_calc = [{
        "crit": item.get("criticidade", item.get("crit", "Média")),
        "prio": item.get("prioridade", item.get("prio", "P2")),
    } for item in confirmed]
    if adjudication["pending"]:
        data["parecer"], data["parecer_badge"] = "PENDENTE DE ADJUDICAÇÃO", "PENDENTE"
    else:
        data["parecer"], data["parecer_badge"] = audit_engine.calculate_parecer(raw_for_calc, data["lacunas"])
    data["decision_status"] = "pendente_adjudicacao" if adjudication["pending"] else "concluido"
    target_count = sum(
        1 for item in data.get("baseline_files", [])
        if item.get("role", "alvo_principal") == "alvo_principal"
    ) or len(data.get("baseline_files", []))
    denom = kpis.get("iqd_denominador", max(target_count * 15, 30))
    if adjudication["pending"]:
        kpis["iqd"] = "—"
        kpis["iqd_denominador"] = denom
    else:
        _, kpis["iqd"], kpis["iqd_denominador"] = audit_engine.calculate_iqd(raw_for_calc, denom)
    _, rel_dir, _, rel_path = _resolve_analysis_dirs(root, timestamp)
    json_path = os.path.join(rel_dir, "dados_analise.json")
    with open(json_path, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
    html_compiler.compile_timestamp_html(rel_path, root_dir=root)
    return json.loads(tool_build_master_index()) if build_master else {}


def _validate_adjudication_evidence(finding: dict, sources: list[dict], data: dict,
                                    timestamp: str, root: str, visual_corroboration: bool = False) -> list[dict]:
    """Valida citação/localização contra o hash congelado antes de confirmar achado textual."""
    if not isinstance(sources, list) or not sources:
        raise ValueError("Confirmar um achado exige evidence_sources com citação e localização verificáveis.")
    if len(sources) > semantic_pipeline.MAX_EVIDENCE_SOURCES:
        raise ValueError(f"Um achado pode ter no máximo {semantic_pipeline.MAX_EVIDENCE_SOURCES} fontes de evidência.")
    baseline_entries = {str(item.get("path", "")): item for item in data.get("baseline_files", [])}
    loaded = {}
    validated = []
    signatures = set()
    for index, source in enumerate(sources, 1):
        if not isinstance(source, dict):
            raise ValueError(f"Fonte de evidência #{index} deve ser um objeto.")
        path = str(source.get("document_path", "")).strip()
        quote = str(source.get("quote", "")).strip()
        location = str(source.get("location", "")).strip()
        if path not in baseline_entries:
            raise ValueError(f"Documento de evidência não pertence à baseline: {path or '(vazio)' }.")
        if not quote or len(quote) > semantic_pipeline.MAX_QUOTE:
            raise ValueError(f"Citação #{index} vazia ou acima de {semantic_pipeline.MAX_QUOTE} caracteres.")
        normalized_location = semantic_pipeline.normalize_evidence_text(location)
        if not location or len(location) < 2 or normalized_location in {
            "localização a confirmar", "localizacao a confirmar", "a confirmar",
            "localização desconhecida", "localizacao desconhecida",
        } or "confirmar seção/página" in normalized_location or "confirmar secao/pagina" in normalized_location:
            raise ValueError(f"Fonte de evidência #{index} precisa de localização específica.")
        if path not in loaded:
            loaded[path] = _load_baseline_document(root, timestamp, baseline_entries[path])
        document = loaded[path]
        provided_hash = str(source.get("sha256", "")).strip()
        if provided_hash and provided_hash.lower() != str(document.get("sha256", "")).lower():
            raise ValueError(f"Hash divergente na fonte de evidência #{index}: {path}.")
        located_text = document.get("located_text", "")
        raw_text = document.get("text", "")
        if not (
            semantic_pipeline.quote_is_literal(located_text, quote)
            or semantic_pipeline.quote_is_literal(raw_text, quote)
        ):
            raise ValueError(f"Citação #{index} não localizada literalmente na baseline {path}.")
        signature = (path, semantic_pipeline.normalize_evidence_text(quote))
        if signature in signatures:
            raise ValueError(f"Fonte de evidência #{index} duplica citação já informada para {path}.")
        signatures.add(signature)
        validated.append({
            "document_path": path,
            "document_name": document["name"],
            "location": location,
            "quote": quote,
            "sha256": document["sha256"],
        })

    evidence_level = str(finding.get("evidencia", "E1")).strip().upper().split()[0]
    criticality = str(finding.get("criticidade", finding.get("crit", ""))).strip().casefold()
    if evidence_level not in semantic_pipeline.ALLOWED_EVIDENCE:
        raise ValueError("O grau de evidência precisa começar com E1, E2 ou E3.")
    if criticality in {"crítica", "alta"} and evidence_level == "E1":
        raise ValueError("Achados críticos/altos exigem evidência E2 ou E3 para confirmação.")
    if evidence_level == "E3" and len(validated) < (1 if visual_corroboration else 2):
        raise ValueError("Evidência E3 exige duas citações literais ou, com ativo visual validado, uma citação textual de confronto.")
    valid_references = []
    for reference in (finding.get("referencias") or []):
        if isinstance(reference, str) and reference.strip():
            valid_references.append(reference.strip())
        elif isinstance(reference, dict):
            ref_title = str(reference.get("titulo", "")).strip()
            ref_url = str(reference.get("url", "")).strip()
            ref_note = str(reference.get("nota", "")).strip()
            if ref_url and not ref_url.startswith(("https://", "http://")):
                continue
            if ref_title or ref_url or ref_note:
                valid_references.append(reference)
    if evidence_level == "E2" and len(validated) < (1 if visual_corroboration else 2) and not valid_references:
        raise ValueError("Evidência E2 exige duas citações literais ou referência técnica corroborativa.")
    return validated


def tool_adjudicate_findings(timestamp: str, decisions: list[dict]) -> str:
    """Registra a decisão de revisão para achados, preservando os candidatos e a trilha de auditoria."""
    if not _is_valid_analysis_identifier(timestamp):
        raise ValueError("Timestamp de análise inválido.")
    if not isinstance(decisions, list) or not decisions or len(decisions) > 200:
        raise ValueError("Informe uma lista de 1 a 200 decisões de adjudicação.")
    root = get_workspace_root()
    _, rel_dir, _, _ = _resolve_analysis_dirs(root, timestamp)
    json_path = os.path.join(rel_dir, "dados_analise.json")
    if not os.path.isfile(json_path):
        raise FileNotFoundError("Dados SSOT não encontrados para essa análise.")
    with open(json_path, "r", encoding="utf-8") as stream:
        data = json.load(stream)
    findings_by_id = {str(item.get("id", "")): item for item in data.get("findings", [])}
    submitted_ids = set()
    normalized_decisions = []
    for index, decision in enumerate(decisions, 1):
        if not isinstance(decision, dict):
            raise ValueError(f"Decisão #{index} deve ser um objeto.")
        finding_id = str(decision.get("finding_id", "")).strip()
        status = str(decision.get("status", "")).strip()
        rationale = str(decision.get("rationale", "")).strip()
        if not finding_id or finding_id not in findings_by_id:
            raise ValueError(f"Achado não encontrado nesta análise: {finding_id or '(ID vazio)'}.")
        if finding_id in submitted_ids:
            raise ValueError(f"Achado informado mais de uma vez: {finding_id}.")
        if status not in FINDING_ADJUDICATION_STATUSES:
            raise ValueError(f"Status de adjudicação inválido: {status or '(vazio)'}.")
        if status != "pendente" and len(rationale) < 20:
            raise ValueError(f"A decisão {status} exige justificativa de pelo menos 20 caracteres.")
        related_id = str(decision.get("related_finding_id", "")).strip()
        if status == "duplicado" and (not related_id or related_id == finding_id or related_id not in findings_by_id):
            raise ValueError("Marcar como duplicado exige related_finding_id de outro achado existente.")
        submitted_ids.add(finding_id)
        normalized_decisions.append((finding_id, status, rationale, related_id, decision))

    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    for finding_id, status, rationale, related_id, decision in normalized_decisions:
        finding = findings_by_id[finding_id]
        metadata = {
            "status": status,
            "rationale": rationale,
            "adjudicated_at": now,
            "reviewer": str(decision.get("reviewer", "revisor")).strip()[:120] or "revisor",
        }
        if related_id:
            metadata["related_finding_id"] = related_id
        if status == "confirmado":
            sources = decision.get("evidence_sources") or finding.get("evidence_sources")
            evidence_level = str(finding.get("evidencia", "E1")).strip().upper().split()[0]
            criticality = str(finding.get("criticidade", finding.get("crit", ""))).strip().casefold()
            if evidence_level not in semantic_pipeline.ALLOWED_EVIDENCE:
                raise ValueError("O grau de evidência precisa começar com E1, E2 ou E3.")
            if criticality in {"crítica", "alta"} and evidence_level == "E1":
                raise ValueError("Achados críticos/altos exigem evidência E2 ou E3 para confirmação.")
            if finding.get("visual_asset_id"):
                inventory_assets = {
                    str(asset.get("asset_id")): asset for asset in data.get("visual_inventory", {}).get("assets", [])
                    if isinstance(asset, dict)
                }
                asset_id = str(finding.get("visual_asset_id"))
                asset = inventory_assets.get(asset_id, {})
                reviewed_assets = set(data.get("visual_analysis", {}).get("assets_reviewed", []))
                if asset_id not in reviewed_assets or str(asset.get("sha256", "")) != str(finding.get("visual_sha256", "")):
                    raise ValueError(f"Evidência visual de {finding_id} não corresponde a ativo revisado e hash da baseline.")
                metadata["verified_visual_evidence"] = {
                    "asset_id": asset_id, "sha256": str(finding.get("visual_sha256", "")),
                    "location": str(finding.get("loc", "")),
                }
                if evidence_level in {"E2", "E3"}:
                    finding["evidence_sources"] = _validate_adjudication_evidence(
                        finding, sources, data, timestamp, root, visual_corroboration=True)
            else:
                finding["evidence_sources"] = _validate_adjudication_evidence(
                    finding, sources, data, timestamp, root)
        finding["adjudication"] = metadata

    result = _refresh_analysis_outputs(data, timestamp, root)
    summary = _finding_adjudication_summary(data.get("findings", []))
    return json.dumps({
        "status": "success", "timestamp": timestamp,
        "decisions_recorded": len(normalized_decisions),
        "adjudication_counts": summary["counts"],
        "pending_adjudication": summary["pending"],
        "parecer": data.get("parecer"),
        "master_html": result.get("master_html"),
    }, ensure_ascii=False, indent=2)


def _sanitize_executive_summary(raw_summary: dict) -> dict:
    """Normaliza e limita campos estruturados do resumo executivo para o SSOT."""
    if not isinstance(raw_summary, dict):
        return {}
    cleaned: dict = {}
    for str_key in ("assunto_email", "destinatario_sugerido", "avaliacao_maturidade", "conclusao_executiva", "justificativa_parecer"):
        if str_key in raw_summary and raw_summary.get(str_key) is not None:
            val = clean_unicode_text(str(raw_summary.get(str_key)).strip())[:5000]
            if val:
                cleaned[str_key] = val
    for list_key in ("pontos_fortes", "acoes_exigidas"):
        raw_list = raw_summary.get(list_key)
        if isinstance(raw_list, list):
            items = [clean_unicode_text(str(x).strip())[:1000] for x in raw_list if str(x).strip()]
            if items:
                cleaned[list_key] = items[:30]
    raw_frag = raw_summary.get("fragilidades_por_dominio")
    if isinstance(raw_frag, list):
        frag_items = []
        for grp in raw_frag[:20]:
            if not isinstance(grp, dict):
                continue
            dom = clean_unicode_text(str(grp.get("dominio") or "").strip())[:300]
            ids = [clean_unicode_text(str(i).strip())[:64] for i in (grp.get("ids") or []) if str(i).strip()][:30]
            itens = [clean_unicode_text(str(it).strip())[:1500] for it in (grp.get("itens") or []) if str(it).strip()][:30]
            if dom and (itens or ids):
                frag_items.append({"dominio": dom, "ids": ids, "itens": itens})
        if frag_items:
            cleaned["fragilidades_por_dominio"] = frag_items
    return cleaned


def tool_record_semantic_analysis(timestamp: str, reviewed_scopes: list[dict], findings: list[dict], executive_summary: dict = None) -> str:
    """Registra a revisão semântica, valida citações contra a baseline e recompila os relatórios."""
    if not _is_valid_analysis_identifier(timestamp):
        raise ValueError("Timestamp de análise inválido.")
    if not isinstance(reviewed_scopes, list) or len(reviewed_scopes) > 1000:
        raise ValueError("reviewed_scopes deve ser uma lista de até 1000 escopos.")
    if not isinstance(findings, list) or len(findings) > 100:
        raise ValueError("Informe uma lista de até 100 achados semânticos por chamada.")
    root = get_workspace_root()
    _, rel_dir, _, rel_path = _resolve_analysis_dirs(root, timestamp)
    json_path = os.path.join(rel_dir, "dados_analise.json")
    if not os.path.isfile(json_path):
        raise FileNotFoundError("Dados SSOT não encontrados para essa análise.")
    with open(json_path, "r", encoding="utf-8") as stream:
        data = json.load(stream)
    state = _semantic_state_from_report(data)
    required = set(state.get("required_scopes", []))
    active_skills = set(data.get("skills_ativas", [])) - semantic_pipeline.VISUAL_SKILLS
    accepted_scopes = set()
    submitted_scope_results = {}
    for index, item in enumerate(reviewed_scopes, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Escopo revisado #{index} deve ser um objeto.")
        skill = str(item.get("skill", "")).strip()
        document_path = str(item.get("document_path", "")).strip()
        key = semantic_pipeline.scope_key(skill, document_path)
        if key not in required:
            raise ValueError(f"Escopo não previsto na matriz semântica: {skill} / {document_path}.")
        outcome = str(item.get("status", "revisado")).strip()
        rationale = str(item.get("justificativa", "")).strip()
        if outcome not in {"revisado", "não_aplicável", "não_verificável"}:
            raise ValueError(f"Status do escopo semântico inválido: {outcome}.")
        if outcome in {"não_aplicável", "não_verificável"} and len(rationale) < 20:
            raise ValueError(f"O escopo {outcome} exige justificativa de pelo menos 20 caracteres.")
        submitted_scope_results[key] = {"status": outcome, "justificativa": rationale}
        if outcome != "não_verificável":
            accepted_scopes.add(key)

    all_reviewed_scopes = set(state.get("reviewed_scopes", [])) | accepted_scopes
    for key, result in submitted_scope_results.items():
        if result.get("status") == "não_verificável":
            all_reviewed_scopes.discard(key)
    all_scope_results = dict(state.get("scope_results", {}))
    all_scope_results.update(submitted_scope_results)
    baseline_entries = {str(item.get("path", "")): item for item in data.get("baseline_files", [])}
    has_primary_targets = any(entry.get("role") == "alvo_principal" for entry in baseline_entries.values())
    target_entries = [entry for entry in baseline_entries.values() if entry.get("role") == "alvo_principal"]
    primary_target_doc = None
    if len(target_entries) == 1:
        t_entry = target_entries[0]
        t_path = str(t_entry.get("path", ""))
        primary_target_doc = {
            "name": str(t_entry.get("name") or os.path.basename(t_path)),
            "relative_path": t_path,
        }
    loaded_sources = {}
    normalized_candidates = []
    batch_name = _extract_batch_name(timestamp, rel_path)
    for ordinal, raw in enumerate(findings, 1):
        if not isinstance(raw, dict):
            raise ValueError(f"Achado semântico #{ordinal} deve ser um objeto.")
        raw_sources = raw.get("evidence_sources")
        if not isinstance(raw_sources, list) or not raw_sources:
            raw_sources = [{
                "document_path": raw.get("document_path", raw.get("doc_path", "")),
                "quote": raw.get("quote", raw.get("citacao", "")),
                "location": raw.get("localizacao_exata", raw.get("loc", "")),
            }]
        skill = str(raw.get("skill", "")).strip()
        source_paths = set()
        for source in raw_sources:
            source_path = str(source.get("document_path", "")).strip() if isinstance(source, dict) else ""
            if source_path not in baseline_entries:
                raise ValueError(f"Documento de evidência não pertence à baseline: {source_path or '(vazio)' }.")
            source_paths.add(source_path)
            if source_path not in loaded_sources:
                loaded_sources[source_path] = _load_baseline_document(root, timestamp, baseline_entries[source_path])
        if skill not in active_skills:
            raise ValueError(f"Skill do achado semântico não está ativa: {skill or '(vazia)'}.")
        missing_source_scopes = []
        for path in source_paths:
            key = semantic_pipeline.scope_key(skill, path)
            doc_role = str(baseline_entries[path].get("role", "alvo_principal"))
            if key not in required and has_primary_targets and doc_role == "apoio_cruzamento":
                continue
            outcome = all_scope_results.get(key, {}).get("status", "revisado" if key in all_reviewed_scopes else "pendente")
            if outcome != "revisado":
                missing_source_scopes.append(path)
        skill_required_scopes = {k for k in required if k.startswith(f"{skill}::")}
        if skill_required_scopes and not any(
            semantic_pipeline.scope_key(skill, path) in required for path in source_paths
        ):
            if not any(
                all_scope_results.get(k, {}).get("status", "revisado" if k in all_reviewed_scopes else "pendente") == "revisado"
                for k in skill_required_scopes
            ):
                missing_source_scopes.append(sorted(source_paths)[0])
        if missing_source_scopes:
            raise ValueError(f"A fonte do achado não foi marcada como revisada/aplicável para {skill}: {', '.join(sorted(missing_source_scopes))}.")
        normalized_candidates.append(semantic_pipeline.normalize_semantic_finding(
            raw, loaded_sources, active_skills, batch_name, primary_target_doc=primary_target_doc))

    existing = data.get("findings", [])
    known_ids = {item.get("id") for item in existing}
    exact_signatures = {
        (str(item.get("semantic_skill", "")), str(item.get("rule_id", "")),
         str(item.get("doc_path", "")), semantic_pipeline.normalize_evidence_text(item.get("title", "")))
        for item in existing
    }
    added = []
    for finding in normalized_candidates:
        signature = (finding["semantic_skill"], finding["rule_id"], finding["doc_path"],
                     semantic_pipeline.normalize_evidence_text(finding["title"]))
        if finding["id"] in known_ids or signature in exact_signatures:
            continue
        added.append(finding)
        known_ids.add(finding["id"])
        exact_signatures.add(signature)

    state["reviewed_scopes"] = sorted(all_reviewed_scopes)
    state["scope_results"] = all_scope_results
    expected_count = len(required)
    reviewed_count = len(required & all_reviewed_scopes)
    unreadable = state.get("unreadable_documents", [])
    has_non_verifiable_scope = any(item.get("status") == "não_verificável" for item in all_scope_results.values())
    if expected_count == 0:
        state["status"] = "não_verificável" if unreadable else "não_aplicável"
    elif reviewed_count == expected_count:
        state["status"] = "concluída com limitações" if unreadable or has_non_verifiable_scope else "concluída"
    elif reviewed_count:
        state["status"] = "parcial"
    else:
        state["status"] = "pendente"
    state["reviewed_scope_count"] = reviewed_count
    state["pending_scope_count"] = expected_count - reviewed_count
    state["findings_recorded"] = sum(bool(item.get("semantic_skill")) for item in existing + added)
    data["semantic_analysis"] = state
    data["findings"] = existing + added
    for skill_row in data.get("execucao_skills", []):
        skill = skill_row.get("skill")
        if skill == "analisar-diagramas":
            continue
        skill_required = {key for key in required if key.startswith(f"{skill}::")}
        skill_reviewed = skill_required & all_reviewed_scopes
        if skill_required:
            skill_row["semantic_status"] = "concluída" if skill_required.issubset(skill_reviewed) else ("parcial" if skill_reviewed else "pendente")

    if isinstance(executive_summary, dict) and executive_summary:
        sanitized_summary = _sanitize_executive_summary(executive_summary)
        if sanitized_summary:
            cur_summary = data.get("resumo_executivo") if isinstance(data.get("resumo_executivo"), dict) else {}
            cur_summary.update(sanitized_summary)
            data["resumo_executivo"] = cur_summary

    master = _refresh_analysis_outputs(data, timestamp, root)
    return json.dumps({
        "status": "success", "timestamp": timestamp,
        "semantic_status": state["status"],
        "scopes_reviewed": reviewed_count, "scopes_total": expected_count,
        "scopes_pending": expected_count - reviewed_count,
        "findings_added": len(added), "findings_total": len(data["findings"]),
        "semantic_findings_total": state["findings_recorded"],
        "master_html": master.get("master_html"),
    }, ensure_ascii=False, indent=2)


def tool_extract_docx_summary(filename: str, lote_path: str = None) -> str:
    """Extrai parágrafos, tabelas e mídias de um .docx."""
    root = get_workspace_root()
    base = os.path.join(root, lote_path) if lote_path else os.path.join(root, 'entrada')
    fpath = os.path.join(base, filename)

    if not os.path.exists(fpath):
        return json.dumps({"status": "error", "message": f"Arquivo não encontrado: {fpath}"}, ensure_ascii=False)

    try:
        z = zipfile.ZipFile(fpath)
        doc_xml = z.read('word/document.xml')
        tree = ET.fromstring(doc_xml)
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        paragraphs = tree.findall('.//w:p', ns)
        tables = tree.findall('.//w:tbl', ns)
        media = [f for f in z.namelist() if f.startswith('word/media/')]
        # Extrai headings para estrutura
        headings = []
        for p in paragraphs:
            style = p.find('.//w:pStyle', ns)
            if style is not None:
                val = style.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', '')
                if 'Heading' in val or 'heading' in val or 'Título' in val:
                    texts = [r.text or '' for r in p.findall('.//w:t', ns)]
                    heading_text = ''.join(texts).strip()
                    if heading_text:
                        headings.append(heading_text)
        return json.dumps({
            "status": "success", "filename": filename,
            "paragraphs_count": len(paragraphs), "tables_count": len(tables),
            "media_count": len(media), "media_files": media,
            "headings": headings[:30]
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)


def tool_extract_xlsx_summary(filename: str, lote_path: str = None) -> str:
    """Extrai abas e dados de um .xlsx."""
    root = get_workspace_root()
    base = os.path.join(root, lote_path) if lote_path else os.path.join(root, 'entrada')
    fpath = os.path.join(base, filename)

    if not os.path.exists(fpath):
        return json.dumps({"status": "error", "message": f"Arquivo não encontrado: {fpath}"}, ensure_ascii=False)

    try:
        data = extract_xlsx_data(fpath)
        if not data:
            return json.dumps({
                "status": "warning",
                "message": "openpyxl não disponível ou arquivo vazio. Instale: pip install openpyxl",
                "filename": filename
            }, ensure_ascii=False)

        sheets_summary = {}
        for sheet_name, rows in data.items():
            headers = rows[0] if rows else []
            sheets_summary[sheet_name] = {
                "headers": headers,
                "row_count": len(rows) - 1,
                "sample_rows": rows[1:4]
            }
        return json.dumps({"status": "success", "filename": filename, "sheets": sheets_summary},
                          indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)


def _get_relatorios_dir(root: str, timestamp: str = None) -> tuple:
    analysis_dir, rel_dir, ent_dir, rel_path = _resolve_analysis_dirs(root, timestamp)
    return rel_dir, rel_path


def tool_validate_analise_contract(timestamp: str = None) -> str:
    """Valida se os entregáveis da RTI (index.html e dados_analise.json) existem em analise/<timestamp>/relatorios/
    ou analise/<lote>/<version>/<timestamp>/relatorios/ e verifica a cobertura de skills recomendadas em relação a decisoes.yaml."""
    root = get_workspace_root()
    rel_dir, ts = _get_relatorios_dir(root, timestamp)

    required = [
        "index.html",
        "dados_analise.json"
    ]

    results = {"status": "success", "timestamp": ts, "path": rel_dir,
               "total_required": len(required), "found": 0, "missing": [], "files": [],
               "validation_warnings": []}

    for rfile in required:
        fpath = os.path.join(rel_dir, rfile)
        exists = os.path.exists(fpath)
        size = os.path.getsize(fpath) if exists else 0
        if exists:
            results["found"] += 1
            results["files"].append({"file": rfile, "status": "ok", "size_bytes": size})
        else:
            # Tenta fallback se existirem os relatórios md legados
            if rfile == "dados_analise.json" and os.path.exists(os.path.join(rel_dir, "00_RESUMO_EXECUTIVO.md")):
                results["found"] += 1
                results["files"].append({"file": rfile, "status": "ok (fallback md)", "size_bytes": 0})
            else:
                results["missing"].append(rfile)
                results["files"].append({"file": rfile, "status": "missing"})

    # Validação de schema SSOT e cobertura de skills em dados_analise.json
    data_json_path = os.path.join(rel_dir, "dados_analise.json")
    decisoes_yaml_path = os.path.join(root, "entrada", "decisoes.yaml")

    if os.path.exists(data_json_path):
        try:
            with open(data_json_path, 'r', encoding='utf-8') as f:
                analise_data = json.load(f)
            for schema_msg in schemas.validate_dados_analise_schema(analise_data):
                if schema_msg not in results["validation_warnings"]:
                    results["validation_warnings"].append(schema_msg)

            if os.path.exists(decisoes_yaml_path):
                skills_ativas = set(analise_data.get("skills_ativas", []))

                # Tentar achar o lote correspondente no decisoes.yaml
                clean_ts = ts.split('/')[-1]
                lote_id = clean_ts.split('_', 2)[2] if len(clean_ts.split('_', 2)) > 2 else clean_ts
                with open(decisoes_yaml_path, 'r', encoding='utf-8') as f:
                    decisoes_content = f.read()

                if lote_id:
                    lote_blocks = decisoes_content.split('  - id: ')
                    for block in lote_blocks:
                        if block.startswith(f'"{lote_id}"') or block.startswith(f"'{lote_id}'") or block.startswith(lote_id):
                            for line in block.splitlines():
                                if 'skill:' in line:
                                    sk_name = line.split('skill:')[1].strip().strip('"').strip("'")
                                    if sk_name and sk_name not in skills_ativas:
                                        msg = f"Skill recomendada '{sk_name}' em decisoes.yaml não foi incluída em 'skills_ativas' do lote {lote_id}."
                                        if msg not in results["validation_warnings"]:
                                            results["validation_warnings"].append(msg)
        except Exception as e:
            results["validation_warnings"].append(f"Aviso ao validar contrato/skills de dados_analise.json: {str(e)}")

    if results["missing"]:
        results["status"] = "incomplete"
    elif results["validation_warnings"]:
        results["status"] = "success_with_warnings"

    return json.dumps(results, indent=2, ensure_ascii=False)


def tool_finalize_execution(timestamp: str, lote: str = None, version: str = None) -> str:
    """
    Move arquivos do lote analisado de entrada/<lote> para analise/<lote>/<version>/<timestamp>/entrada/
    e atualiza o portal master index.
    """
    root = get_workspace_root()
    entrada_dir = os.path.join(root, 'entrada')

    if not timestamp:
        return json.dumps({"status": "error", "message": "Parâmetro timestamp é obrigatório."}, ensure_ascii=False)

    analysis_dir, rel_dir, dest_entrada, rel_path = _resolve_analysis_dirs(root, timestamp)
    os.makedirs(dest_entrada, exist_ok=True)

    parts = rel_path.split('/')
    if len(parts) >= 3:
        detected_lote = parts[0]
        detected_version = parts[1]
    elif len(parts) == 2:
        detected_lote = parts[0]
        detected_version = version or "v1.0"
    else:
        detected_lote = lote or _extract_batch_name(timestamp, rel_path)
        detected_version = version or "v1.0"

    moved = []
    src_lote_dir = os.path.join(entrada_dir, detected_lote) if detected_lote else entrada_dir
    if detected_lote and not os.path.isdir(src_lote_dir):
        src_lote_dir = entrada_dir

    json_path = os.path.join(rel_dir, "dados_analise.json")
    baseline_filenames = []
    if os.path.isfile(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                d = json.load(f)
                for bf in d.get("baseline_files", []):
                    fn = bf.get("name") or os.path.basename(bf.get("path", ""))
                    if fn:
                        baseline_filenames.append(fn)
        except Exception:
            pass

    if os.path.isdir(src_lote_dir):
        for dirpath, _, filenames in os.walk(src_lote_dir):
            for item in sorted(filenames):
                if item.startswith('.') or item in ('README.md', 'decisoes.yaml'):
                    continue
                src = os.path.join(dirpath, item)
                rel_item = os.path.relpath(src, src_lote_dir).replace('\\', '/')
                if baseline_filenames and item not in baseline_filenames and rel_item not in baseline_filenames:
                    continue
                dst = os.path.join(dest_entrada, rel_item)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                os.remove(src)
                moved.append(f"{detected_lote}/{rel_item}" if detected_lote else rel_item)

        rem_files = []
        for dirpath, _, filenames in os.walk(src_lote_dir):
            for f in filenames:
                if not f.startswith('.') and f not in ('README.md', 'decisoes.yaml'):
                    rem_files.append(f)
        if not rem_files and src_lote_dir != entrada_dir:
            try:
                shutil.rmtree(src_lote_dir)
            except Exception:
                pass

    gitkeep = os.path.join(entrada_dir, '.gitkeep')
    if not os.path.exists(gitkeep):
        with open(gitkeep, 'w') as f:
            f.write('')

    html_result = tool_build_run_index_html(rel_path)
    master_result = tool_build_master_index()

    return json.dumps({
        "status": "success", "timestamp": rel_path,
        "moved": moved, "dest_entrada": dest_entrada,
        "html": json.loads(html_result),
        "master": json.loads(master_result)
    }, indent=2, ensure_ascii=False)


def tool_build_run_index_html(timestamp: str) -> str:
    """Compila o HTML executivo da análise a partir do dados_analise.json SSOT."""
    root = get_workspace_root()
    analysis_dir, rel_dir, ent_dir, rel_path = _resolve_analysis_dirs(root, timestamp)

    if not os.path.exists(rel_dir):
        return json.dumps({"status": "error", "message": f"Diretório não encontrado: {rel_dir}"}, ensure_ascii=False)

    try:
        sys.path.insert(0, os.path.dirname(__file__))
        import html_compiler
        result = html_compiler.compile_timestamp_html(rel_path, root_dir=root)
        return json.dumps({"status": "success", "message": result}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)


def tool_create_review_revision(source_analysis: str, reason: str = "Ajuste e Adjudicação de Relatório", reviewer: str = "auditor") -> str:
    """
    Cria uma nova rodada de revisão/adjudicação a partir de um relatório existente,
    preservando o histórico e gerando um novo timestamp na mesma versão de documento:
    analise/<lote>/<version>/<novo_timestamp>/
    """
    root = get_workspace_root()
    src_dir, src_rel, src_ent, src_relpath = _resolve_analysis_dirs(root, source_analysis)
    
    if not os.path.isdir(src_dir) or not os.path.isdir(src_rel):
        return json.dumps({"status": "error", "message": f"Análise de origem não encontrada: {source_analysis}"}, ensure_ascii=False)
        
    src_json = os.path.join(src_rel, "dados_analise.json")
    if not os.path.isfile(src_json):
        return json.dumps({"status": "error", "message": "dados_analise.json não encontrado na análise de origem."}, ensure_ascii=False)
        
    with open(src_json, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    parts = src_relpath.split('/')
    if len(parts) >= 3:
        lote = parts[0]
        version = parts[1]
    elif len(parts) == 2:
        lote = parts[0]
        version = data.get("metadata", {}).get("versao_documento", "v1.0")
    else:
        lote = data.get("metadata", {}).get("lote") or _extract_batch_name(source_analysis, src_relpath) or "lote_geral"
        version = data.get("metadata", {}).get("versao_documento", "v1.0")

    now = datetime.datetime.now()
    new_ts = now.strftime("%Y%m%d_%H%M%S") + "_revisao"
    
    dest_dir = os.path.join(root, "analise", lote, version, new_ts)
    dest_rel = os.path.join(dest_dir, "relatorios")
    dest_ent = os.path.join(dest_dir, "entrada")
    
    os.makedirs(dest_rel, exist_ok=True)
    os.makedirs(dest_ent, exist_ok=True)
    
    if os.path.isdir(src_ent):
        for dirpath, _, filenames in os.walk(src_ent):
            for item in sorted(filenames):
                s = os.path.join(dirpath, item)
                rel_item = os.path.relpath(s, src_ent)
                d = os.path.join(dest_ent, rel_item)
                os.makedirs(os.path.dirname(d), exist_ok=True)
                shutil.copy2(s, d)

    src_visuais = os.path.join(src_rel, "visuais")
    dest_visuais = os.path.join(dest_rel, "visuais")
    if os.path.isdir(src_visuais) and not os.path.exists(dest_visuais):
        shutil.copytree(src_visuais, dest_visuais)

    src_inv = os.path.join(src_rel, "inventario_visual.json")
    if os.path.isfile(src_inv):
        shutil.copy2(src_inv, os.path.join(dest_rel, "inventario_visual.json"))
        
    audit_trail = data.get("audit_trail", [])
    audit_trail.append({
        "event": "revision_created",
        "parent_analysis": src_relpath,
        "created_at": now.isoformat(),
        "reason": reason,
        "reviewer": reviewer
    })
    data["audit_trail"] = audit_trail
    data["parent_analysis"] = src_relpath
    data["timestamp"] = f"{lote}/{version}/{new_ts}"
    data["revision_timestamp"] = new_ts
    if "metadata" not in data or not isinstance(data["metadata"], dict):
        data["metadata"] = {}
    data["metadata"]["timestamp"] = new_ts
    data["metadata"]["lote"] = lote
    data["metadata"]["versao_documento"] = version
    data["metadata"]["rodada_tipo"] = "revisao_adjudicada"
    
    dest_json = os.path.join(dest_rel, "dados_analise.json")
    with open(dest_json, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        
    import html_compiler
    new_relpath = f"{lote}/{version}/{new_ts}"
    evo_res = html_compiler.compile_evolution_html(new_relpath, root_dir=root)
    html_compiler.compile_timestamp_html(new_relpath, root_dir=root)
    if src_relpath != new_relpath:
        html_compiler.compile_timestamp_html(src_relpath, root_dir=root)
    tool_build_master_index()
    
    return json.dumps({
        "status": "success",
        "message": "Nova rodada de revisão criada com sucesso.",
        "parent_analysis": src_relpath,
        "new_analysis_path": new_relpath,
        "new_timestamp": new_ts,
        "relatorios_dir": dest_rel,
        "html_url": f"{new_relpath}/relatorios/index.html",
        "evolution_html": evo_res.get("evolution_html", "")
    }, indent=2, ensure_ascii=False)


def tool_reconcile_versions(
    previous_timestamp: str,
    current_timestamp: str,
    summary_notes: str = "",
    external_audit_disposition: list[dict] = None,
) -> str:
    """
    Compara duas rodadas/versões de análise (previous_timestamp vs current_timestamp),
    gera o relatório evolutivo dedicado (evolucao.html) e o Quadro de Reconciliação Técnica
    (novos, refinados, expurgados/saneados e reincidentes), persiste em dados_analise.json
    e recompila os relatórios HTML sem embutir o diff no corpo do relatório principal.
    """
    if not _is_valid_analysis_identifier(previous_timestamp) or not _is_valid_analysis_identifier(current_timestamp):
        raise ValueError("Identificadores de análise inválidos para reconciliação de versões.")
    root = get_workspace_root()
    _, prev_rel, _, prev_relpath = _resolve_analysis_dirs(root, previous_timestamp)
    _, curr_rel, _, curr_relpath = _resolve_analysis_dirs(root, current_timestamp)

    prev_json_path = os.path.join(prev_rel, "dados_analise.json")
    curr_json_path = os.path.join(curr_rel, "dados_analise.json")
    if not os.path.isfile(prev_json_path) or not os.path.isfile(curr_json_path):
        raise FileNotFoundError("dados_analise.json não encontrado em uma das versões informadas.")

    with open(prev_json_path, "r", encoding="utf-8") as f:
        prev_data = json.load(f)
    with open(curr_json_path, "r", encoding="utf-8") as f:
        curr_data = json.load(f)

    import audit_engine
    import html_compiler
    reconciliation = audit_engine.reconcile_versions(
        prev_data,
        curr_data,
        summary_notes=summary_notes,
        external_audit_disposition=external_audit_disposition,
    )
    curr_data["version_reconciliation"] = reconciliation
    with open(curr_json_path, "w", encoding="utf-8") as f:
        json.dump(curr_data, f, indent=2, ensure_ascii=False)

    evo_res = html_compiler.compile_evolution_html(curr_relpath, root_dir=root)
    html_compiler.compile_timestamp_html(curr_relpath, root_dir=root)
    if prev_relpath != curr_relpath:
        html_compiler.compile_timestamp_html(prev_relpath, root_dir=root)
    tool_build_master_index()
    return json.dumps({
        "status": "success",
        "previous_analysis": prev_relpath,
        "current_analysis": curr_relpath,
        "evolution_html": evo_res.get("evolution_html", ""),
        "reconciliation": reconciliation,
    }, indent=2, ensure_ascii=False)


def tool_export_executive_email(timestamp: str, output_filename: str = None) -> str:
    """Exporta sob demanda a minuta de e-mail executivo (.md) para a pasta raiz do lote em analise/."""
    if not _is_valid_analysis_identifier(timestamp):
        raise ValueError("Timestamp de análise inválido.")
    root = get_workspace_root()
    analysis_dir, rel_dir, _, rel_path = _resolve_analysis_dirs(root, timestamp)
    json_path = os.path.join(rel_dir, "dados_analise.json")
    if not os.path.isfile(json_path):
        raise FileNotFoundError("dados_analise.json não encontrado para essa análise.")
    with open(json_path, "r", encoding="utf-8") as stream:
        data = json.load(stream)

    import html_compiler
    email_model = html_compiler.build_executive_email_model(data)

    parts = [p for p in rel_path.replace("\\", "/").split("/") if p]
    target_dir = os.path.join(root, "analise", parts[0]) if len(parts) >= 2 else analysis_dir
    os.makedirs(target_dir, exist_ok=True)

    if output_filename and str(output_filename).strip():
        raw_name = str(output_filename).strip()
        if "/" in raw_name or "\\" in raw_name or ".." in raw_name:
            raise ValueError("output_filename deve ser apenas o nome do arquivo, sem caminhos ou '..'.")
        fname = raw_name if raw_name.lower().endswith(".md") else f"{raw_name}.md"
    else:
        ver = str((data.get("metadata") or {}).get("versao_documento") or "v1.0").strip()
        safe_lote = re.sub(r"[^a-zA-Z0-9_-]+", "_", parts[0]).strip("_").lower() if parts else "lote"
        fname = f"email_resumo_analise_{safe_lote}_{ver}.md"

    out_path = os.path.join(target_dir, fname)
    real_dir = os.path.realpath(target_dir)
    real_out = os.path.realpath(out_path)
    if os.path.commonpath([real_dir, real_out]) != real_dir:
        raise ValueError("Caminho de saída do e-mail inválido.")

    with open(out_path, "w", encoding="utf-8") as stream:
        stream.write(email_model["markdown"])

    return json.dumps({
        "status": "success",
        "timestamp": rel_path,
        "email_file": out_path,
        "assunto": email_model["assunto"],
        "parecer": email_model["parecer"],
        "iqd": email_model["iqd"],
    }, indent=2, ensure_ascii=False)


def tool_build_master_index() -> str:
    """
    Recompila o arquivo analise/index.html (Central Master) e o analise/manifest.json
    escaneando todas as subpastas YYYYMMDD_HHMMSS_* em analise/.
    """
    root = get_workspace_root()
    analise_dir = os.path.join(root, 'analise')
    manifest_path = os.path.join(analise_dir, 'manifest.json')
    master_html_path = os.path.join(analise_dir, 'index.html')
    template_path = os.path.join(root, 'framework', 'templates', 'master_index_template.html')

    if not os.path.exists(analise_dir):
        return json.dumps({"status": "error", "message": "Pasta analise/ não encontrada."})

    runs = []

    # Escaneia pastas de relatórios suportando profundidade tripla:
    # analise/<lote>/<version>/<timestamp>/relatorios/, analise/<lote>/<timestamp>/ ou analise/<timestamp>/
    candidates = []
    for dirpath, dirnames, filenames in os.walk(analise_dir):
        if os.path.basename(dirpath) == 'relatorios' and ('dados_analise.json' in filenames or 'index.html' in filenames):
            run_dir = os.path.dirname(dirpath)
            rel_p = os.path.relpath(run_dir, analise_dir).replace('\\', '/')
            parts = rel_p.split('/')
            if len(parts) >= 3:
                lote_p = parts[0]
                version_p = parts[1]
                ts_p = parts[2]
            elif len(parts) == 2:
                lote_p = parts[0]
                version_p = "v1.0"
                ts_p = parts[1]
            else:
                lote_p = None
                version_p = "v1.0"
                ts_p = parts[0]
            candidates.append({
                "ts": ts_p,
                "version": version_p,
                "lote_parent": lote_p,
                "ts_dir": run_dir,
                "rel_dir": dirpath,
                "rel_path": rel_p
            })
    candidates.sort(key=lambda c: c["ts"], reverse=True)

    for cand in candidates:
        ts = cand["ts"]
        version = cand["version"]
        lote_parent = cand["lote_parent"]
        ts_dir = cand["ts_dir"]
        rel_dir = cand["rel_dir"]
        rel_path = cand["rel_path"]
        json_path = os.path.join(rel_dir, 'dados_analise.json')
        resumo_path = os.path.join(rel_dir, '00_RESUMO_EXECUTIVO.md')

        # Formata data
        date_str = ts
        if len(ts) >= 15 and ts[:8].isdigit():
            date_str = f"{ts[6:8]}/{ts[4:6]}/{ts[:4]} às {ts[9:11]}:{ts[11:13]}:{ts[13:15]}"

        # Extrai nome do lote do sufixo do timestamp ou da pasta pai
        if lote_parent:
            lote_name = clean_unicode_text(lote_parent.replace('_', ' '))
        else:
            parts = ts.split('_', 2)
            raw_lote_name = parts[2].replace('_', ' ') if len(parts) > 2 else ts
            lote_name = clean_unicode_text(raw_lote_name)
        title = clean_unicode_text(f"Revisão Técnica — {lote_name}")

        # Extrai dados do JSON ou Markdown
        data_json = {}
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data_json = json.load(f)
            except Exception:
                pass

        # Migra relatórios legados para o estado fail-safe: achados sem adjudicação ficam pendentes.
        if data_json and isinstance(data_json.get("findings"), list) and data_json.get("findings"):
            adjudication_state = _finding_adjudication_summary(data_json["findings"])
            current_kpis = data_json.get("kpis") or {}
            expected_decision_status = "pendente_adjudicacao" if adjudication_state["pending"] else "concluido"
            needs_adjudication_sync = (
                data_json.get("adjudication_summary") != adjudication_state["counts"]
                or data_json.get("decision_status") != expected_decision_status
                or current_kpis.get("achados_confirmados") != adjudication_state["confirmed"]
                or current_kpis.get("achados_pendentes_adjudicacao") != adjudication_state["pending"]
                or current_kpis.get("achados_excluidos") != adjudication_state["excluded"]
                or (adjudication_state["pending"] and current_kpis.get("iqd") != "—")
            )
            if needs_adjudication_sync:
                _refresh_analysis_outputs(data_json, rel_path, root, build_master=False)

        if data_json:
            import audit_engine
            kpis = data_json.get("kpis") or data_json.get("metadata", {}) or {}
            achados_list = data_json.get("findings") or data_json.get("achados", [])
            adjudication = _finding_adjudication_summary(achados_list)
            confirmed_findings = [a for a in achados_list if _finding_adjudication_status(a) == ACTIVE_FINDING_STATUS]
            total_achados = len(achados_list)
            criticos = sum(1 for a in confirmed_findings if str(a.get("criticidade", a.get("crit", ""))).casefold() == "crítica")
            lacunas = sum(1 for a in confirmed_findings if "lacuna" in str(a.get("tipo", "")).casefold())
            risks = [a for a in confirmed_findings if "risco" in str(a.get("tipo", "")).casefold()]
            if adjudication["pending"]:
                parecer = "PENDENTE DE ADJUDICAÇÃO"
            else:
                active_for_calc = [{
                    "crit": a.get("criticidade", a.get("crit", "Média")),
                    "prio": a.get("prioridade", a.get("prio", "P2")),
                } for a in confirmed_findings]
                parecer = audit_engine.calculate_parecer(active_for_calc, [a for a in confirmed_findings if "lacuna" in str(a.get("tipo", "")).casefold()])[0]
            parecer = clean_unicode_text(parecer)
            iqd = kpis.get("iqd") or data_json.get("metadata", {}).get("iqd", "—")
            skills_found = data_json.get("skills_ativas", ["analisar-documento"])

            b_files = data_json.get("baseline_files") or data_json.get("files") or data_json.get("metadata", {}).get("baseline_files") or []
            json_files = []
            for f in b_files:
                if isinstance(f, dict):
                    fn = f.get("name") or f.get("filename") or f.get("path") or ""
                    if fn:
                        json_files.append(clean_unicode_text(os.path.basename(fn)))
                elif isinstance(f, str):
                    json_files.append(clean_unicode_text(os.path.basename(f)))

            # Coleta do Top 3 Achados de Risco (Críticos / P0 / P1 / Altos)
            top_achados = []
            for a in confirmed_findings:
                crit_val = a.get('criticidade') or a.get('crit', '')
                prio_val = a.get('prioridade') or a.get('prio', '')
                if crit_val in ('Crítica', 'Alta') or prio_val in ('P0', 'P1'):
                    t_title = clean_unicode_text(a.get('title', 'Achado Relevante'))
                    t_doc = clean_unicode_text(a.get('doc_origem', ''))
                    t_imp = clean_unicode_text(a.get('impacto', ''))
                    top_achados.append({
                        'id': clean_unicode_text(a.get('id', 'ACH-000')),
                        'title': t_title,
                        'doc': t_doc,
                        'impacto': t_imp[:120] + '...' if len(t_imp) > 120 else t_imp
                    })
                    if len(top_achados) >= 3:
                        break
            if not top_achados and confirmed_findings:
                for a in confirmed_findings[:2]:
                    t_title = clean_unicode_text(a.get('title', 'Achado Relevante'))
                    t_doc = clean_unicode_text(a.get('doc_origem', ''))
                    t_imp = clean_unicode_text(a.get('impacto', ''))
                    top_achados.append({
                        'id': clean_unicode_text(a.get('id', 'ACH-000')),
                        'title': t_title,
                        'doc': t_doc,
                        'impacto': t_imp[:120] + '...' if len(t_imp) > 120 else t_imp
                    })

            # Breakdown
            altos = sum(1 for a in confirmed_findings if (a.get("criticidade") or a.get("crit")) == "Alta")
            medios = sum(1 for a in confirmed_findings if (a.get("criticidade") or a.get("crit")) in ("Média", "Media"))
            estrutura_cnt = sum(1 for a in confirmed_findings if (
                (a.get("tipo") or "") in ("Errata/Estrutura", "Estrutura / Numeração", "Integridade Redacional e Estrutural") or
                (a.get("cat") or "") in ("Integridade Redacional e Estrutural", "Governança de Documento", "Qualidade Editorial")
            ))
            de_para_cnt = sum(1 for a in confirmed_findings if (
                a.get("is_direct") is True or
                bool(a.get("de") and a.get("para")) or
                (a.get("tipo_solucao") or "") in ("De → Para (Minuta)", "De->Para", "Minuta Sugerida") or
                bool(a.get("texto_sugerido"))
            ))
            perguntas_cnt = len(data_json.get("esclarecimentos") or data_json.get("perguntas") or [])
            if perguntas_cnt == 0:
                perguntas_cnt = sum(1 for a in achados_list if (a.get("id_acao") or "").startswith("Q-") or (a.get("id") or "").startswith("Q-"))

            # Diagnóstico Executivo Dinâmico e Específico por Lote
            resumo_snippet = (
                data_json.get("resumo_executivo", {}).get("justificativa_parecer")
                or data_json.get("metadata", {}).get("justificativa_parecer")
                or data_json.get("metadata", {}).get("descricao_parecer")
            )
            if adjudication["pending"]:
                resumo_snippet = (
                    f"Parecer pendente de adjudicação: {adjudication['pending']} achado(s) aguardam validação. "
                    f"{adjudication['confirmed']} confirmado(s), {adjudication['excluded']} excluído(s) com justificativa."
                )
            elif not resumo_snippet:
                if "NÃO APTO" in parecer.upper():
                    if top_achados:
                        resumo_snippet = f"Análise concluída com parecer **NÃO APTO PARA DECISÃO**. Lote bloqueado por {criticos} achado(s) crítico(s) e {altos} de alta severidade, destacando-se: {top_achados[0]['title']} ({top_achados[0]['id']})."
                    else:
                        resumo_snippet = f"Análise concluída com parecer **NÃO APTO PARA DECISÃO** devido a inconsistências técnicas e lacunas de alto impacto no lote ({total_achados} achados)."
                else:
                    if top_achados:
                        resumo_snippet = f"Análise concluída com parecer **APTO COM RESSALVAS** (IQD {iqd}). Requer atenção técnica para: {top_achados[0]['title']} ({top_achados[0]['id']})."
                    else:
                        resumo_snippet = f"Análise concluída com parecer **APTO COM RESSALVAS** (IQD {iqd}). Documentação consistente, registrando apenas {total_achados} apontamento(s) de menor gravidade."
            resumo_snippet = clean_unicode_text(resumo_snippet)

        else:
            resumo_txt = ""
            if os.path.exists(resumo_path):
                with open(resumo_path, 'r', encoding='utf-8', errors='ignore') as f:
                    resumo_txt = f.read()
            parecer = _extract_value(resumo_txt, r'Parecer[^:]*:\s*\*?\*?([A-ZÁÉÍÓÚÃÕÇ /]+)\*?\*?', "APTO COM RESSALVAS")
            total_achados = int(_extract_value(resumo_txt, r'Total de Achados\s*\|\s*\*\*(\d+)\*\*', "0"))
            criticos = int(_extract_value(resumo_txt, r'Críticos[^|]*\|\s*\*\*(\d+)\*\*', "0"))
            lacunas = int(_extract_value(resumo_txt, r'Lacunas[^|]*\|\s*\*\*(\d+)\*\*', "0"))
            iqd = _extract_value(resumo_txt, r'IQD[^|]*\|\s*\*\*([0-9,.]+%|—)\*\*', "—")
            skills_found = re.findall(r'`(analisar-[a-z0-9-]+)`', resumo_txt) or ["analisar-documento"]
            skills_found = sorted(list(set(skills_found)))
            json_files = []
            resumo_snippet = "Análise técnica realizada sobre a baseline do lote."
            top_achados = []
            altos = 0
            medios = 0
            estrutura_cnt = 0
            de_para_cnt = 0
            perguntas_cnt = 0

        if not resumo_snippet:
            resumo_snippet = "Análise técnica e auditoria de integridade realizadas sobre a baseline do lote."

        if len(resumo_snippet) > 320:
            resumo_snippet = resumo_snippet[:320] + "..."

        # Lista arquivos de entrada
        ent_dir = os.path.join(analise_dir, rel_path, 'entrada')
        entrada_files = []
        if os.path.exists(ent_dir):
            for dirpath, _, filenames in os.walk(ent_dir):
                for fname in sorted(filenames):
                    if not fname.startswith('.'):
                        entrada_files.append(clean_unicode_text(fname))
        if not entrada_files and json_files:
            entrada_files = json_files

        evolucao_rel_path = ""
        rel_evolucao_file = os.path.join(rel_dir, "evolucao.html")
        ver_evolucao_file = os.path.join(analise_dir, lote_parent, version, "evolucao.html") if lote_parent else ""
        has_version_history = bool(
            data_json.get("version_reconciliation")
            or data_json.get("parent_analysis")
            or data_json.get("audit_trail")
        )
        if not os.path.isfile(rel_evolucao_file) and has_version_history:
            try:
                import html_compiler
                html_compiler.compile_evolution_html(rel_path, root_dir=root)
            except Exception:
                pass
        if os.path.isfile(rel_evolucao_file):
            evolucao_rel_path = f"{rel_path}/relatorios/evolucao.html"
        elif ver_evolucao_file and os.path.isfile(ver_evolucao_file):
            evolucao_rel_path = f"{lote_parent}/{version}/evolucao.html"

        runs.append({
            "timestamp": ts,
            "version": version,
            "is_revision": "revisao" in ts.lower() or bool(data_json.get("audit_trail")),
            "date_formatted": date_str,
            "title": title,
            "lote_name": lote_name,
            "parecer": parecer,
            "pending_adjudication": adjudication["pending"] if data_json else 0,
            "files": entrada_files,
            "skills": skills_found,
            "resumo_snippet": resumo_snippet,
            "top_achados": top_achados,
            "lote_parent": lote_parent,
            "rel_path": rel_path,
            "index_html": f"{rel_path}/relatorios/index.html",
            "evolution_html": evolucao_rel_path,
            "metrics": {
                "total_achados": total_achados,
                "confirmados": adjudication["confirmed"] if data_json else 0,
                "pendentes_adjudicacao": adjudication["pending"] if data_json else 0,
                "excluidos": adjudication["excluded"] if data_json else 0,
                "criticos": criticos,
                "altos": altos,
                "medios": medios,
                "lacunas": lacunas,
                "estrutura": estrutura_cnt,
                "de_para": de_para_cnt,
                "perguntas": perguntas_cnt,
                "iqd": iqd
            }
        })

    latest_runs = []
    seen_lotes = set()
    for r in runs:
        lote_key = r.get("lote_parent") or r.get("lote_name") or r["timestamp"]
        if lote_key not in seen_lotes:
            seen_lotes.add(lote_key)
            latest_runs.append(r)

    manifest = {
        "updated_at": datetime.datetime.now().isoformat(),
        "total_analyses": len(runs),
        "total_unique_lotes": len(latest_runs),
        "analyses": runs
    }

    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Recompila master HTML
    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()

        cards_html = ""
        rows_html = ""
        
        runs_nao_apto = sum(1 for r in runs if "NÃO APTO" in r["parecer"].upper())
        runs_pendentes = sum(1 for r in runs if "PENDENTE DE ADJUDICAÇÃO" in r["parecer"].upper())
        runs_ressalvas = sum(1 for r in runs if "RESSALVA" in r["parecer"].upper())
        total_criticos = sum(r["metrics"]["criticos"] for r in latest_runs)
        total_lacunas = sum(r["metrics"]["lacunas"] for r in latest_runs)
        
        # Média numérica do IQD considerando a rodada mais recente de cada lote
        iqd_nums = []
        for r in latest_runs:
            v_str = r["metrics"]["iqd"].replace('%', '').replace(',', '.').strip()
            try:
                iqd_nums.append(float(v_str))
            except ValueError:
                pass
        avg_iqd_str = f"{sum(iqd_nums)/len(iqd_nums):.1f}%" if iqd_nums else "—"

        for r in runs:
            m = r["metrics"]
            files_html = ", ".join([f'<code>{html.escape(str(fn))}</code>' for fn in r["files"][:3]]) or "<code>Baseline</code>"
            if len(r["files"]) > 3:
                files_html += f" (+{len(r['files'])-3} arquivos)"

            skills_html = "".join([f'<span class="skill-badge"><i class="fa-solid fa-wand-magic-sparkles"></i> {html.escape(str(sk))}</span>' for sk in r["skills"]])

            parecer_upper = r["parecer"].upper()
            if "NÃO APTO" in parecer_upper:
                parecer_cls = "badge-nao-apto"
                card_status_cls = "nao-apto"
            elif "PENDENTE DE ADJUDICAÇÃO" in parecer_upper:
                parecer_cls = "badge-pendente"
                card_status_cls = "pendente"
            elif "RESSALVA" in parecer_upper:
                parecer_cls = "badge-ressalvas"
                card_status_cls = "ressalvas"
            else:
                parecer_cls = "badge-apto"
                card_status_cls = "apto"

            # Top Achados HTML
            top_achados_html = ""
            if r["top_achados"]:
                items_html = ""
                for ta in r["top_achados"]:
                    items_html += f"""
                    <li class="top-achado-item">
                      <span class="top-achado-id">{html.escape(str(ta['id']))}</span>
                      <div><strong>{html.escape(str(ta['title']))}</strong> <span style="font-size:0.75rem; color:#b91c1c;">({html.escape(str(ta['doc']))})</span></div>
                    </li>"""
                top_achados_html = f"""
                <div class="top-achados-box">
                    <div class="top-achados-title"><i class="fa-solid fa-triangle-exclamation"></i> Principais Achados de Risco (Top P0/P1):</div>
                    <ul class="top-achados-list">
                      {items_html}
                    </ul>
                </div>"""

            search_str = f"{r['timestamp']} {r['title']} {r['lote_name']} {r['date_formatted']} {' '.join(r['skills'])} {r['resumo_snippet']} {card_status_cls}".lower()
            safe_search_str = html.escape(search_str, quote=True)

            escaped_resumo = html.escape(str(r['resumo_snippet']))
            resumo_html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', escaped_resumo)
            resumo_html = re.sub(r'`(.*?)`', r'<code>\1</code>', resumo_html).replace('**', '')

            esc_date = html.escape(str(r['date_formatted']))
            esc_title = html.escape(str(r['title']))
            esc_version = html.escape(str(r.get('version', 'v1.0')))
            esc_parecer = html.escape(str(r['parecer']))
            esc_ts = html.escape(str(r['timestamp']))
            esc_lote = html.escape(str(r['lote_name']))
            esc_iqd = html.escape(str(m['iqd']))
            safe_href = html.escape(str(r['index_html']), quote=True)
            safe_evo_href = html.escape(str(r.get('evolution_html') or ''), quote=True)
            evo_card_btn = (
                f' <a href="{safe_evo_href}" class="btn-open-report" style="background:#7c3aed; flex:1 1 170px;">'
                f'<i class="fa-solid fa-code-compare"></i> Evolução de Versões</a>'
                if safe_evo_href else ""
            )
            evo_row_btn = (
                f' <a href="{safe_evo_href}" class="btn-open-report" style="padding:6px 10px; font-size:0.75rem; background:#7c3aed;">'
                f'<i class="fa-solid fa-code-compare"></i> Evolução</a>'
                if safe_evo_href else ""
            )

            cards_html += f"""
            <div class="run-card {card_status_cls}" data-search="{safe_search_str}" data-parecer="{card_status_cls}">
                <div class="run-card-header">
                    <div>
                        <div class="run-date"><i class="fa-solid fa-calendar-day"></i> {esc_date}</div>
                        <h3 class="run-title">{esc_title} <span class="skill-badge" style="background:#e0f2fe; color:#0369a1; border:1px solid #bae6fd; font-size:0.75rem;"><i class="fa-solid fa-code-branch"></i> {esc_version}</span>{' <span class="skill-badge" style="background:#fef3c7; color:#92400e; border:1px solid #fde68a; font-size:0.75rem;"><i class="fa-solid fa-clock-rotate-left"></i> Revisão Adjudicada</span>' if r.get('is_revision') else ''}</h3>
                    </div>
                    <span class="badge {parecer_cls}">{esc_parecer}</span>
                </div>
                <div class="run-body">
                    <div class="run-files">
                        <div class="files-label"><i class="fa-solid fa-folder-tree"></i> Arquivos da Baseline ({len(r['files'])}):</div>
                        <div class="file-item">{files_html}</div>
                    </div>

                    <div class="resumo-snippet-box">
                        <div class="resumo-snippet-title"><i class="fa-solid fa-file-contract"></i> Diagnóstico Executivo & Justificativa:</div>
                        <p>{resumo_html}</p>
                    </div>

                    {top_achados_html}

                    <div class="breakdown-row">
                        <span class="chip red"><i class="fa-solid fa-circle-exclamation"></i> Críticos: {m['criticos']}</span>
                        <span class="chip amber"><i class="fa-solid fa-triangle-exclamation"></i> Altos: {m['altos']}</span>
                        <span class="chip amber"><i class="fa-solid fa-hourglass-half"></i> Pendentes: {m['pendentes_adjudicacao']}</span>
                        <span class="chip blue"><i class="fa-solid fa-pen-ruler"></i> Erratas/Estrutura: {m['estrutura']}</span>
                        <span class="chip"><i class="fa-solid fa-pen-to-square"></i> De-Para: {m['de_para']}</span>
                    </div>

                    <div>
                        <div class="files-label"><i class="fa-solid fa-microscope"></i> Skills Executadas:</div>
                        <div class="skills-box">{skills_html}</div>
                    </div>

                    <div class="run-metrics-grid">
                        <div class="metric-sub"><span class="lbl">Achados</span><span class="val">{m['total_achados']}</span></div>
                        <div class="metric-sub"><span class="lbl">Críticos</span><span class="val crit">{m['criticos']}</span></div>
                        <div class="metric-sub"><span class="lbl">Lacunas</span><span class="val lac">{m['lacunas']}</span></div>
                        <div class="metric-sub"><span class="lbl">IQD</span><span class="val iqd">{esc_iqd}</span></div>
                    </div>
                </div>
                <div class="run-card-footer" style="display:flex; flex-wrap:wrap; gap:8px;">
                    <a href="{safe_href}" class="btn-open-report" style="flex:1 1 200px;"><i class="fa-solid fa-chart-column"></i> Abrir Relatório Consolidado HTML</a>{evo_card_btn}
                </div>
            </div>"""

            rows_html += f"""
            <tr data-search="{safe_search_str}" data-parecer="{card_status_cls}">
                <td><code>{esc_ts}</code><br><span class="run-date">{esc_date}</span></td>
                <td><strong>{esc_lote}</strong><br><span style="font-size:0.75rem; color:var(--text-muted);">{files_html}</span></td>
                <td><span class="badge {parecer_cls}">{esc_parecer}</span></td>
                <td><strong style="color:var(--success); font-size:1.05rem;">{esc_iqd}</strong></td>
                <td>
                  <div style="font-size:0.78rem;">
                    <strong>Total:</strong> {m['total_achados']}<br>
                    <strong style="color:#b45309">Pendentes:</strong> {m['pendentes_adjudicacao']} | <strong style="color:#15803d">Confirmados:</strong> {m['confirmados']}<br>
                    <strong style="color:var(--danger)">Críticos:</strong> {m['criticos']} | <strong style="color:var(--warning)">Lacunas:</strong> {m['lacunas']}
                  </div>
                </td>
                <td><div style="max-width:400px; font-size:0.82rem; color:var(--text-main);">{resumo_html}</div></td>
                <td><div style="display:flex; flex-direction:column; gap:6px;"><a href="{safe_href}" class="btn-open-report" style="padding:6px 10px; font-size:0.75rem;"><i class="fa-solid fa-arrow-up-right-from-square"></i> Abrir</a>{evo_row_btn}</div></td>
            </tr>"""

        master = template.replace('__TOTAL_RUNS__', str(len(runs)))
        master = master.replace('__RUNS_NAO_APTO__', str(runs_nao_apto))
        master = master.replace('__RUNS_PENDENTES__', str(runs_pendentes))
        master = master.replace('__RUNS_RESSALVAS__', str(runs_ressalvas))
        master = master.replace('__TOTAL_CRITICOS__', str(total_criticos))
        master = master.replace('__TOTAL_LACUNAS__', str(total_lacunas))
        master = master.replace('__AVG_IQD__', avg_iqd_str)
        master = master.replace('__RUN_CARDS_HTML__', cards_html)
        master = master.replace('__RUN_TABLE_ROWS_HTML__', rows_html)

        with open(master_html_path, 'w', encoding='utf-8') as f:
            f.write(master)

    return json.dumps({
        "status": "success",
        "total_analyses": len(runs),
        "manifest": manifest_path,
        "master_html": master_html_path
    }, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────
# Definição das Ferramentas MCP
# ─────────────────────────────────────────────

TOOLS_MANIFEST = [
    {
        "name": "freeze_baseline",
        "description": "Calcula hashes SHA-256 de todos os arquivos de um lote (busca recursiva em subpastas). Retorna inventário imutável.",
        "inputSchema": {"type": "object", "properties": {
            "lote_path": {"type": "string", "description": "Caminho relativo do lote (ex: entrada/lote-exemplo-rfp). Se omitido, varre toda entrada/."}
        }, "required": []}
    },
    {
        "name": "profile_baseline",
        "description": "Triagem adaptativa do lote: detecta domínios semanticamente, mapeia checklists ativos/inaplicáveis, recomenda skills com justificativa e gera entrada/decisoes.yaml.",
        "inputSchema": {"type": "object", "properties": {
            "lote_path": {"type": "string", "description": "Caminho relativo do lote específico. Se omitido, detecta todos os lotes em entrada/."},
            "primary_files": {"type": "array", "items": {"type": "string"}, "description": "Lista opcional de nomes/caminhos relativos dos documentos-alvo principais do lote; os demais documentos normativos são classificados como apoio_cruzamento."}
        }, "required": []}
    },
    {
        "name": "run_full_audit",
        "description": "Executa auditoria isolada de um lote, extrai imagens para inventário visual e gera SSOT/HTML. Depois, use get_visual_assets para inspeção multimodal e record_visual_analysis para persistir achados visuais.",
        "inputSchema": {"type": "object", "properties": {
            "lote_path": {"type": "string", "description": "Caminho relativo do lote em entrada/."},
            "primary_files": {"type": "array", "items": {"type": "string"}, "description": "Lista opcional de nomes/caminhos relativos dos documentos-alvo principais do lote; os demais documentos normativos são classificados como apoio_cruzamento."}
        }, "required": []}
    },
    {
        "name": "get_visual_assets",
        "description": "Retorna em blocos MCP de imagem os diagramas extraídos/renderizados e seus metadados de rastreabilidade para interpretação visual pelo modelo chamador. Paginar com offset e limit.",
        "inputSchema": {"type": "object", "properties": {
            "timestamp": {"type": "string"}, "offset": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 8}
        }, "required": ["timestamp"]}
    },
    {
        "name": "record_visual_analysis",
        "description": "Registra os ativos efetivamente revisados, achados da inspeção multimodal no SSOT e recompila os HTMLs. Marque reviewed_asset_ids somente após inspecionar cada imagem. Cada achado deve referenciar asset_id. Para evidência E3, informe trecho_textual_correlacionado literal.",
        "inputSchema": {"type": "object", "properties": {
            "timestamp": {"type": "string"},
            "reviewed_asset_ids": {"type": "array", "items": {"type": "string"}},
            "findings": {"type": "array", "items": {"type": "object", "properties": {
                "asset_id": {"type": "string"}, "title": {"type": "string"},
                "tipo": {"type": "string"}, "criticidade": {"type": "string"},
                "prioridade": {"type": "string"}, "evidencia": {"type": "string"},
                "observacao_visual": {"type": "string"}, "fato": {"type": "string"},
                "impacto": {"type": "string"}, "solucao": {"type": "string"},
                "trecho_textual_correlacionado": {"type": "string"},
                "documento_textual_correlacionado": {"type": "string"},
                "texto_afirmado": {"type": "string"},
                "diagrama_demonstrado": {"type": "string"},
                "proprietario": {"type": "string"}, "rule_id": {"type": "string"}
            }, "required": ["asset_id", "title", "observacao_visual", "fato"]}}
        }, "required": ["timestamp", "reviewed_asset_ids", "findings"]}
    },
    {
        "name": "get_semantic_review_manifest",
        "description": "Lista a matriz de revisão semântica por skill/documento, escopos pendentes, achados existentes e limitações. Use depois de run_full_audit para planejar as passagens especializadas.",
        "inputSchema": {"type": "object", "properties": {
            "timestamp": {"type": "string"}
        }, "required": ["timestamp"]}
    },
    {
        "name": "get_semantic_document_chunk",
        "description": "Retorna um bloco paginado de texto de um documento da baseline, conferindo SHA-256 e preservando marcadores de página/parágrafo/planilha. Continue pelo next_start_char até has_more=false.",
        "inputSchema": {"type": "object", "properties": {
            "timestamp": {"type": "string"}, "document_path": {"type": "string"},
            "start_char": {"type": "integer", "minimum": 0},
            "max_chars": {"type": "integer", "minimum": 1, "maximum": 30000}
        }, "required": ["timestamp", "document_path"]}
    },
    {
        "name": "record_semantic_analysis",
        "description": "Persiste escopos revisados e achados de agentes semânticos. Valida skills ativas, fontes da baseline e citações literais; exige duas citações para E3 e evidência forte para criticidade alta/crítica; atualiza SSOT, relatório individual e índice central.",
        "inputSchema": {"type": "object", "properties": {
            "timestamp": {"type": "string"},
            "reviewed_scopes": {"type": "array", "items": {"type": "object", "properties": {
                "skill": {"type": "string"}, "document_path": {"type": "string"},
                "status": {"type": "string", "enum": ["revisado", "não_aplicável", "não_verificável"]},
                "justificativa": {"type": "string"}
            }, "required": ["skill", "document_path"]}},
            "findings": {"type": "array", "items": {"type": "object", "properties": {
                "skill": {"type": "string"}, "rule_id": {"type": "string"}, "title": {"type": "string"},
                "document_path": {"type": "string"}, "localizacao_exata": {"type": "string"},
                "categoria": {"type": "string"}, "tipo": {"type": "string"},
                "evidencia": {"type": "string"}, "criticidade": {"type": "string"},
                "prioridade": {"type": "string"}, "fato": {"type": "string"},
                "impacto": {"type": "string"}, "solucao": {"type": "string"},
                "proprietario": {"type": "string"}, "quote": {"type": "string"},
                "evidence_sources": {"type": "array", "items": {"type": "object", "properties": {
                    "document_path": {"type": "string"}, "location": {"type": "string"}, "quote": {"type": "string"}
                }, "required": ["document_path", "quote"]}},
                "referencias": {"type": "array", "items": {"type": "object", "properties": {
                    "titulo": {"type": "string"}, "url": {"type": "string"}, "nota": {"type": "string"}
                }}}
            }, "required": ["skill", "title", "tipo", "criticidade", "prioridade", "fato", "impacto"]}},
            "executive_summary": {
                "type": "object",
                "description": "Opcional: síntese executiva estruturada (assunto_email, destinatario_sugerido, avaliacao_maturidade, conclusao_executiva, pontos_fortes, fragilidades_por_dominio, acoes_exigidas) para alimentar a Minuta de E-mail Executivo na Seção 1 do HTML.",
                "properties": {
                    "assunto_email": {"type": "string"},
                    "destinatario_sugerido": {"type": "string"},
                    "avaliacao_maturidade": {"type": "string"},
                    "conclusao_executiva": {"type": "string"},
                    "pontos_fortes": {"type": "array", "items": {"type": "string"}},
                    "fragilidades_por_dominio": {"type": "array", "items": {"type": "object"}},
                    "acoes_exigidas": {"type": "array", "items": {"type": "string"}}
                }
            }
        }, "required": ["timestamp", "reviewed_scopes", "findings"]}
    },
    {
        "name": "adjudicate_findings",
        "description": "Adjudica achados existentes como confirmados, falso positivo, fora de escopo, duplicado, evidência insuficiente ou pendentes. Confirmações exigem citações/localizações literais verificadas contra a baseline ou evidência visual revisada com hash correspondente; atualiza SSOT e relatórios.",
        "inputSchema": {"type": "object", "properties": {
            "timestamp": {"type": "string"},
            "decisions": {"type": "array", "minItems": 1, "maxItems": 200, "items": {"type": "object", "properties": {
                "finding_id": {"type": "string"},
                "status": {"type": "string", "enum": ["pendente", "confirmado", "falso_positivo", "fora_de_escopo", "evidencia_insuficiente", "duplicado"]},
                "rationale": {"type": "string"},
                "related_finding_id": {"type": "string"},
                "reviewer": {"type": "string"},
                "evidence_sources": {"type": "array", "items": {"type": "object", "properties": {
                    "document_path": {"type": "string"}, "location": {"type": "string"},
                    "quote": {"type": "string"}, "sha256": {"type": "string"}
                }, "required": ["document_path", "location", "quote"]}}
            }, "required": ["finding_id", "status", "rationale"]}}
        }, "required": ["timestamp", "decisions"]}
    },
    {
        "name": "analyze_structural_integrity",
        "description": "Executa a verificação determinística e exaustiva dos 7 pilares estruturais e redacionais sobre todos os documentos de entrada.",
        "inputSchema": {"type": "object", "properties": {
            "lote_path": {"type": "string", "description": "Caminho do lote (default: 'entrada')."}
        }, "required": []}
    },
    {
        "name": "scaffold_skill",
        "description": "Gera o rascunho de uma nova skill em .agents/skills/<skill_name>/SKILL.md seguindo o padrão oficial FCA-ENG-001.",
        "inputSchema": {"type": "object", "properties": {
            "skill_name": {"type": "string"},
            "description": {"type": "string"},
            "domain": {"type": "string"},
            "checklist_file": {"type": "string"}
        }, "required": ["skill_name"]}
    },
    {
        "name": "extract_docx_summary",
        "description": "Extrai contagem de parágrafos, tabelas e mídias de um arquivo .docx.",
        "inputSchema": {"type": "object", "properties": {
            "filename": {"type": "string"},
            "lote_path": {"type": "string"}
        }, "required": ["filename"]}
    },
    {
        "name": "extract_xlsx_summary",
        "description": "Extrai abas, cabeçalhos e amostra de dados de um arquivo .xlsx.",
        "inputSchema": {"type": "object", "properties": {
            "filename": {"type": "string"},
            "lote_path": {"type": "string"}
        }, "required": ["filename"]}
    },
    {
        "name": "validate_analise_contract",
        "description": "Valida se os entregáveis da RTI (index.html e dados_analise.json) existem em analise/<timestamp>/relatorios/ e verifica a cobertura de skills.",
        "inputSchema": {"type": "object", "properties": {
            "timestamp": {"type": "string"}
        }, "required": []}
    },
    {
        "name": "build_run_index_html",
        "description": "Recompila o dashboard HTML de uma análise individual a partir do dados_analise.json SSOT.",
        "inputSchema": {"type": "object", "properties": {
            "timestamp": {"type": "string", "description": "Timestamp completo da análise (YYYYMMDD_HHMMSS_NOME_LOTE)."}
        }, "required": ["timestamp"]}
    },
    {
        "name": "finalize_execution",
        "description": "Move os arquivos do lote de entrada/ para analise/<lote>/<version>/<timestamp>/entrada/ e atualiza analise/index.html.",
        "inputSchema": {"type": "object", "properties": {
            "timestamp": {"type": "string", "description": "Timestamp ou caminho da análise."},
            "lote": {"type": "string", "description": "Nome do lote (opcional se dedutível do timestamp)."},
            "version": {"type": "string", "description": "Versão do documento (ex: v1.0, v1.8)."}
        }, "required": ["timestamp"]}
    },
    {
        "name": "create_review_revision",
        "description": "Cria uma nova rodada de revisão pontual/adjudicação a partir de um relatório existente (analise/<lote>/<version>/<novo_timestamp>/), preservando o histórico e a baseline imutável da rodada anterior.",
        "inputSchema": {"type": "object", "properties": {
            "source_analysis": {"type": "string", "description": "Timestamp ou caminho relativo da análise de origem (ex: 03_HLD_NUTANIX/v1.8/20261014_202600 ou 20261014_202600)."},
            "reason": {"type": "string", "description": "Justificativa/motivação da revisão pontual do auditor."},
            "reviewer": {"type": "string", "description": "Identificação do revisor/auditor."}
        }, "required": ["source_analysis"]}
    },
    {
        "name": "reconcile_versions",
        "description": "Compara duas versões/rodadas de análise (previous_timestamp vs current_timestamp), gera o relatório dedicado evolucao.html e o Quadro de Reconciliação Técnica e Evolução (novos, refinados, expurgados/saneados e reincidentes), persiste em dados_analise.json e recompila os HTMLs.",
        "inputSchema": {"type": "object", "properties": {
            "previous_timestamp": {"type": "string", "description": "Timestamp ou caminho relativo da versão anterior."},
            "current_timestamp": {"type": "string", "description": "Timestamp ou caminho relativo da versão atual."},
            "summary_notes": {"type": "string", "description": "Sumário executivo opcional explicando o motivo e o escopo das alterações incorporadas na nova versão."},
            "external_audit_disposition": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Opcional: matriz de disposição/rastreabilidade de apontamentos oriundos de insumos externos avaliados como não-fonte-de-verdade."
            }
        }, "required": ["previous_timestamp", "current_timestamp"]}
    },
    {
        "name": "export_executive_email",
        "description": "Exporta sob demanda a minuta de e-mail executivo (.md) para a pasta raiz do lote em analise/<lote>/ a partir do dados_analise.json (SSOT).",
        "inputSchema": {"type": "object", "properties": {
            "timestamp": {"type": "string", "description": "Timestamp ou caminho relativo da análise."},
            "output_filename": {"type": "string", "description": "Nome opcional do arquivo .md (apenas basename, ex: email_resumo_analise.md)."}
        }, "required": ["timestamp"]}
    },
    {
        "name": "build_master_index",
        "description": "Recompila analise/index.html e analise/manifest.json varrendo todos os relatórios.",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "check_environment",
        "description": "Audita o ambiente (pacotes Python e utilitários do SO como poppler-utils e tesseract) e retorna a matriz de prontidão analítica.",
        "inputSchema": {"type": "object", "properties": {}, "required": []}
    },
]


# ─────────────────────────────────────────────
# Loop MCP JSON-RPC 2.0
# ─────────────────────────────────────────────

def dispatch_tool(name: str, args: dict) -> str:
    if name == "freeze_baseline":
        return tool_freeze_baseline(args.get("lote_path"))
    elif name == "profile_baseline":
        return tool_profile_baseline(args.get("lote_path"), primary_files=args.get("primary_files"))
    elif name == "check_environment":
        return tool_check_environment()
    elif name == "run_full_audit":
        return tool_run_full_audit(args.get("lote_path"), primary_files=args.get("primary_files"))
    elif name == "record_visual_analysis":
        return tool_record_visual_analysis(args.get("timestamp", ""), args.get("reviewed_asset_ids", []), args.get("findings", []))
    elif name == "get_semantic_review_manifest":
        return tool_get_semantic_review_manifest(args.get("timestamp", ""))
    elif name == "get_semantic_document_chunk":
        return tool_get_semantic_document_chunk(args.get("timestamp", ""), args.get("document_path", ""),
                                                args.get("start_char", 0), args.get("max_chars", 12000))
    elif name == "record_semantic_analysis":
        return tool_record_semantic_analysis(
            args.get("timestamp", ""),
            args.get("reviewed_scopes", []),
            args.get("findings", []),
            executive_summary=args.get("executive_summary"),
        )
    elif name == "adjudicate_findings":
        return tool_adjudicate_findings(args.get("timestamp", ""), args.get("decisions", []))
    elif name == "analyze_structural_integrity":
        return tool_analyze_structural_integrity(args.get("lote_path", "entrada"))
    elif name == "scaffold_skill":
        return tool_scaffold_skill(args.get("skill_name", ""), args.get("description", ""),
                                   args.get("domain", ""), args.get("checklist_file", ""))
    elif name == "extract_docx_summary":
        return tool_extract_docx_summary(args.get("filename", ""), args.get("lote_path"))
    elif name == "extract_xlsx_summary":
        return tool_extract_xlsx_summary(args.get("filename", ""), args.get("lote_path"))
    elif name == "validate_analise_contract":
        return tool_validate_analise_contract(args.get("timestamp"))
    elif name == "build_run_index_html":
        return tool_build_run_index_html(args.get("timestamp", ""))
    elif name == "finalize_execution":
        return tool_finalize_execution(args.get("timestamp", ""), args.get("lote"), args.get("version"))
    elif name == "create_review_revision":
        return tool_create_review_revision(args.get("source_analysis", ""), args.get("reason", "Ajuste e Adjudicação de Relatório"), args.get("reviewer", "auditor"))
    elif name == "reconcile_versions":
        return tool_reconcile_versions(
            args.get("previous_timestamp", ""),
            args.get("current_timestamp", ""),
            summary_notes=args.get("summary_notes", ""),
            external_audit_disposition=args.get("external_audit_disposition"),
        )
    elif name == "export_executive_email":
        return tool_export_executive_email(args.get("timestamp", ""), output_filename=args.get("output_filename"))
    elif name == "build_master_index":
        return tool_build_master_index()
    else:
        return json.dumps({"error": f"Ferramenta desconhecida: {name}"})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        req_id = request.get("id")
        method = request.get("method", "")

        if method == "initialize":
            response = {"jsonrpc": "2.0", "id": req_id, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fca-eng-001-rti", "version": "1.4.2"}
            }}
        elif method == "tools/list":
            response = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS_MANIFEST}}
        elif method == "tools/call":
            params = request.get("params", {})
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            try:
                if tool_name == "get_visual_assets":
                    content = tool_get_visual_assets(
                        tool_args.get("timestamp", ""), tool_args.get("offset", 0), tool_args.get("limit", 6))
                else:
                    result_text = dispatch_tool(tool_name, tool_args)
                    content = [{"type": "text", "text": result_text}]
                response = {"jsonrpc": "2.0", "id": req_id, "result": {"content": content}}
            except Exception as e:
                response = {"jsonrpc": "2.0", "id": req_id, "result": {
                    "content": [{"type": "text", "text": json.dumps({"status": "error", "message": str(e)})}]
                }}
        else:
            response = {"jsonrpc": "2.0", "id": req_id, "result": {}}

        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
