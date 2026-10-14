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
import shutil
import hashlib
import zipfile
import datetime
import re
import xml.etree.ElementTree as ET
from functools import lru_cache

_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

import html_compiler
import audit_pipeline
import specialized_controls
import cross_document
import tabular_visual_controls
import advanced_specialized_controls
import visual_pipeline
import semantic_pipeline
from xlsx_fallback import extract_xlsx_data as extract_xlsx_data_fallback



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

def extract_docx_text(fpath: str) -> str:
    """Extrai texto de .docx preservando estrutura de parágrafos."""
    try:
        z = zipfile.ZipFile(fpath)
        doc_xml = z.read('word/document.xml').decode('utf-8', errors='ignore')
        # Namespace WordprocessingML
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        tree = ET.fromstring(doc_xml)
        paragraphs = []
        for p in tree.findall('.//w:p', ns):
            texts = [r.text or '' for r in p.findall('.//w:t', ns)]
            para_text = ''.join(texts).strip()
            if para_text:
                paragraphs.append(para_text)
        return '\n'.join(paragraphs)
    except Exception:
        # Fallback: strip all XML tags
        try:
            z = zipfile.ZipFile(fpath)
            doc_xml = z.read('word/document.xml').decode('utf-8', errors='ignore')
            return re.sub(r'<[^>]+>', ' ', doc_xml)
        except Exception:
            return ''


def extract_pdf_text(fpath: str) -> str:
    """Extrai texto de .pdf usando pypdf se disponível."""
    try:
        import pypdf
        reader = pypdf.PdfReader(fpath)
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return '\n'.join(pages)
    except ImportError:
        return ''
    except Exception:
        return ''


def extract_xlsx_data(fpath: str) -> dict:
    """Extrai dados de .xlsx usando openpyxl se disponível."""
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
    """Lê CSV como texto."""
    try:
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read(200000)
    except Exception:
        return ''


def extract_text_file(fpath: str) -> str:
    """Lê .md, .txt, .json, .yaml como texto."""
    try:
        with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read(200000)
    except Exception:
        return ''


def get_file_text(fpath: str) -> str:
    """Roteador principal — extrai texto de qualquer formato suportado."""
    ext = os.path.splitext(fpath)[1].lower()
    if ext == '.docx':
        return extract_docx_text(fpath)
    elif ext == '.pdf':
        return extract_pdf_text(fpath)
    elif ext in ('.md', '.txt', '.json', '.yaml', '.yml'):
        return extract_text_file(fpath)
    elif ext == '.csv':
        return extract_csv_text(fpath)
    # xlsx tem tratamento especial via extract_xlsx_data
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
    "rfp":         ["contratos.md", "oss.md", "bss.md", "arquitetura.md", "integracoes.md", "editorial.md", "estrutura_e_referencias.md"],
    "hld":         ["arquitetura.md", "datacenter.md", "cloud.md", "seguranca.md", "integracoes.md", "diagramas.md", "imagens.md"],
    "lld":         ["arquitetura.md", "integracoes.md", "seguranca.md", "editorial.md"],
    "contrato":    ["contratos.md", "editorial.md", "estrutura_e_referencias.md"],
    "lgpd":        ["seguranca.md"],
    "oss":         ["oss.md", "bss.md", "integracoes.md", "tm_forum.md"],
    "bss":         ["bss.md", "oss.md", "integracoes.md"],
    "seguranca":   ["seguranca.md", "arquitetura.md"],
    "cloud":       ["cloud.md", "arquitetura.md", "seguranca.md"],
    "datacenter":  ["datacenter.md", "arquitetura.md", "seguranca.md"],
    "integracoes": ["integracoes.md", "tm_forum.md", "arquitetura.md"],
    "tm_forum":    ["tm_forum.md", "integracoes.md", "oss.md"],
    "arquitetura": ["arquitetura.md", "integracoes.md", "seguranca.md"],
    "carrier":     ["carrier.md", "arquitetura.md", "integracoes.md"],
    "dwdm":        ["carrier.md", "arquitetura.md"],
    "dcn":         ["carrier.md", "arquitetura.md", "seguranca.md", "datacenter.md"],
}

ALL_CHECKLISTS = [
    "oss.md", "bss.md", "seguranca.md", "contratos.md", "arquitetura.md",
    "cloud.md", "datacenter.md", "integracoes.md", "tm_forum.md", "imagens.md",
    "diagramas.md", "editorial.md", "estrutura_e_referencias.md", "carrier.md",
    "tabelas.md", "fluxogramas.md", "ieee.md", "iso.md", "itil.md", "mef.md", "rfc.md"
]


# Domínios de tipo de documento requerem evidência mais forte
# para evitar falsos positivos de menções incidentais em outros documentos.
DOC_TYPE_DOMAINS = {"hld", "lld", "rfp"}  # Exigem 2+ hits ou presença no filename


def has_embedded_images(fpath: str, ext: str) -> bool:
    """Verifica se um arquivo .docx ou .pdf contém imagens/diagramas embutidos."""
    if ext == '.docx':
        try:
            z = zipfile.ZipFile(fpath)
            for name in z.namelist():
                if name.startswith('word/media/'):
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
    """Extrai o texto legível de um arquivo (.docx, .pdf, .txt, .md, .json, .yaml)."""
    ext = os.path.splitext(fpath)[1].lower()
    text = ""
    if ext == '.docx':
        try:
            z = zipfile.ZipFile(fpath)
            if 'word/document.xml' in z.namelist():
                xml_content = z.read('word/document.xml')
                tree = ET.fromstring(xml_content)
                text = ' '.join(tree.itertext())
        except Exception:
            pass
    elif ext == '.pdf':
        try:
            import pypdf
            reader = pypdf.PdfReader(fpath)
            for page in reader.pages:
                text += page.extract_text() or ""
        except Exception:
            pass
    elif ext in ('.txt', '.md', '.json', '.yaml', '.yml', '.svg', '.drawio'):
        try:
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
        except Exception:
            pass
    elif ext == '.csv':
        text = extract_csv_text(fpath)
    elif ext in ('.xlsx', '.xls'):
        sheets = extract_xlsx_data(fpath)
        text = '\n'.join(
            f"[ABA: {sheet}]\n" + '\n'.join(' | '.join(row) for row in rows)
            for sheet, rows in sheets.items()
        )
    return text


def analyze_document_structure(fpath: str) -> list:
    """Realiza a varredura não-técnica dos 6 pilares de integridade redacional e estrutural."""
    filename = os.path.basename(fpath)
    text = extract_text_from_file(fpath)
    if not text:
        return []

    findings = []

    # Pilar 6: Marcadores de Rascunho / Campos em Branco
    draft_matches = re.findall(r'\[(Preenchido por|Inserir|A definir|TBD|XXX|\?\?\?)[^\]]*\]', text, re.IGNORECASE)
    if "Preenchido por Compras" in text or draft_matches:
        findings.append({
            'id': 'EDIT-001',
            'title': f'Campos de rascunho/template não preenchidos em {filename}',
            'doc_origem': filename,
            'loc': 'Seções de Identificação / Cabeçalhos',
            'cat': 'Integridade Redacional e Estrutural',
            'tipo': 'Errata/Estrutura',
            'evid': 'E3 (Confirmado por confronto direto)',
            'crit': 'Média',
            'prio': 'P2',
            'fato': 'O documento contém marcações de rascunho/template não preenchidas (ex: "[Preenchido por Compras]" ou marcas de placeholder).',
            'impacto': 'Publicação de documento com marcas de rascunho prejudica a imagem institucional e dificulta a comunicação formal.',
            'tipo_solucao': 'De → Para (Minuta)',
            'texto_atual': '[Preenchido por Compras / Rascunho]',
            'texto_sugerido': 'Preencher formalmente todos os campos cadastrais antes da publicação.',
            'proprietario': 'Área Emissora do Documento',
            'id_acao': 'ACT-EDIT-001'
        })

    # Pilar 4: Erros de codificação / OCR (ex: An?lise, Especifica??o)
    encoding_bugs = re.findall(r'\b[A-Za-z]+\?[A-Za-z]+\b', text)
    if encoding_bugs:
        sample_bugs = ', '.join(list(set(encoding_bugs))[:5])
        findings.append({
            'id': 'EDIT-002',
            'title': f'Artefatos de conversão de codificação/OCR em palavras de {filename}',
            'doc_origem': filename,
            'loc': 'Corpo do Texto',
            'cat': 'Integridade Redacional e Estrutural',
            'tipo': 'Errata/Estrutura',
            'evid': 'E3 (Confirmado por confronto direto)',
            'crit': 'Baixa',
            'prio': 'P3',
            'fato': f'Foram identificadas palavras com erro de caracter acentuado (ex: {sample_bugs}).',
            'impacto': 'Prejuízo à legibilidade e apresentação gráfica do documento.',
            'tipo_solucao': 'De → Para (Minuta)',
            'texto_atual': f'Exemplo de termos com erro: {sample_bugs}',
            'texto_sugerido': 'Corrigir a codificação de caracteres para UTF-8 sem perdas de acentuação.',
            'proprietario': 'Revisão Editorial / Autor',
            'id_acao': 'ACT-EDIT-002'
        })

    # Pilar 4: Vocabulário PT-PT proibido pela regra 8 do AGENTS.md
    pt_pt_terms = re.findall(r'\b(ficheiro|ficheiros|equipa|equipas|ecrã|ecrãs|facto|factos|planeamento)\b', text, re.IGNORECASE)
    if pt_pt_terms:
        unique_terms = ', '.join(list(set([t.lower() for t in pt_pt_terms]))[:5])
        findings.append({
            'id': 'EDIT-003',
            'title': f'Uso de vocabulário de Português de Portugal (PT-PT) em {filename}',
            'doc_origem': filename,
            'loc': 'Texto Integral',
            'cat': 'Integridade Redacional e Estrutural',
            'tipo': 'Errata/Estrutura',
            'evid': 'E3 (Confirmado por confronto direto)',
            'crit': 'Baixa',
            'prio': 'P3',
            'fato': f'O documento utiliza termos do Português de Portugal (ex: {unique_terms}), contrariando a norma FCA-ENG-001.',
            'impacto': 'Desalinhamento com as diretrizes corporativas de redação oficial em PT-BR.',
            'tipo_solucao': 'De → Para (Minuta)',
            'texto_atual': f'Termos identificados: {unique_terms}',
            'texto_sugerido': 'Substituir por equivalente PT-BR: "arquivo", "equipe", "tela", "fato", "planejamento".',
            'proprietario': 'Revisão Editorial',
            'id_acao': 'ACT-EDIT-003'
        })

    # Pilar 7 (RFC 2119 / RFC 8174): Termos Fracos e Ambíguos em Requisitos Mandatórios
    weak_terms = re.findall(r'\b(em princípio|desejável|preferencialmente|quando conveniente|na medida do possível|se conveniente|se possível)\b', text, re.IGNORECASE)
    if weak_terms:
        unique_weak = ', '.join(list(set([w.lower() for w in weak_terms]))[:5])
        findings.append({
            'id': 'EDIT-004',
            'title': f'Termos fracos e ambíguos em cláusulas normativas de {filename} (RFC 2119 / RFC 8174)',
            'doc_origem': filename,
            'loc': 'Requisitos Técnicos / Normativos',
            'cat': 'Conformidade RFC 2119/8174',
            'tipo': 'Ambiguidade',
            'evid': 'E3 (Confirmado por confronto direto)',
            'crit': 'Média',
            'prio': 'P2',
            'fato': f'O documento utiliza linguagem de descompromisso ou ambígua em especificações técnicas (ex: "{unique_weak}").',
            'impacto': 'Reduz a força coercitiva contratual e impede a exigência de cumprimento estrito no aceite.',
            'tipo_solucao': 'De → Para (Minuta)',
            'texto_atual': f'Expressões ambíguas encontradas: {unique_weak}',
            'texto_sugerido': 'Substituir por verbos estritos da RFC 2119 em caixa alta: DEVE (mandatório), RECOMENDA-SE (opção justificada) ou PODE (opcional).',
            'proprietario': 'Engenharia de Requisitos / Jurídico',
            'id_acao': 'ACT-EDIT-004'
        })

    # Pilar 7 (ISO/IEC/IEEE 29148): Requisitos Subjetivos e Não Mensuráveis
    subjective_terms = re.findall(r'\b(altíssima velocidade|sistema rápido|alta performance|interface amigável|super seguro|resposta instantânea)\b', text, re.IGNORECASE)
    if subjective_terms:
        unique_subj = ', '.join(list(set([s.lower() for s in subjective_terms]))[:5])
        findings.append({
            'id': 'EDIT-005',
            'title': f'Requisitos subjetivos e não mensuráveis em {filename} (ISO/IEC/IEEE 29148)',
            'doc_origem': filename,
            'loc': 'Especificações Técnicas',
            'cat': 'Engenharia de Requisitos (ISO 29148)',
            'tipo': 'Ambiguidade',
            'evid': 'E2 (Corroborado)',
            'crit': 'Média',
            'prio': 'P2',
            'fato': f'O documento contém adjetivos subjetivos sem métricas numéricas objetivas de teste (ex: "{unique_subj}").',
            'impacto': 'Violou o critério de Testabilidade da ISO 29148, gerando margem para contestação em homologação.',
            'tipo_solucao': 'Plano de Ação Estruturado',
            'texto_atual': f'Adjetivos subjetivos: {unique_subj}',
            'texto_sugerido': 'Especificar KPI numérico quantitativo de aceite (ex: latência < 50ms, vazão > 10 Gbps, SLA 99,99%).',
            'proprietario': 'Comissão Técnica de Engenharia',
            'id_acao': 'ACT-EDIT-005'
        })

    # Pilar 7 (ISO 8601): SLAs e Janelas de Manutenção sem Fuso Horário
    sla_no_tz = re.findall(r'\b(24x7|horário comercial|janela de manutenção)\b', text, re.IGNORECASE)
    if sla_no_tz and not re.search(r'\b(UTC|BRT|UTC-3)\b', text):
        findings.append({
            'id': 'EDIT-006',
            'title': f'Janelas de SLA / Manutenção sem indicação de fuso horário em {filename} (ISO 8601)',
            'doc_origem': filename,
            'loc': 'Cláusulas de SLA e Suporte',
            'cat': 'Integridade Redacional e Estrutural',
            'tipo': 'Lacuna',
            'evid': 'E3 (Confirmado por confronto direto)',
            'crit': 'Baixa',
            'prio': 'P3',
            'fato': 'O documento referencia janelas de atendimento/SLA ("24x7" ou "horário comercial") sem especificar o fuso horário oficial (BRT / UTC-3).',
            'impacto': 'Possibilidade de divergência na contagem de prazos em operações multi-região ou suporte remoto internacional.',
            'tipo_solucao': 'De → Para (Minuta)',
            'texto_atual': 'Período sem fuso horário explicitado.',
            'texto_sugerido': 'Explicitar o fuso horário oficial em todos os prazos: ex. "24x7x365 no fuso horário de Brasília (BRT / UTC-3)".',
            'proprietario': 'Gestão de Operações / Contratos',
            'id_acao': 'ACT-EDIT-006'
        })

    return findings


def analyze_document_domain_technical(fpath: str, skills_ativas: list = None) -> list:
    """
    Executa a auditoria técnica exaustiva de domínio com base nas skills ativas no lote.
    Mapeia fatos, lacunas, inconsistências e riscos específicos por domínio.
    """
    filename = os.path.basename(fpath)
    text = extract_text_from_file(fpath)
    if not text:
        return []

    text_lower = text.lower()
    findings = []
    skills = [s.lower() for s in (skills_ativas or [])]

    # --- SKILL: analisar-carrier (Carrier Telecom & DCN) ---
    if not skills or 'analisar-carrier' in skills:
        # 1. Dark Fiber & DWDM OSNR
        if ('dwdm' in text_lower or 'óptica' in text_lower or 'optica' in text_lower or 'fibra' in text_lower) and not re.search(r'\b(osnr|span budget|otdr|db/km)\b', text_lower):
            findings.append({
                'id': 'CARRIER-001',
                'title': f'Parâmetros ópticos de DWDM / Fibra Apagada (OSNR, Span Budget, dB/km) omissos em {filename}',
                'doc_origem': filename,
                'loc': 'Especificação de Transporte / Camada Óptica',
                'cat': 'Carrier Telecom & DCN',
                'tipo': 'Lacuna',
                'evid': 'E3 (Confirmado por confronto direto)',
                'crit': 'Alta',
                'prio': 'P1',
                'fato': 'O documento referencia enlace de transporte óptico/DWDM sem especificar a margem mínima de OSNR, a atenuação máxima por km (dB/km) ou a exigência de laudos de OTDR.',
                'impacto': 'Impossibilidade de homologar a viabilidade física e a margem de degradação da camada óptica do backbone.',
                'tipo_solucao': 'Plano de Ação Estruturado',
                'texto_atual': 'Especificação óptica sem parâmetros de OSNR / dB/km.',
                'texto_sugerido': 'Exigir tabela de span budget, margem de OSNR mínima (≥ 18 dB) e laudos de ensaio OTDR para aceite da fibra.',
                'proprietario': 'Engenharia de Transporte / Óptica',
                'id_acao': 'ACT-CARRIER-001'
            })

        # 2. IP Core Convergence & BFD
        if ('bgp' in text_lower or 'mpls' in text_lower or 'isis' in text_lower or 'srv6' in text_lower) and not re.search(r'\b(bfd|frr|fast reroute)\b', text_lower):
            findings.append({
                'id': 'CARRIER-002',
                'title': f'Mecanismos de convergência ultra-rápida (BFD e SR-FRR < 50ms) não especificados no Core IP em {filename}',
                'doc_origem': filename,
                'loc': 'Arquitetura de Roteamento / Core IP',
                'cat': 'Carrier Telecom & DCN',
                'tipo': 'Inconsistência',
                'evid': 'E3 (Confirmado por confronto direto)',
                'crit': 'Alta',
                'prio': 'P1',
                'fato': 'O documento descreve protocolos de roteamento de backbone (BGP/IS-IS/SRv6) sem exigir explicitamente a ativação de BFD (Bidirectional Forwarding Detection) e Fast Reroute (FRR sub-50ms).',
                'impacto': 'Tempo de convergência em queda de enlace pode subir de milissegundos para segundos, derrubando sessões L2/L3VPN e voip.',
                'tipo_solucao': 'De → Para (Minuta)',
                'texto_atual': 'Roteamento IP sem especificação de BFD / FRR.',
                'texto_sugerido': 'DEVE ser ativado BFD com timer de detecção ≤ 50ms e SR-FRR Topology-Independent LFA (TI-LFA) em todas as adjacências de Core.',
                'proprietario': 'Engenharia de Roteamento IP',
                'id_acao': 'ACT-CARRIER-002'
            })

        # 3. BGP Route Reflectors & Peering RPKI
        if ('peering' in text_lower or 'ixp' in text_lower or 'ptt' in text_lower or 'route reflector' in text_lower) and not re.search(r'\b(rpki|roa|flowspec|blackhole)\b', text_lower):
            findings.append({
                'id': 'CARRIER-003',
                'title': f'Políticas de proteção de Peering e BGP (RPKI, max-prefix, Flowspec) omissas em {filename}',
                'doc_origem': filename,
                'loc': 'BGP & Pontos de Troca de Tráfego (IXP/PNI)',
                'cat': 'Carrier Telecom & DCN',
                'tipo': 'Lacuna',
                'evid': 'E3 (Confirmado por confronto direto)',
                'crit': 'Crítica',
                'prio': 'P0',
                'fato': 'A arquitetura BGP de Peering/IXP não especifica a validação compulsória de RPKI (ROA Validation), limites de prefixos recebidos (max-prefix) ou mecanismos anti-DDoS (BGP Flowspec/RTBH).',
                'impacto': 'Risco de sequestro de rotas BGP (BGP Route Leak/Hijacking) e instabilidade por estouro de tabela de roteamento no backbone.',
                'tipo_solucao': 'De → Para (Minuta)',
                'texto_atual': 'Conexão BGP de Peering sem política de segurança RPKI.',
                'texto_sugerido': 'Ativar RPKI ROA Validation com política Invalid Drop, max-prefix e suporte a BGP Flowspec (RFC 8955).',
                'proprietario': 'Segurança de Rede / Roteamento BGP',
                'id_acao': 'ACT-CARRIER-003'
            })

        # 4. DCN Fabric, Telemetria & PAM Break-Glass
        if ('dcn' in text_lower or 'spine' in text_lower or 'leaf' in text_lower or 'evpn' in text_lower) and not re.search(r'\b(gnmi|grpc|pam|break-glass|oob)\b', text_lower):
            findings.append({
                'id': 'CARRIER-004',
                'title': f'Instrumentação DCN (Streaming Telemetry gNMI) e Gestão PAM Break-Glass não especificadas em {filename}',
                'doc_origem': filename,
                'loc': 'Infraestrutura DCN & Observabilidade',
                'cat': 'Carrier Telecom & DCN',
                'tipo': 'Lacuna',
                'evid': 'E2 (Corroborado)',
                'crit': 'Média',
                'prio': 'P2',
                'fato': 'A rede DCN (Spine-Leaf / Out-Of-Band) omite a exigência de Streaming Telemetry (gNMI/gRPC/OpenConfig) e a política de custódia/rotação compulsória de credenciais locais (Break-Glass PAM).',
                'impacto': 'Monitoramento legado por SNMP polling perde eventos transientes e o uso de senhas locais sem rotação compromete a governança OOB.',
                'tipo_solucao': 'Plano de Ação Estruturado',
                'texto_atual': 'Gestão DCN por SNMP polling sem fluxo PAM Break-Glass.',
                'texto_sugerido': 'Implementar Streaming Telemetry via gNMI/gRPC e selagem de senhas locais em cofre PAM com rotação automática em 24h após acionamento.',
                'proprietario': 'Gerência de DCN & Segurança da Informação',
                'id_acao': 'ACT-CARRIER-004'
            })

    # --- SKILL: analisar-rfp (Requests for Proposal / RFIs) ---
    if not skills or 'analisar-rfp' in skills:
        if ('sla' in text_lower or 'penalidade' in text_lower) and not re.search(r'\b(raci|matriz de responsabilidades)\b', text_lower):
            findings.append({
                'id': 'RFP-001',
                'title': f'Ausência de Matriz RACI explicita para obrigações contratuais e SLAs em {filename}',
                'doc_origem': filename,
                'loc': 'Cláusulas de SLA e Responsabilidades',
                'cat': 'Requests for Proposal (RFP)',
                'tipo': 'Lacuna',
                'evid': 'E3 (Confirmado por confronto direto)',
                'crit': 'Alta',
                'prio': 'P1',
                'fato': 'O documento estabelece metas de SLA e penalidades mas não define formalmente a Matriz RACI (Responsible, Accountable, Consulted, Informed) para cada evento operacional.',
                'impacto': 'Risco de omissão em incidentes graves por indefinição de quem deve executar o chamado ou autorizar a janela de manutenção.',
                'tipo_solucao': 'De → Para (Minuta)',
                'texto_atual': 'Obrigações operacionais em voz passiva sem responsável atribuído.',
                'texto_sugerido': 'Incluir anexo normativo com a Matriz RACI detalhando a responsabilidade da Contratada e da Contratante para cada SLA.',
                'proprietario': 'Comissão Licitante / Gestão de Contratos',
                'id_acao': 'ACT-RFP-001'
            })

    # --- SKILL: analisar-hld (High Level Design) ---
    if not skills or 'analisar-hld' in skills:
        if ('cluster' in text_lower or 'redundância' in text_lower or 'ha' in text_lower) and not re.search(r'\b(quorum|split-brain|witness|fencing)\b', text_lower):
            findings.append({
                'id': 'HLD-001',
                'title': f'Mecanismo de Quorum e proteção contra Split-Brain não especificado no cluster de {filename}',
                'doc_origem': filename,
                'loc': 'Arquitetura de Alta Disponibilidade (HA)',
                'cat': 'High Level Design (HLD)',
                'tipo': 'Lacuna',
                'evid': 'E3 (Confirmado por confronto direto)',
                'crit': 'Alta',
                'prio': 'P1',
                'fato': 'O HLD prevê arquitetura em cluster de alta disponibilidade (HA) mas não detalha o mecanismo de Quorum, nó Witness ou protocolo de Fencing para prevenção de Split-Brain.',
                'impacto': 'Em caso de partição de rede, ambos os nós podem assumir papel primário simultaneamente, causando corrupção de dados.',
                'tipo_solucao': 'Plano de Ação Estruturado',
                'texto_atual': 'Cluster HA descrito sem especificação de Quorum / Witness.',
                'texto_sugerido': 'Especificar o mecanismo de Quorum (ex: Majority Node Set ou Witness em 3º site) e a política de fencing automático.',
                'proprietario': 'Arquitetura de Soluções / Datacenter',
                'id_acao': 'ACT-HLD-001'
            })

    # --- SKILL: analisar-lgpd (Lei Geral de Proteção de Dados) ---
    if not skills or 'analisar-lgpd' in skills:
        if not re.search(r'\b(dpo|encarregado|anonimização|criptografia|base legal)\b', text_lower):
            findings.append({
                'id': 'LGPD-001',
                'title': f'Ausência de controles formais de LGPD (Base Legal, DPO e Criptografia de PII) em {filename}',
                'doc_origem': filename,
                'loc': 'Tratamento de Dados e Privacidade',
                'cat': 'Conformidade LGPD (Lei 13.709/2018)',
                'tipo': 'Lacuna',
                'evid': 'E2 (Corroborado)',
                'crit': 'Alta',
                'prio': 'P1',
                'fato': 'O documento referencia o manuseio de dados de usuários sem formalizar a Base Legal (Art. 7º LGPD), a indicação do Encarregado (DPO) ou o padrão de criptografia em trânsito e repouso.',
                'impacto': 'Risco de sanções administrativas da ANPD e incidentes de vazamento sem plano de resposta a titulares.',
                'tipo_solucao': 'De → Para (Minuta)',
                'texto_atual': 'Menção vaga ao tratamento de dados sem cláusulas LGPD.',
                'texto_sugerido': 'Inserir Anexo de Proteção de Dados com requisitos de pseudonimização, criptografia AES-256 e canal do DPO.',
                'proprietario': 'Jurídico / Privacidade & DPO',
                'id_acao': 'ACT-LGPD-001'
            })

    # --- SKILL: analisar-datacenter (Datacenter Tier III/IV) ---
    if not skills or 'analisar-datacenter' in skills:
        if not re.search(r'\b(autonomia|gerador|ups|nobreak|2n|n\+1)\b', text_lower):
            findings.append({
                'id': 'DC-001',
                'title': f'Especificação de redundância de energia/climatização (2N / N+1) e autonomia de UPS incompleta em {filename}',
                'doc_origem': filename,
                'loc': 'Infraestrutura Datacenter / Facilidades',
                'cat': 'Infraestrutura Datacenter Tier III/IV',
                'tipo': 'Lacuna',
                'evid': 'E3 (Confirmado por confronto direto)',
                'crit': 'Média',
                'prio': 'P2',
                'fato': 'O documento menciona ambiente de Datacenter sem detalhar a autonomia dos grupos geradores de combustível, a topologia de UPS (2N vs N+1) e o tempo de sustentação das baterias.',
                'impacto': 'Vulnerabilidade a apagões na concessionária sem garantia de transição suave para os geradores.',
                'tipo_solucao': 'Plano de Ação Estruturado',
                'texto_atual': 'Especificação de Datacenter sem SLAs de facilidades.',
                'texto_sugerido': 'Exigir certificação Tier III/IV (Uptime Institute) e autonomia mínima de 15 minutos em UPS 2N com geradores de partida em < 10s.',
                'proprietario': 'Engenharia de Infraestrutura / Datacenter',
                'id_acao': 'ACT-DC-001'
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
    if has_xlsx:
        active.add("tabelas.md")

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


def tool_profile_baseline(lote_path: str = None) -> str:
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

    IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.svg', '.drawio', '.bmp', '.gif'}
    XLSX_EXTS = {'.xlsx', '.xls', '.csv'}
    DOC_EXTS = {'.docx', '.pdf', '.txt', '.md', '.json', '.yaml', '.yml'}

    def profile_lote(lote_dir: str) -> dict:
        text_corpus = ""
        filename_corpus = ""
        files_found = []
        images = []
        xlsx_files = []
        doc_files = []

        has_embedded = False
        for dirpath, _, filenames in os.walk(lote_dir):
            for fname in sorted(filenames):
                if fname.startswith('.') or fname in ('README.md', 'decisoes.yaml'):
                    continue
                fpath = os.path.join(dirpath, fname)
                ext = os.path.splitext(fname)[1].lower()
                rel = os.path.relpath(fpath, lote_dir)
                size = os.path.getsize(fpath)

                files_found.append({"name": fname, "path": rel, "ext": ext, "size_bytes": size})
                filename_corpus += " " + fname.lower() + " " + rel.lower()

                if ext in IMAGE_EXTS:
                    images.append(fname)
                elif ext in XLSX_EXTS:
                    xlsx_files.append(fname)
                    if ext == '.xlsx':
                        # Extrai texto das planilhas para análise semântica
                        data = extract_xlsx_data(fpath)
                        for sheet_rows in data.values():
                            for row in sheet_rows[:50]:
                                text_corpus += " " + " ".join(str(c).lower() for c in row)
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
            "lote_name": os.path.basename(lote_dir),
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
    """Executa a verificação automatizada dos 6 pilares de integridade estrutural e redacional sobre todos os arquivos do lote."""
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
    chk = checklist_file or f"{skill_name.replace('analisar-', '')}.md"

    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as tf:
            content = tf.read()
        content = content.replace('{{SKILL_NAME}}', skill_name)
        content = content.replace('{{SKILL_DESCRIPTION}}', desc)
        content = content.replace('{{SKILL_TITLE}}', title)
        content = content.replace('{{SKILL_DOMAIN}}', domain_name)
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
3. Registrar achados no `01_PONTOS_DE_ATENCAO.md` com Ficha 360° completa.
"""

    with open(skill_file, 'w', encoding='utf-8') as sf:
        sf.write(content)

    return json.dumps({
        "status": "success",
        "message": f"Rascunho da skill {skill_name} criado para validação.",
        "skill_file": skill_file
    }, indent=2, ensure_ascii=False)


def tool_run_full_audit(lote_path: str = None) -> str:
    """
    Executa o pipeline nativo e 100% dinâmico de auditoria RTI sobre os lotes em entrada/.
    Triagem adaptativa -> Extração ao vivo -> 7 Pilares -> Checklists -> JSON SSOT + HTML -> Central Master.
    """
    root = get_workspace_root()
    raw_profile = tool_profile_baseline(lote_path)
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
        ts = f"{now_str}_{lote_name}"

        rel_dir = os.path.join(root, 'analise', ts, 'relatorios')
        ent_dir = os.path.join(root, 'analise', ts, 'entrada')
        os.makedirs(rel_dir, exist_ok=True)
        os.makedirs(ent_dir, exist_ok=True)

        baseline_files = []
        documents = []
        if os.path.exists(lote_dir):
            for dirpath, _, filenames in os.walk(lote_dir):
                for fname in sorted(filenames):
                    if fname.startswith('.') or fname in ('README.md', 'decisoes.yaml'):
                        continue
                    fpath = os.path.join(dirpath, fname)
                    h = calculate_file_hash(fpath)
                    sz = os.path.getsize(fpath)
                    relative_path = os.path.relpath(fpath, lote_dir)
                    baseline_files.append({"name": clean_unicode_text(fname), "path": relative_path, "sha256": h, "size_bytes": sz})
                    extracted = extract_text_from_file(fpath)
                    documents.append({"name": clean_unicode_text(fname), "relative_path": relative_path,
                                      "ext": os.path.splitext(fname)[1].lower(), "text": extracted,
                                      "warning": "" if extracted.strip() else "Extracao sem texto retornado."})

        visual_inventory = visual_pipeline.extract_visual_inventory(
            lote_dir, os.path.join(rel_dir, "visuais"), documents)

        skills_ativas = [s["skill"] for s in p.get("skills_recommendation", [])]
        semantic_state = semantic_pipeline.initialize_semantic_state(documents, skills_ativas)

        all_findings = []
        if os.path.exists(lote_dir):
            for dirpath, _, filenames in os.walk(lote_dir):
                for fname in sorted(filenames):
                    if fname.startswith('.') or fname in ('README.md', 'decisoes.yaml'):
                        continue
                    fpath = os.path.join(dirpath, fname)
                    sf = analyze_document_structure(fpath)
                    tf = analyze_document_domain_technical(fpath, skills_ativas)
                    all_findings.extend(sf)
                    all_findings.extend(tf)

        # Correlaciona exclusivamente os documentos deste lote e normaliza o SSOT.
        all_findings.extend(specialized_controls.run_specialized_controls(documents, skills_ativas))
        all_findings.extend(advanced_specialized_controls.run(documents, skills_ativas))
        all_findings.extend(cross_document.run(documents, skills_ativas))
        all_findings.extend(tabular_visual_controls.run(documents, skills_ativas))
        all_findings.extend(audit_pipeline.find_cross_document_conflicts(documents))
        all_findings = audit_pipeline.normalize_findings(lote_name, all_findings, documents)
        coverage = audit_pipeline.build_extraction_coverage(documents)
        # Separa achados por tipo/categoria para enriquecimento dos relatórios
        achados_list = [f for f in all_findings if f.get('tipo') in ('Inconsistência', 'Erro', 'Errata/Estrutura', 'Ambiguidade')]
        lacunas_list = [f for f in all_findings if f.get('tipo') == 'Lacuna']
        riscos_list = [f for f in all_findings if f.get('tipo') == 'Risco']

        # Gera perguntas formais para lacunas e riscos de prioridade P0/P1
        esclarecimentos_list = []
        for idx, item in enumerate(lacunas_list + riscos_list, 1):
            esclarecimentos_list.append({
                'id_pergunta': f'PERG-{idx:03d}',
                'doc_ref': item.get('doc_origem', lote_name),
                'secao_ref': item.get('loc', 'Geral'),
                'pergunta': f"Favor esclarecer a seguinte pendência identificada no documento: {item.get('title')} ({item.get('fato')})",
                'justificativa': item.get('impacto', 'Mitigação de risco operacional e normativo.'),
                'destinatario': item.get('proprietario', 'Comissão Técnica / Gestor do Processo')
            })

        data = {
            'title': f"{lote_name.replace('_', ' ')}",
            'timestamp': ts,
            'baseline_files': baseline_files,
            'achados': all_findings,
            'lacunas': lacunas_list,
            'riscos': riscos_list,
            'redacoes': [],
            'erratas': [],
            'esclarecimentos': esclarecimentos_list,
            'checklists_status': audit_pipeline.build_checklist_status(p.get('active_checklists', []), all_findings, coverage),
            'skills_ativas': skills_ativas,
            'iqd_denominador': max(len(baseline_files) * 15, 30),
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
    if not re.fullmatch(r"\d{8}_\d{6}_[A-Za-z0-9_-]+", timestamp or ""):
        raise ValueError("Timestamp de análise inválido.")
    limit = max(1, min(int(limit), 8))
    offset = max(0, int(offset))
    report_dir = os.path.join(get_workspace_root(), "analise", timestamp, "relatorios")
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
    if not re.fullmatch(r"\d{8}_\d{6}_[A-Za-z0-9_-]+", timestamp or ""):
        raise ValueError("Timestamp de análise inválido.")
    if not isinstance(findings, list) or len(findings) > 100:
        raise ValueError("Informe uma lista de até 100 achados visuais.")
    root = get_workspace_root()
    rel_dir = os.path.join(root, "analise", timestamp, "relatorios")
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
            lote_name = timestamp.split("_", 2)[2]
            candidates = [
                os.path.join(root, "entrada", lote_name, text_doc_path),
                os.path.join(root, "analise", timestamp, "entrada", text_doc_path),
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
        }
        added.append(finding)
        known_ids.add(fid)

    all_findings = existing + added
    data["findings"] = all_findings
    data["lacunas"] = [item for item in all_findings if "lacuna" in str(item.get("tipo", "")).lower()]
    data["riscos"] = [item for item in all_findings if "risco" in str(item.get("tipo", "")).lower()]
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
    with open(json_path, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)

    import audit_engine
    import html_compiler
    kpis = data.setdefault("kpis", {})
    kpis["total_achados"] = len(all_findings)
    kpis["lacunas"] = len(data["lacunas"])
    kpis["riscos"] = len(data["riscos"])
    kpis["criticos"] = sum(item.get("criticidade", "").upper() == "CRÍTICA" for item in all_findings)
    kpis["altos"] = sum(item.get("criticidade", "").upper() == "ALTA" for item in all_findings)
    kpis["medios"] = sum(item.get("criticidade", "").upper() == "MÉDIA" for item in all_findings)
    kpis["baixos"] = sum(item.get("criticidade", "").upper() in ("BAIXA", "INFORMATIVA") for item in all_findings)
    raw_for_calc = [{"crit": item.get("criticidade", "Média"), "prio": item.get("prioridade", "P2")} for item in all_findings]
    _, parecer_badge = audit_engine.calculate_parecer(raw_for_calc, data["lacunas"])
    data["parecer_badge"] = parecer_badge
    data["parecer"] = audit_engine.calculate_parecer(raw_for_calc, data["lacunas"])[0]
    denom = kpis.get("iqd_denominador", max(len(data.get("baseline_files", [])) * 15, 30))
    _, kpis["iqd"], kpis["iqd_denominador"] = audit_engine.calculate_iqd(raw_for_calc, denom)
    with open(json_path, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
    html_compiler.compile_timestamp_html(timestamp, root_dir=root)
    master = json.loads(tool_build_master_index())
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
    batch_name = timestamp.split("_", 2)[2]
    relative_path = str(baseline_entry.get("path", ""))
    expected_hash = str(baseline_entry.get("sha256", ""))
    bases = [
        os.path.join(root, "entrada", batch_name),
        os.path.join(root, "analise", timestamp, "entrada"),
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
            return "\n\n".join(parts)
        except Exception:
            return ""
    if ext == ".docx":
        try:
            with zipfile.ZipFile(fpath) as archive:
                tree = ET.fromstring(archive.read("word/document.xml"))
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            parts = []
            for index, paragraph in enumerate(tree.findall(".//w:p", ns), 1):
                paragraph_text = "".join(paragraph.itertext()).strip()
                if paragraph_text:
                    parts.append(f"[Parágrafo {index}] {paragraph_text}")
            return "\n".join(parts)
        except Exception:
            return ""
    if ext in (".xlsx", ".xls"):
        try:
            sheets = extract_xlsx_data(fpath)
            parts = []
            for sheet_name, rows in sheets.items():
                for row_index, row in enumerate(rows, 1):
                    parts.append(f"[Planilha {sheet_name} · linha {row_index}] " + " | ".join(row))
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
            "text": "texto extraído" if coverage.get("status") == "extraido" else "",
        })
    state = semantic_pipeline.initialize_semantic_state(documents, data.get("skills_ativas", []))
    data["semantic_analysis"] = state
    return state


def tool_get_semantic_review_manifest(timestamp: str) -> str:
    """Lista escopos de leitura semântica, baseline e achados existentes para o agente."""
    if not re.fullmatch(r"\d{8}_\d{6}_[A-Za-z0-9_-]+", timestamp or ""):
        raise ValueError("Timestamp de análise inválido.")
    root = get_workspace_root()
    json_path = os.path.join(root, "analise", timestamp, "relatorios", "dados_analise.json")
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
    if not re.fullmatch(r"\d{8}_\d{6}_[A-Za-z0-9_-]+", timestamp or ""):
        raise ValueError("Timestamp de análise inválido.")
    root = get_workspace_root()
    json_path = os.path.join(root, "analise", timestamp, "relatorios", "dados_analise.json")
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
            and str(question.get("pergunta", "")).startswith("Favor esclarecer a seguinte pendência documental:")
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
    denom = kpis.get("iqd_denominador", max(len(data.get("baseline_files", [])) * 15, 30))
    if adjudication["pending"]:
        kpis["iqd"] = "—"
        kpis["iqd_denominador"] = denom
    else:
        _, kpis["iqd"], kpis["iqd_denominador"] = audit_engine.calculate_iqd(raw_for_calc, denom)
    json_path = os.path.join(root, "analise", timestamp, "relatorios", "dados_analise.json")
    with open(json_path, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
    html_compiler.compile_timestamp_html(timestamp, root_dir=root)
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
        searchable_text = document.get("located_text") or document.get("text", "")
        if not semantic_pipeline.quote_is_literal(searchable_text, quote):
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
    if not re.fullmatch(r"\d{8}_\d{6}_[A-Za-z0-9_-]+", timestamp or ""):
        raise ValueError("Timestamp de análise inválido.")
    if not isinstance(decisions, list) or not decisions or len(decisions) > 200:
        raise ValueError("Informe uma lista de 1 a 200 decisões de adjudicação.")
    root = get_workspace_root()
    json_path = os.path.join(root, "analise", timestamp, "relatorios", "dados_analise.json")
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


def tool_record_semantic_analysis(timestamp: str, reviewed_scopes: list[dict], findings: list[dict]) -> str:
    """Registra a revisão semântica, valida citações contra a baseline e recompila os relatórios."""
    if not re.fullmatch(r"\d{8}_\d{6}_[A-Za-z0-9_-]+", timestamp or ""):
        raise ValueError("Timestamp de análise inválido.")
    if not isinstance(reviewed_scopes, list) or len(reviewed_scopes) > 1000:
        raise ValueError("reviewed_scopes deve ser uma lista de até 1000 escopos.")
    if not isinstance(findings, list) or len(findings) > 100:
        raise ValueError("Informe uma lista de até 100 achados semânticos por chamada.")
    root = get_workspace_root()
    json_path = os.path.join(root, "analise", timestamp, "relatorios", "dados_analise.json")
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
    loaded_sources = {}
    normalized_candidates = []
    batch_name = timestamp.split("_", 2)[2]
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
            outcome = all_scope_results.get(key, {}).get("status", "revisado" if key in all_reviewed_scopes else "pendente")
            if outcome != "revisado":
                missing_source_scopes.append(path)
        if missing_source_scopes:
            raise ValueError(f"A fonte do achado não foi marcada como revisada/aplicável para {skill}: {', '.join(sorted(missing_source_scopes))}.")
        normalized_candidates.append(semantic_pipeline.normalize_semantic_finding(
            raw, loaded_sources, active_skills, batch_name))

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
    analise_dir = os.path.join(root, 'analise')
    if timestamp:
        direct_path = os.path.join(analise_dir, timestamp, 'relatorios')
        if os.path.exists(direct_path):
            return direct_path, timestamp
        # Procura em subpastas de lotes: analise/<lote>/<timestamp>/relatorios
        if os.path.exists(analise_dir):
            for entry in os.listdir(analise_dir):
                entry_path = os.path.join(analise_dir, entry)
                if os.path.isdir(entry_path):
                    candidate = os.path.join(entry_path, timestamp, 'relatorios')
                    if os.path.exists(candidate):
                        return candidate, f"{entry}/{timestamp}"
        return direct_path, timestamp
    if os.path.exists(analise_dir):
        # Procura o mais recente tanto na raiz quanto dentro de lotes
        found = []
        for d in os.listdir(analise_dir):
            dp = os.path.join(analise_dir, d)
            if not os.path.isdir(dp) or d.startswith('.'):
                continue
            if os.path.exists(os.path.join(dp, 'relatorios')):
                found.append((d, os.path.join(dp, 'relatorios'), d))
            else:
                for sub in os.listdir(dp):
                    subp = os.path.join(dp, sub)
                    if os.path.isdir(subp) and os.path.exists(os.path.join(subp, 'relatorios')):
                        found.append((sub, os.path.join(subp, 'relatorios'), f"{d}/{sub}"))
        if found:
            found.sort(key=lambda x: x[0], reverse=True)
            return found[0][1], found[0][2]
    return os.path.join(analise_dir, 'relatorios'), 'default'


def tool_validate_analise_contract(timestamp: str = None) -> str:
    """Valida se os entregáveis da RTI (index.html e dados_analise.json) existem em analise/<timestamp>/relatorios/
    ou analise/<lote>/<timestamp>/relatorios/ e verifica a cobertura de skills recomendadas em relação a decisoes.yaml."""
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

    # Validação de cobertura de skills em dados_analise.json
    data_json_path = os.path.join(rel_dir, "dados_analise.json")
    decisoes_yaml_path = os.path.join(root, "entrada", "decisoes.yaml")

    if os.path.exists(data_json_path) and os.path.exists(decisoes_yaml_path):
        try:
            with open(data_json_path, 'r', encoding='utf-8') as f:
                analise_data = json.load(f)
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
            results["validation_warnings"].append(f"Aviso ao validar cobertura de skills: {str(e)}")

    if results["missing"]:
        results["status"] = "incomplete"
    elif results["validation_warnings"]:
        results["status"] = "success_with_warnings"

    return json.dumps(results, indent=2, ensure_ascii=False)


def tool_finalize_execution(timestamp: str, lote: str = None) -> str:
    """Move arquivos do lote analisado de entrada/<lote> para analise/<lote>/<timestamp>/entrada/ (ou analise/<timestamp>/entrada/) e atualiza o índice master."""
    root = get_workspace_root()
    entrada_dir = os.path.join(root, 'entrada')

    if not timestamp:
        return json.dumps({"status": "error", "message": "Parâmetro timestamp é obrigatório."}, ensure_ascii=False)

    # Detectar o lote
    parts = timestamp.split('/')
    if len(parts) > 1:
        detected_lote = parts[0]
        actual_ts = parts[1]
    else:
        actual_ts = timestamp
        ts_parts = actual_ts.split('_', 2)
        detected_lote = lote or (ts_parts[2] if len(ts_parts) > 2 else None)

    if detected_lote:
        dest_entrada = os.path.join(root, 'analise', detected_lote, actual_ts, 'entrada')
    else:
        dest_entrada = os.path.join(root, 'analise', actual_ts, 'entrada')

    os.makedirs(dest_entrada, exist_ok=True)

    moved = []
    lote_src = os.path.join(entrada_dir, detected_lote) if detected_lote else None

    if lote_src and os.path.exists(lote_src):
        for item in os.listdir(lote_src):
            if item.startswith('.'):
                continue
            src = os.path.join(lote_src, item)
            dst = os.path.join(dest_entrada, item)
            shutil.move(src, dst)
            moved.append(f"{detected_lote}/{item}")
    else:
        for item in os.listdir(entrada_dir):
            if item.startswith('.') or item in ('README.md', 'decisoes.yaml'):
                continue
            src = os.path.join(entrada_dir, item)
            dst = os.path.join(dest_entrada, item)
            if os.path.isfile(src):
                shutil.move(src, dst)
                moved.append(item)


    # Garante .gitkeep em entrada/
    gitkeep = os.path.join(entrada_dir, '.gitkeep')
    if not os.path.exists(gitkeep):
        with open(gitkeep, 'w') as f:
            f.write('')

    # Recompila HTML e atualiza master index
    html_result = tool_build_run_index_html(timestamp)
    master_result = tool_build_master_index()

    return json.dumps({
        "status": "success", "timestamp": timestamp,
        "moved": moved, "dest_entrada": dest_entrada,
        "html": json.loads(html_result),
        "master": json.loads(master_result)
    }, indent=2, ensure_ascii=False)


def tool_build_run_index_html(timestamp: str) -> str:
    """Compila o HTML executivo da análise a partir do dados_analise.json SSOT."""
    root = get_workspace_root()
    rel_dir = os.path.join(root, 'analise', timestamp, 'relatorios')

    if not os.path.exists(rel_dir):
        return json.dumps({"status": "error", "message": f"Diretório não encontrado: {rel_dir}"}, ensure_ascii=False)

    try:
        sys.path.insert(0, os.path.dirname(__file__))
        import html_compiler
        result = html_compiler.compile_timestamp_html(timestamp, root_dir=root)
        return json.dumps({"status": "success", "message": result}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)


def sanitize_batch_isolation(text: str) -> str:
    """Remove ou neutraliza citações cruzadas a outros lotes para garantir isolamento estrito por lote."""
    if not isinstance(text, str) or not text:
        return text
    text = re.sub(r'Idêntico ao achado [A-Z]{2,5}-\d{3} do Lote \d+:?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'— mesmo padrão do Lote \d+', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\(Lote \d+\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\(Lotes \d+(?:,\s*\d+)*(?:\s*e\s*\d+)?\)', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Lote \d+ \(([^)]+)\)', r'\1', text, flags=re.IGNORECASE)
    text = re.sub(r'Lote \d+', 'especificação técnica', text, flags=re.IGNORECASE)
    return text


def clean_unicode_text(val):
    """Normaliza texto Unicode em NFC, sanitiza surrogates/mojibake e garante isolamento estrito de lote."""
    if not isinstance(val, str):
        return val
    if not val:
        return ""
    import unicodedata
    # Sanitiza surrogates inválidos de filesystem Linux
    val = val.encode('utf-8', errors='surrogateescape').decode('utf-8', errors='replace')
    val = unicodedata.normalize('NFC', val)
    val = val.replace('A\ufffdRequisitos', 'A — Requisitos')
    val = val.replace('A?Requisitos', 'A — Requisitos')
    val = val.replace('3\ufffdEm', '3ª Emissão')
    val = val.replace('3?Em', '3ª Emissão')
    val = val.replace('3Em', '3ª Emissão')
    val = val.replace('MODERNIZA\ufffdO', 'MODERNIZAÇÃO')
    val = val.replace('MODERNIZA??O', 'MODERNIZAÇÃO')
    val = val.replace('MODERNIZAO', 'MODERNIZAÇÃO')
    val = val.replace('T\ufffdcnica', 'Técnica')
    val = val.replace('T?cnica', 'Técnica')
    val = val.replace('Tcnica', 'Técnica')
    val = val.replace('Especifica\ufffd\ufffdo', 'Especificação')
    val = val.replace('Especifica??o', 'Especificação')
    val = val.replace('Especificao', 'Especificação')
    val = val.replace('Moderniza\ufffd\ufffdo', 'Modernização')
    val = val.replace('Moderniza??o', 'Modernização')
    val = val.replace('Modernizao', 'Modernização')
    val = val.replace('An\ufffdlise', 'Análise')
    val = val.replace('An?lise', 'Análise')
    val = val.replace('Anlise', 'Análise')
    val = val.replace('Comentario \ufffd', 'Comentário —')
    val = val.replace('Comentario ?', 'Comentário —')
    val = val.replace(' \ufffd ', ' — ')
    val = val.replace('\ufffd', '')
    return sanitize_batch_isolation(val)


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

    # Escaneia pastas de relatórios por lote e timestamp (suporta analise/<timestamp> e analise/<lote>/<timestamp>)
    candidates = []
    for entry in sorted(os.listdir(analise_dir), reverse=True):
        entry_dir = os.path.join(analise_dir, entry)
        if not os.path.isdir(entry_dir) or entry.startswith('.'):
            continue
        rel_direct = os.path.join(entry_dir, 'relatorios')
        if os.path.exists(rel_direct):
            candidates.append((entry, None, entry_dir, rel_direct))
        else:
            for sub_ts in sorted(os.listdir(entry_dir), reverse=True):
                sub_dir = os.path.join(entry_dir, sub_ts)
                rel_sub = os.path.join(sub_dir, 'relatorios')
                if os.path.isdir(sub_dir) and os.path.exists(rel_sub):
                    candidates.append((sub_ts, entry, sub_dir, rel_sub))

    for ts, lote_parent, ts_dir, rel_dir in candidates:
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
                _refresh_analysis_outputs(data_json, ts, root, build_master=False)

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
                        resumo_snippet = f"Análise concluída com parecer <strong>NÃO APTO PARA DECISÃO</strong>. Lote bloqueado por {criticos} achado(s) crítico(s) e {altos} de alta severidade, destacando-se: {top_achados[0]['title']} ({top_achados[0]['id']})."
                    else:
                        resumo_snippet = f"Análise concluída com parecer <strong>NÃO APTO PARA DECISÃO</strong> devido a inconsistências técnicas e lacunas de alto impacto no lote ({total_achados} achados)."
                else:
                    if top_achados:
                        resumo_snippet = f"Análise concluída com parecer <strong>APTO COM RESSALVAS</strong> (IQD {iqd}). Requer atenção técnica para: {top_achados[0]['title']} ({top_achados[0]['id']})."
                    else:
                        resumo_snippet = f"Análise concluída com parecer <strong>APTO COM RESSALVAS</strong> (IQD {iqd}). Documentação consistente, registrando apenas {total_achados} apontamento(s) de menor gravidade."
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
        ent_dir = os.path.join(analise_dir, ts, 'entrada')
        entrada_files = []
        if os.path.exists(ent_dir):
            for dirpath, _, filenames in os.walk(ent_dir):
                for fname in sorted(filenames):
                    if not fname.startswith('.'):
                        entrada_files.append(clean_unicode_text(fname))
        if not entrada_files and json_files:
            entrada_files = json_files

        runs.append({
            "timestamp": ts,
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
            "index_html": f"{lote_parent}/{ts}/relatorios/index.html" if lote_parent else f"{ts}/relatorios/index.html",
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

    manifest = {
        "updated_at": datetime.datetime.now().isoformat(),
        "total_analyses": len(runs),
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
        total_criticos = sum(r["metrics"]["criticos"] for r in runs)
        total_lacunas = sum(r["metrics"]["lacunas"] for r in runs)
        
        # Média numérica do IQD
        iqd_nums = []
        for r in runs:
            v_str = r["metrics"]["iqd"].replace('%', '').replace(',', '.').strip()
            try:
                iqd_nums.append(float(v_str))
            except ValueError:
                pass
        avg_iqd_str = f"{sum(iqd_nums)/len(iqd_nums):.1f}%" if iqd_nums else "—"

        for r in runs:
            m = r["metrics"]
            files_html = ", ".join([f'<code>{fn}</code>' for fn in r["files"][:3]]) or "<code>Baseline</code>"
            if len(r["files"]) > 3:
                files_html += f" (+{len(r['files'])-3} arquivos)"

            skills_html = "".join([f'<span class="skill-badge"><i class="fa-solid fa-wand-magic-sparkles"></i> {sk}</span>' for sk in r["skills"]])

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
                      <span class="top-achado-id">{ta['id']}</span>
                      <div><strong>{ta['title']}</strong> <span style="font-size:0.75rem; color:#b91c1c;">({ta['doc']})</span></div>
                    </li>"""
                top_achados_html = f"""
                <div class="top-achados-box">
                    <div class="top-achados-title"><i class="fa-solid fa-triangle-exclamation"></i> Principais Achados de Risco (Top P0/P1):</div>
                    <ul class="top-achados-list">
                      {items_html}
                    </ul>
                </div>"""

            search_str = f"{r['timestamp']} {r['title']} {r['lote_name']} {r['date_formatted']} {' '.join(r['skills'])} {r['resumo_snippet']} {card_status_cls}".lower()

            resumo_html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', r['resumo_snippet'])
            resumo_html = re.sub(r'`(.*?)`', r'<code>\1</code>', resumo_html).replace('**', '')

            cards_html += f"""
            <div class="run-card {card_status_cls}" data-search="{search_str}" data-parecer="{card_status_cls}">
                <div class="run-card-header">
                    <div>
                        <div class="run-date"><i class="fa-solid fa-calendar-day"></i> {r['date_formatted']}</div>
                        <h3 class="run-title">{r['title']}</h3>
                    </div>
                    <span class="badge {parecer_cls}">{r['parecer']}</span>
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
                        <div class="metric-sub"><span class="lbl">IQD</span><span class="val iqd">{m['iqd']}</span></div>
                    </div>
                </div>
                <div class="run-card-footer">
                    <a href="{r['index_html']}" class="btn-open-report"><i class="fa-solid fa-chart-column"></i> Abrir Relatório Consolidado HTML</a>
                </div>
            </div>"""

            rows_html += f"""
            <tr data-search="{search_str}" data-parecer="{card_status_cls}">
                <td><code>{r['timestamp']}</code><br><span class="run-date">{r['date_formatted']}</span></td>
                <td><strong>{r['lote_name']}</strong><br><span style="font-size:0.75rem; color:var(--text-muted);">{files_html}</span></td>
                <td><span class="badge {parecer_cls}">{r['parecer']}</span></td>
                <td><strong style="color:var(--success); font-size:1.05rem;">{m['iqd']}</strong></td>
                <td>
                  <div style="font-size:0.78rem;">
                    <strong>Total:</strong> {m['total_achados']}<br>
                    <strong style="color:#b45309">Pendentes:</strong> {m['pendentes_adjudicacao']} | <strong style="color:#15803d">Confirmados:</strong> {m['confirmados']}<br>
                    <strong style="color:var(--danger)">Críticos:</strong> {m['criticos']} | <strong style="color:var(--warning)">Lacunas:</strong> {m['lacunas']}
                  </div>
                </td>
                <td><div style="max-width:400px; font-size:0.82rem; color:var(--text-main);">{resumo_html}</div></td>
                <td><a href="{r['index_html']}" class="btn-open-report" style="padding:6px 10px; font-size:0.75rem;"><i class="fa-solid fa-arrow-up-right-from-square"></i> Abrir</a></td>
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
            "lote_path": {"type": "string", "description": "Caminho relativo do lote específico. Se omitido, detecta todos os lotes em entrada/."}
        }, "required": []}
    },
    {
        "name": "run_full_audit",
        "description": "Executa auditoria isolada de um lote, extrai imagens para inventário visual e gera SSOT/HTML. Depois, use get_visual_assets para inspeção multimodal e record_visual_analysis para persistir achados visuais.",
        "inputSchema": {"type": "object", "properties": {"lote_path": {"type": "string", "description": "Caminho relativo do lote em entrada/."}}, "required": []}
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
            }, "required": ["skill", "title", "tipo", "criticidade", "prioridade", "fato", "impacto"]}}
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
                "reviewer": {"type": "string"}
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
        "description": "Move os arquivos do lote de entrada/ para analise/<timestamp>/entrada/ e atualiza analise/index.html.",
        "inputSchema": {"type": "object", "properties": {
            "timestamp": {"type": "string", "description": "Timestamp completo da análise (YYYYMMDD_HHMMSS_NOME_LOTE)."}
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
        return tool_profile_baseline(args.get("lote_path"))
    elif name == "check_environment":
        return tool_check_environment()
    elif name == "run_full_audit":
        return tool_run_full_audit(args.get("lote_path"))
    elif name == "record_visual_analysis":
        return tool_record_visual_analysis(args.get("timestamp", ""), args.get("reviewed_asset_ids", []), args.get("findings", []))
    elif name == "get_semantic_review_manifest":
        return tool_get_semantic_review_manifest(args.get("timestamp", ""))
    elif name == "get_semantic_document_chunk":
        return tool_get_semantic_document_chunk(args.get("timestamp", ""), args.get("document_path", ""),
                                                args.get("start_char", 0), args.get("max_chars", 12000))
    elif name == "record_semantic_analysis":
        return tool_record_semantic_analysis(args.get("timestamp", ""), args.get("reviewed_scopes", []), args.get("findings", []))
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
        return tool_finalize_execution(args.get("timestamp", ""))
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
                "serverInfo": {"name": "fca-eng-001-rti", "version": "2.0.0"}
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
