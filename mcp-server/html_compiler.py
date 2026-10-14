#!/usr/bin/env python3
"""
Compilador HTML da RTI — FCA-ENG-001 v3.2
Gera o Relatório Consolidado Exaustivo HTML (index.html) no estilo visual corporativo
moderno (Inter + Outfit, Hero Card Gradient, KPI Grid, Sidebar Colapsável por Padrão, Filtros Interativos por Categoria, De-Para Copiável e Print CSS).

Hierarquia de Seções Atualizada (8 Seções Sequenciais):
1. Resumo Executivo & Matriz de Skills (#resumo)
2. Matriz Master SSOT de Achados (#matriz-master) — Tabela consolidada com links âncora por ID
3. Caderno de Fichas 360° Detalhadas (#fichas) — Cards com filtro por Categoria, Criticidade, Tipo, Documento e Busca
4. Caderno de Erratas (De → Para) (#erratas) — Substituições diretas com IDs linkados e cópia
5. Planos de Ação & Perguntas Formais (#acoes-perguntas) — Matriz de governança e ofícios formais com IDs linkados
6. Mapeamento de Lacunas Estratégicas & Matriz de Riscos (#lacunas-riscos) — Matriz de riscos com IDs linkados
7. Status de Conformidade por Checklist de Domínio (#checklists)
8. Rastreabilidade de Baseline & Hashes SHA-256 (#rastreabilidade) — Inventário final isolado

Zero hardcodes, 100% dinâmico e seguro.
"""

import os
import sys
import re
import json
import base64
import mimetypes
import unicodedata
import html

ADJUDICATION_LABELS = {
    "pendente": "Pendente de adjudicação",
    "confirmado": "Confirmado",
    "falso_positivo": "Falso positivo",
    "fora_de_escopo": "Fora de escopo",
    "evidencia_insuficiente": "Evidência insuficiente",
    "duplicado": "Duplicado",
}


def _adjudication_status(finding: dict) -> str:
    metadata = finding.get("adjudication")
    status = metadata.get("status") if isinstance(metadata, dict) else finding.get("adjudication_status")
    return status if isinstance(status, str) and status in ADJUDICATION_LABELS else "pendente"


def _confirmed_findings(findings: list[dict]) -> list[dict]:
    return [finding for finding in findings if _adjudication_status(finding) == "confirmado"]


def _adjudication_counts(findings: list[dict]) -> dict:
    counts = {status: 0 for status in ADJUDICATION_LABELS}
    for finding in findings:
        counts[_adjudication_status(finding)] += 1
    return counts


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


def _read_md(rel_dir: str, filename: str) -> str:
    p = os.path.join(rel_dir, filename)
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8', errors='ignore') as f:
            return clean_unicode_text(f.read())
    return ""


def _extract_value(text: str, pattern: str, fallback: str = "—") -> str:
    m = re.search(pattern, text, re.IGNORECASE)
    return clean_unicode_text(m.group(1).strip()) if m else fallback


def _inline_md(text: str, linkify_ids: bool = False) -> str:
    if not text:
        return ""
    text = clean_unicode_text(text)
    # **negrito**
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    # *itálico*
    text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', text)
    # `código`
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)

    # Autolink IDs de achados (ex: RFP-001 -> link âncora)
    if linkify_ids:
        def replace_id(match):
            found_id = match.group(0)
            return f'<a href="#card-{found_id}" class="id-link">{found_id}</a>'
        text = re.sub(r'\b[A-Z]{2,5}-\d{3}\b', replace_id, text)

    return text


def _md_to_html_simple(md: str, linkify_ids: bool = False) -> str:
    """Converte Markdown em HTML com tabelas e formatação básica, linkando IDs se solicitado."""
    if not md:
        return "<p class='empty-msg'><em>Nenhum registro encontrado nesta dimensão.</em></p>"

    html_lines = []
    in_table = False
    thead_done = False

    for line in md.splitlines():
        stripped = line.strip()

        # Tabelas Markdown
        if stripped.startswith('|') and stripped.endswith('|'):
            if not in_table:
                html_lines.append('<div class="table-responsive"><table class="rpt-table"><thead>')
                in_table = True
                thead_done = False
            cells = [c.strip() for c in stripped.strip('|').split('|')]
            if all(re.match(r'^[-:]+$', c.replace(' ', '')) for c in cells if c):
                if not thead_done:
                    html_lines.append('</thead><tbody>')
                    thead_done = True
                continue
            tag = 'th' if not thead_done else 'td'
            row = ''.join(f'<{tag}>{_inline_md(c, linkify_ids)}</{tag}>' for c in cells)
            html_lines.append(f'<tr>{row}</tr>')
            continue

        if in_table:
            html_lines.append('</tbody></table></div>')
            in_table = False
            thead_done = False

        # Títulos
        if stripped.startswith('#### '):
            html_lines.append(f'<h4 class="md-h4">{_inline_md(stripped[5:], linkify_ids)}</h4>')
        elif stripped.startswith('### '):
            html_lines.append(f'<h3 class="md-h3">{_inline_md(stripped[4:], linkify_ids)}</h3>')
        elif stripped.startswith('## '):
            html_lines.append(f'<h2 class="md-h2">{_inline_md(stripped[3:], linkify_ids)}</h2>')
        elif stripped.startswith('# '):
            html_lines.append(f'<h1 class="md-h1">{_inline_md(stripped[2:], linkify_ids)}</h1>')
        # Blockquote
        elif stripped.startswith('> '):
            html_lines.append(f'<blockquote class="md-quote">{_inline_md(stripped[2:], linkify_ids)}</blockquote>')
        # Listas
        elif stripped.startswith('- ') or stripped.startswith('* '):
            html_lines.append(f'<li class="md-li">{_inline_md(stripped[2:], linkify_ids)}</li>')
        elif re.match(r'^\d+\. ', stripped):
            item_txt = re.sub(r'^\d+\. ', '', stripped)
            html_lines.append(f'<li class="md-li-num">{_inline_md(item_txt, linkify_ids)}</li>')
        # Divisores
        elif stripped in ('---', '***', '___'):
            html_lines.append('<hr class="md-hr">')
        elif not stripped:
            html_lines.append('<div class="spacer"></div>')
        else:
            html_lines.append(f'<p class="md-p">{_inline_md(stripped, linkify_ids)}</p>')

    if in_table:
        html_lines.append('</tbody></table></div>')

    return '\n'.join(html_lines)


def _inline_md(text: str, linkify_ids: bool = False) -> str:
    """Converte Markdown inline para tags HTML, linkando IDs de achado quando ativado."""
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank">\1</a>', text)

    if linkify_ids:
        # Transforma menções como ESTR-001, HLD-001, LGPD-001 em links para os cards
        text = re.sub(r'\b([A-Z]{2,6}-\d{3})\b', r'<a href="#card-\1" class="ssot-link"><i class="fa-solid fa-arrow-right-to-bracket"></i> \1</a>', text)

    return text


def _parse_findings(pontos_md: str) -> list:
    """Fallback parser de Fichas 360° em Markdown."""
    findings = []
    blocks = re.split(r'### 📌 ', pontos_md)
    for block in blocks[1:]:
        lines = block.strip().splitlines()
        first = lines[0] if lines else ""

        m_id = re.search(r'\[?([A-Z]{2,6}-\d{3})\]?', first)
        fid = m_id.group(1) if m_id else f"ACH-{len(findings)+1:03d}"
        title = re.sub(r'\[?[A-Z]{2,6}-\d{3}\]?\s*', '', first).strip(' -:—')

        def get_field(label: str) -> str:
            for l in lines:
                if label.lower() in l.lower():
                    parts = l.split('|')
                    if len(parts) >= 3:
                        return parts[2].strip()
                    parts2 = l.split(':', 1)
                    if len(parts2) > 1:
                        return parts2[1].strip()
            return ""

        def get_block(label: str) -> str:
            collecting = False
            result = []
            for l in lines:
                l_lower = l.lower()
                if label.lower() in l_lower and (l.strip().startswith('#') or '**' in l):
                    collecting = True
                    continue
                if collecting:
                    if l.strip().startswith('#') or (l.strip().startswith('**') and '**:' in l):
                        break
                    if l.strip().startswith('---'):
                        break
                    txt = l.strip().lstrip('> ')
                    if txt:
                        result.append(txt)
            return ' '.join(result)

        crit_raw = get_field("Criticidade")
        crit = "Crítica" if "crítica" in crit_raw.lower() else \
               "Alta" if "alta" in crit_raw.lower() else \
               "Média" if "média" in crit_raw.lower() else \
               "Baixa" if "baixa" in crit_raw.lower() else "Informativa"

        prio_m = re.search(r'(P[0-3])', get_field("Prioridade"))
        prio = prio_m.group(1) if prio_m else "P2"

        tipo = get_field("Tipo de Achado") or "Erro Técnico"
        tipo_sol = get_field("Tipo de Solução")

        de_txt, para_txt = "", ""
        for l in lines:
            if "texto atual" in l.lower() or "(de)" in l.lower() or "baseline" in l.lower():
                m = re.search(r'"([^"]+)"', l)
                if m: de_txt = m.group(1)
            if "texto sugerido" in l.lower() or "(para)" in l.lower() or "minuta" in l.lower():
                m = re.search(r'"([^"]+)"', l)
                if m: para_txt = m.group(1)

        is_direct = bool(de_txt or para_txt or "direta" in tipo_sol.lower() or "→" in tipo_sol or "->" in tipo_sol or "grafia" in tipo.lower() or "sequência" in tipo.lower())

        findings.append({
            "id": fid,
            "title": title,
            "doc_origem": get_field("Documento de Origem") or "Documento Baseline",
            "loc": get_field("Localização Exata") or "Seção Geral",
            "categoria": get_field("Categoria") or "Geral",
            "tipo": tipo,
            "evidencia": get_field("Grau de Evidência") or "E2 (Corroborado)",
            "criticidade": crit,
            "prioridade": prio,
            "fato": get_block("Fato Observado") or "Fato reportado na análise.",
            "impacto": get_block("Impacto Potencial") or "Impacto não especificado.",
            "solucao": get_block("Plano de Solução") or get_block("Plano de Ação") or get_block("Solução") or "",
            "de": de_txt,
            "para": para_txt,
            "is_direct": is_direct,
            "proprietario": get_field("Proprietário Sugerido") or "Proprietário Técnico"
        })
    return findings


def _resolve_image_data_uri_or_path(rel_path: str, base_dir: str = None, max_bytes_inline: int = 4 * 1024 * 1024) -> str:
    """Retorna data URI em base64 se o arquivo existir localmente para gerar HTML autocontido e portátil."""
    if not rel_path:
        return ""
    if base_dir:
        full_path = os.path.join(base_dir, rel_path)
        if os.path.isfile(full_path):
            try:
                size = os.path.getsize(full_path)
                if size <= max_bytes_inline:
                    ext = os.path.splitext(full_path)[1].lower()
                    mime = mimetypes.guess_type(full_path)[0] or "image/png"
                    if ext == ".svg":
                        mime = "image/svg+xml"
                    with open(full_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("ascii")
                    return f"data:{mime};base64,{b64}"
            except Exception:
                pass
    return f"./{rel_path}"


def _build_resumo_html(data_json: dict) -> str:
    resumo_md = data_json.get("resumo_md", "").strip()
    if resumo_md and not data_json.get("adjudication_summary"):
        return _md_to_html_simple(resumo_md, linkify_ids=True)
    
    parecer = data_json.get("parecer", "APTO COM RESSALVAS")
    kpis = data_json.get("kpis", {})
    baseline_files = data_json.get("baseline_files", [])
    skills_ativas = data_json.get("skills_ativas", ["analisar-documento"])
    timestamp = data_json.get("timestamp", "—")
    title = data_json.get("title", "Revisão Técnica Independente")
    coverage = data_json.get("cobertura_extracao", {})
    coverage_html = f"<tr><td>Arquivos extraídos com texto</td><td><strong>{coverage.get('extraidos', 0)}</strong> de {coverage.get('total_arquivos', len(baseline_files))}</td></tr><tr><td>Arquivos não verificáveis</td><td><strong>{coverage.get('nao_verificaveis', 0)}</strong></td></tr>"
    semantic = data_json.get("semantic_analysis", {})
    semantic_status = html.escape(str(semantic.get("status", "não iniciada")))
    semantic_reviewed = int(semantic.get("reviewed_scope_count", len(semantic.get("reviewed_scopes", [])) or 0))
    semantic_expected = int(semantic.get("expected_scope_count", len(semantic.get("required_scopes", [])) or 0))
    semantic_html = f"<tr><td>Revisão semântica especializada</td><td><strong>{semantic_status}</strong> · {semantic_reviewed} de {semantic_expected} escopos</td></tr>"
    pending = int(kpis.get("achados_pendentes_adjudicacao", 0))
    adjudication_note = (
        f'<div class="ssot-intro-note"><strong>Adjudicação:</strong> {kpis.get("achados_confirmados", 0)} confirmado(s), '
        f'{pending} pendente(s) e {kpis.get("achados_excluidos", 0)} excluído(s) com justificativa. '
        + ("O parecer permanece pendente; candidatos não revisados não contam como riscos confirmados." if pending else "O parecer considera somente achados confirmados.")
        + "</div>"
    )

    baseline_rows = ""
    for bf in baseline_files:
        name = bf.get("name", bf.get("filename", "—"))
        size = bf.get("size_bytes", bf.get("size", 0))
        h = bf.get("sha256", "—")
        baseline_rows += f"<tr><td><code>{name}</code></td><td>{size} bytes</td><td><code>{h}</code></td></tr>"

    if not baseline_rows:
        baseline_rows = '<tr><td colspan="3">Nenhum arquivo de baseline registrado.</td></tr>'

    skills_badges = "".join([f'<span class="badge-skill" style="display:inline-block; margin:4px; padding:6px 12px; background:var(--primary-light); color:var(--primary); border-radius:6px; font-weight:600;"><i class="fa-solid fa-microchip"></i> {s}</span>' for s in skills_ativas])

    return f"""
    <div class="resumo-executivo-container">
        {adjudication_note}
        <h3>Parecer Técnico da Análise</h3>
        <p>A Revisão Técnica Independente (RTI) analisou o lote <strong>"{title}"</strong> (Timestamp: <code>{timestamp}</code>) e concluiu com o parecer <strong>{parecer}</strong>.</p>
        
        <h4 style="margin-top:20px;">Resumo dos KPIs da Auditoria</h4>
        <table class="rpt-table">
            <thead>
                <tr>
                    <th>Indicador</th>
                    <th>Valor</th>
                </tr>
            </thead>
            <tbody>
                <tr><td>Total de Achados</td><td><strong>{kpis.get("total_achados", 0)}</strong></td></tr>
                <tr><td>Achados Confirmados</td><td><strong>{kpis.get("achados_confirmados", 0)}</strong></td></tr>
                <tr><td>Pendentes de Adjudicação</td><td><strong>{pending}</strong></td></tr>
                <tr><td>Excluídos com Justificativa</td><td>{kpis.get("achados_excluidos", 0)}</td></tr>
                <tr><td>Achados Críticos (P0)</td><td><strong style="color:var(--danger);">{kpis.get("criticos", 0)}</strong></td></tr>
                <tr><td>Achados Altos (P1)</td><td><strong style="color:var(--accent);">{kpis.get("altos", 0)}</strong></td></tr>
                <tr><td>Achados Médios</td><td>{kpis.get("medios", 0)}</td></tr>
                <tr><td>Achados Baixos / Informativos</td><td>{kpis.get("baixos", 0)}</td></tr>
                <tr><td>Lacunas Mapeadas</td><td><strong>{kpis.get("lacunas", 0)}</strong></td></tr>
                <tr><td>Riscos Identificados</td><td><strong>{kpis.get("riscos", 0)}</strong></td></tr>
                <tr><td>Minutas / Erratas Sugeridas</td><td>{kpis.get("redacoes", 0)}</td></tr>
                <tr><td>Perguntas Formais (Q-XXX)</td><td>{kpis.get("perguntas", 0)}</td></tr>
                <tr><td>Índice IQD (Qualidade Documental)</td><td><strong style="color:var(--success);">{kpis.get("iqd", "100%")}</strong></td></tr>
                {coverage_html}
                {semantic_html}
            </tbody>
        </table>
        
        <h4 style="margin-top:25px;">Baseline de Documentos de Entrada</h4>
        <table class="rpt-table">
            <thead>
                <tr>
                    <th>Nome do Arquivo</th>
                    <th>Tamanho</th>
                    <th>Hash SHA-256</th>
                </tr>
            </thead>
            <tbody>
                {baseline_rows}
            </tbody>
        </table>
        
        <h4 style="margin-top:25px;">Skills e Agentes Especializados Ativados</h4>
        <div class="skills-grid" style="margin-top:10px;">
            {skills_badges}
        </div>
    </div>
    """


def _build_acoes_html(data_json: dict) -> str:
    acoes_md = data_json.get("acoes_md", "").strip()
    if acoes_md and not data_json.get("adjudication_summary"):
        return _md_to_html_simple(acoes_md, linkify_ids=True)

    findings = data_json.get("findings", [])
    confirmed_ids = {str(item.get("id", "")) for item in _confirmed_findings(findings)}
    redacoes = [item for item in data_json.get("redacoes", []) if str(item.get("achado_id", item.get("achado", ""))) in confirmed_ids]
    esclarecimentos = [item for item in data_json.get("esclarecimentos", []) if str(item.get("finding_id", "")) in confirmed_ids]

    act_rows = ""
    if redacoes:
        for idx, r in enumerate(redacoes, 1):
            aid = r.get("id", f"ACT-{idx:03d}")
            achado_id = r.get("achado_id", r.get("achado", "—"))
            achado_link = f'<a href="#card-{achado_id}" class="ssot-link">{achado_id}</a>' if achado_id != "—" else "—"
            desc = r.get("acao", r.get("descricao", "—"))
            prio = r.get("prio", r.get("prioridade", "P2"))
            resp = r.get("responsavel", r.get("proprietario", "Equipe Técnica"))
            act_rows += f"<tr><td><strong>{aid}</strong></td><td>{achado_link}</td><td>{desc}</td><td><span class='badge-prio'>{prio}</span></td><td>{resp}</td></tr>"
    else:
        for idx, f in enumerate(_confirmed_findings(findings), 1):
            if f.get("solucao"):
                fid = f.get("id", "ACH-000")
                act_rows += f"<tr><td><strong>ACT-{idx:03d}</strong></td><td><a href='#card-{fid}' class='ssot-link'>{fid}</a></td><td>{f['solucao']}</td><td><span class='badge-prio'>{f.get('prioridade','P2')}</span></td><td>{f.get('proprietario','Proprietário Técnico')}</td></tr>"

    if not act_rows:
        act_rows = '<tr><td colspan="5">Nenhum plano de ação registrado separadamente. Consulte as Fichas 360°.</td></tr>'

    q_rows = ""
    for idx, esc in enumerate(esclarecimentos, 1):
        qid = esc.get("id", f"Q-{idx:03d}")
        doc = esc.get("doc", esc.get("documento", "—"))
        perg = esc.get("pergunta", "—")
        imp = esc.get("impacto", esc.get("contexto", "—"))
        dest = esc.get("destinatario", "Comissão Técnica")
        q_rows += f"<tr><td><strong>{qid}</strong></td><td><code>{doc}</code></td><td>{perg}</td><td>{imp}</td><td>{dest}</td></tr>"

    if not q_rows:
        q_rows = '<tr><td colspan="5">Nenhuma pergunta formal registrada nesta auditoria.</td></tr>'

    return f"""
    <div class="acoes-perguntas-container">
        <h3>Matriz de Planos de Ação (ACT-XXX)</h3>
        <div class="table-responsive">
            <table class="rpt-table">
                <thead>
                    <tr>
                        <th>ID Ação</th>
                        <th>Achado Vinculado</th>
                        <th>Ação Recomendada</th>
                        <th>Prioridade</th>
                        <th>Responsável Sugerido</th>
                    </tr>
                </thead>
                <tbody>
                    {act_rows}
                </tbody>
            </table>
        </div>

        <h3 style="margin-top:35px;">Ofício de Perguntas Formais de Esclarecimento (Q-XXX)</h3>
        <div class="table-responsive">
            <table class="rpt-table">
                <thead>
                    <tr>
                        <th>ID Pergunta</th>
                        <th>Documento / Seção</th>
                        <th>Pergunta Formal</th>
                        <th>Impacto se não Esclarecido</th>
                        <th>Destinatário Sugerido</th>
                    </tr>
                </thead>
                <tbody>
                    {q_rows}
                </tbody>
            </table>
        </div>
    </div>
    """


def _build_lacunas_html(data_json: dict) -> str:
    lacunas_md = data_json.get("lacunas_md", "").strip()
    if lacunas_md and not data_json.get("adjudication_summary"):
        return _md_to_html_simple(lacunas_md, linkify_ids=True)

    lacunas = data_json.get("lacunas", [])
    riscos = data_json.get("riscos", [])
    findings = data_json.get("findings", [])

    lac_rows = ""
    if lacunas:
        for idx, lac in enumerate(lacunas, 1):
            lid = lac.get("id", f"LAC-{idx:03d}")
            doc = lac.get("doc", lac.get("documento", "—"))
            desc = lac.get("descricao", lac.get("titulo", "—"))
            crit = lac.get("crit", lac.get("criticidade", "Média"))
            mitig = lac.get("mitigacao", lac.get("acao_sugerida", "Formular pergunta formal."))
            c_class = "crit-critica" if "crítica" in crit.lower() else "crit-alta" if "alta" in crit.lower() else "crit-media"
            lac_rows += f"<tr><td><strong>{lid}</strong></td><td><code>{doc}</code></td><td>{desc}</td><td><span class='badge-crit {c_class}'>{crit}</span></td><td>{mitig}</td></tr>"
    else:
        lac_findings = [f for f in _confirmed_findings(findings) if "lacuna" in f.get("tipo","").lower() or "lacuna" in f.get("categoria","").lower() or "omissão" in f.get("tipo","").lower()]
        for f in lac_findings:
            fid = f.get("id", "ACH-000")
            crit = f.get("criticidade", "Média")
            c_class = "crit-critica" if "crítica" in crit.lower() else "crit-alta" if "alta" in crit.lower() else "crit-media"
            lac_rows += f"<tr><td><a href='#card-{fid}' class='ssot-link'>{fid}</a></td><td><code>{f.get('doc_origem','—')}</code></td><td>{f['title']} — {f.get('fato','')}</td><td><span class='badge-crit {c_class}'>{crit}</span></td><td>{f.get('solucao','Solicitar esclarecimento.')}</td></tr>"

    if not lac_rows:
        lac_rows = '<tr><td colspan="5">Nenhuma lacuna registrada nesta análise.</td></tr>'

    rsc_rows = ""
    if riscos:
        for idx, rsc in enumerate(riscos, 1):
            rid = rsc.get("id", f"RSC-{idx:03d}")
            ev = rsc.get("evento", rsc.get("titulo", "—"))
            prob = rsc.get("prob", rsc.get("probabilidade", "Média"))
            imp = rsc.get("impacto", "Médio")
            mitig = rsc.get("mitigacao", "—")
            rsc_rows += f"<tr><td><strong>{rid}</strong></td><td>{ev}</td><td>{prob}</td><td>{imp}</td><td>{mitig}</td></tr>"
    else:
        rsc_findings = [f for f in _confirmed_findings(findings) if "risco" in f.get("tipo","").lower() or "risco" in f.get("categoria","").lower()]
        for f in rsc_findings:
            fid = f.get("id", "ACH-000")
            rsc_rows += f"<tr><td><a href='#card-{fid}' class='ssot-link'>{fid}</a></td><td>{f['title']}</td><td>Média</td><td>{f.get('impacto','Médio')}</td><td>{f.get('solucao','—')}</td></tr>"

    if not rsc_rows:
        rsc_rows = '<tr><td colspan="5">Nenhum risco registrado separadamente. Consulte as Fichas 360°.</td></tr>'

    return f"""
    <div class="lacunas-riscos-container">
        <h3>Lacunas Estratégicas Mapeadas</h3>
        <div class="table-responsive">
            <table class="rpt-table">
                <thead>
                    <tr>
                        <th>ID Lacuna</th>
                        <th>Documento / Seção</th>
                        <th>Descrição da Lacuna</th>
                        <th>Criticidade</th>
                        <th>Ação Mitigatória Recomendada</th>
                    </tr>
                </thead>
                <tbody>
                    {lac_rows}
                </tbody>
            </table>
        </div>

        <h3 style="margin-top:35px;">Matriz de Riscos Mapeados</h3>
        <div class="table-responsive">
            <table class="rpt-table">
                <thead>
                    <tr>
                        <th>ID Risco</th>
                        <th>Evento de Risco</th>
                        <th>Probabilidade</th>
                        <th>Impacto Potencial</th>
                        <th>Mitigação Recomendada</th>
                    </tr>
                </thead>
                <tbody>
                    {rsc_rows}
                </tbody>
            </table>
        </div>
    </div>
    """


def _build_checklists_html(data_json: dict) -> str:
    checklists_md = data_json.get("checklists_md", "").strip()
    if checklists_md:
        return _md_to_html_simple(checklists_md, linkify_ids=False)

    checklists_status = data_json.get("checklists_status", {})
    if not checklists_status:
        return "<p class='empty-msg'><em>Nenhum status de checklist informado nesta análise.</em></p>"

    html_out = "<div class='checklists-container'>"
    for chk_name, chk_data in checklists_status.items():
        html_out += f"<div class='checklist-card' style='margin-bottom:25px;'><h4 style='color:var(--primary);'><i class='fa-solid fa-square-check'></i> Checklist: <code>{chk_name}</code></h4>"
        if isinstance(chk_data, dict) and "itens" in chk_data:
            itens = chk_data["itens"]
            html_out += """<div class='table-responsive'><table class='rpt-table'>
                <thead><tr><th>Verificação</th><th>Status</th><th>Achado Vinculado</th><th>Evidência</th></tr></thead><tbody>"""
            for item in itens:
                st = item.get("status", "").lower().replace(" ", "_")
                badge_st = '<span class="badge-crit crit-baixa">Conforme</span>' if "conforme" in st and "nao" not in st else \
                           '<span class="badge-crit crit-critica">Não Conforme</span>' if "nao_conforme" in st else \
                           '<span class="badge-crit crit-info">N/A</span>'
                achado_id = item.get("achado", "—")
                achado_link = f'<a href="#card-{achado_id}" class="ssot-link">{achado_id}</a>' if achado_id and achado_id != "—" else "—"
                html_out += f"<tr><td>{item.get('verificacao','—')}</td><td>{badge_st}</td><td>{achado_link}</td><td>{item.get('evidencia','—')}</td></tr>"
            html_out += "</tbody></table></div>"
        elif isinstance(chk_data, dict):
            conf = chk_data.get("conformidade_pct", "—")
            obs = chk_data.get("observacao", "Checklist verificado.")
            html_out += f"<p><strong>Conformidade:</strong> {conf} | <strong>Observação:</strong> {obs}</p>"
        html_out += "</div>"
    html_out += "</div>"
    return html_out


def _build_rastrea_html(data_json: dict, rel_dir: str = None) -> str:
    rastrea_md = data_json.get("rastrea_md", "").strip()
    if rastrea_md:
        return _md_to_html_simple(rastrea_md, linkify_ids=False)

    baseline_files = data_json.get("baseline_files", [])
    timestamp = data_json.get("timestamp", "—")
    skills_ativas = data_json.get("skills_ativas", ["analisar-documento"])
    kpis = data_json.get("kpis", {})

    b_rows = ""
    for bf in baseline_files:
        name = bf.get("name", bf.get("filename", "—"))
        size = bf.get("size_bytes", bf.get("size", 0))
        h = bf.get("sha256", "—")
        b_rows += f"<tr><td><code>{name}</code></td><td>{size} bytes</td><td><code>{h}</code></td></tr>"

    if not b_rows:
        b_rows = '<tr><td colspan="3">Nenhum arquivo de baseline registrado.</td></tr>'

    inventory = data_json.get("visual_inventory", {})
    visual_assets = inventory.get("assets", []) if isinstance(inventory, dict) else []
    visual_status = inventory.get("visual_analysis_status", "não iniciado") if isinstance(inventory, dict) else "não iniciado"
    visual_cards = []
    for asset in visual_assets:
        rel = str(asset.get("file", ""))
        if not rel.startswith("visuais/") or ".." in rel.replace("\\", "/").split("/"):
            continue
        label = html.escape(str(asset.get("asset_id", "imagem")))
        source = html.escape(str(asset.get("source_document", "")))
        kind = html.escape(str(asset.get("kind", "")))
        digest = html.escape(str(asset.get("sha256", "")))
        path = html.escape(rel, quote=True)
        mime_type = str(asset.get("mime_type", ""))
        img_src = _resolve_image_data_uri_or_path(rel, rel_dir) if mime_type.startswith("image/") else f"./{path}"
        preview = f'<img src="{img_src}" alt="{label}" loading="lazy">' if mime_type.startswith("image/") else '<span class="visual-file-icon">Arquivo vetorial estruturado</span>'
        page = asset.get("page")
        dimensions = f"{asset.get('width')} × {asset.get('height')}" if asset.get("width") and asset.get("height") else "dimensão não identificada"
        ocr_text = str(asset.get("ocr_text", "")).strip()
        ocr_html = f"<p><strong>OCR:</strong> {html.escape(ocr_text[:1200])}</p>" if ocr_text else f"<p><strong>OCR:</strong> {html.escape(str(asset.get('ocr_status', 'não executado')))}</p>"
        location = f"Página {page}" if page else "Imagem sem número de página"
        visual_cards.append(f"""
          <article class="visual-asset-card">
            <a href="./{path}" target="_blank" rel="noopener">{preview}</a>
            <div><strong>{label}</strong> · {html.escape(location)} · {html.escape(dimensions)}</div>
            <div>{source} · {kind}</div>
            {ocr_html}
            <small>SHA-256: <code>{digest}</code></small>
          </article>
        """)
    if visual_cards:
        visual_inventory_html = f"""
        <h3 style="margin-top:35px;">Inventário de Imagens e Diagramas</h3>
        <p><strong>Estado da interpretação visual:</strong> {html.escape(str(visual_status))} · {len(visual_assets)} ativo(s) extraído(s) · {inventory.get('rendered_pdf_pages', 0)} página(s) de PDF renderizada(s).</p>
        <div class="visual-assets-grid">{''.join(visual_cards)}</div>
        """
    else:
        visual_inventory_html = f"<h3 style=\"margin-top:35px;\">Inventário de Imagens e Diagramas</h3><p>Nenhum ativo visual extraído. Estado: {html.escape(str(visual_status))}.</p>"

    semantic = data_json.get("semantic_analysis", {})
    semantic_status = html.escape(str(semantic.get("status", "não iniciada")))
    semantic_skills = ", ".join(html.escape(str(skill)) for skill in semantic.get("required_skills", [])) or "nenhuma skill textual aplicável"
    semantic_html = (
        f"<li><strong>Revisão semântica:</strong> {semantic_status} · "
        f"{int(semantic.get('reviewed_scope_count', len(semantic.get('reviewed_scopes', [])) or 0))}/"
        f"{int(semantic.get('expected_scope_count', len(semantic.get('required_scopes', [])) or 0))} escopos; "
        f"skills: {semantic_skills}; achados semânticos: {int(semantic.get('findings_recorded', 0))}</li>"
    )

    return f"""
    <div class="rastreabilidade-container">
        <h3>Inventário de Baseline & Hashes SHA-256 (Imutáveis)</h3>
        <div class="table-responsive">
            <table class="rpt-table">
                <thead>
                    <tr>
                        <th>Nome do Arquivo</th>
                        <th>Tamanho</th>
                        <th>Hash SHA-256</th>
                    </tr>
                </thead>
                <tbody>
                    {b_rows}
                </tbody>
            </table>
        </div>

        {visual_inventory_html}

        <h3 style="margin-top:35px;">Log Auditável de Execução da RTI</h3>
        <ul class="audit-log-list" style="line-height:1.8;">
            <li><strong>Timestamp de Execução:</strong> <code>{timestamp}</code></li>
            <li><strong>Skills Ativadas:</strong> {", ".join([f"<code>{s}</code>" for s in skills_ativas])}</li>
            {semantic_html}
            <li><strong>Total de Arquivos Analisados:</strong> {len(baseline_files)}</li>
            <li><strong>Total de Achados Auditados:</strong> {kpis.get("total_achados", 0)}</li>
            <li><strong>Índice IQD Resultante:</strong> <strong>{kpis.get("iqd", "100%")}</strong></li>
            <li><strong>Parecer Final Emitido:</strong> <strong>{data_json.get("parecer", "APTO COM RESSALVAS")}</strong></li>
        </ul>
    </div>
    """


def compile_timestamp_html(timestamp: str, root_dir: str = None) -> str:
    """Compila a Central Executiva HTML a partir de dados_analise.json ou Markdown."""
    if root_dir is None:
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    rel_dir = os.path.join(root_dir, 'analise', timestamp, 'relatorios')
    output_path = os.path.join(rel_dir, 'index.html')
    json_path = os.path.join(rel_dir, 'dados_analise.json')

    if not os.path.exists(rel_dir):
        return f"Diretório não encontrado: {rel_dir}"

    lote_name = timestamp.split('_', 2)[2].replace('_', ' ') if len(timestamp.split('_', 2)) > 2 else timestamp
    data_fmt = f"{timestamp[6:8]}/{timestamp[4:6]}/{timestamp[:4]}" if len(timestamp) >= 8 else timestamp

    # 1. Tenta carregar dados_analise.json
    data_json = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data_json = json.load(f)
        except Exception as e:
            print(f"Aviso ao ler dados_analise.json: {e}", file=sys.stderr)

    # Fallback ou Dados do JSON
    if data_json:
        findings = data_json.get("findings", [])
        adjudication_counts = _adjudication_counts(findings)
        pending_count = adjudication_counts["pendente"] + adjudication_counts["evidencia_insuficiente"]
        confirmed_findings = _confirmed_findings(findings)
        kpis = dict(data_json.get("kpis", {}))
        kpis["total_achados"] = len(findings)
        kpis["achados_confirmados"] = len(confirmed_findings)
        kpis["achados_pendentes_adjudicacao"] = pending_count
        kpis["achados_excluidos"] = sum(adjudication_counts[status] for status in ("falso_positivo", "fora_de_escopo", "duplicado"))
        kpis["criticos"] = sum(1 for item in confirmed_findings if str(item.get("criticidade", item.get("crit", ""))).casefold() == "crítica")
        kpis["altos"] = sum(1 for item in confirmed_findings if str(item.get("criticidade", item.get("crit", ""))).casefold() == "alta")
        kpis["medios"] = sum(1 for item in confirmed_findings if str(item.get("criticidade", item.get("crit", ""))).casefold() in ("média", "media"))
        kpis["baixos"] = sum(1 for item in confirmed_findings if str(item.get("criticidade", item.get("crit", ""))).casefold() in ("baixa", "informativa"))
        kpis["lacunas"] = sum(1 for item in confirmed_findings if "lacuna" in str(item.get("tipo", "")).casefold())
        kpis["riscos"] = sum(1 for item in confirmed_findings if "risco" in str(item.get("tipo", "")).casefold())
        data_json["kpis"] = kpis
        data_json["adjudication_summary"] = adjudication_counts
        data_json["lacunas"] = [item for item in confirmed_findings if "lacuna" in str(item.get("tipo", "")).casefold()]
        data_json["riscos"] = [item for item in confirmed_findings if "risco" in str(item.get("tipo", "")).casefold()]
        raw_confirmed = [{
            "crit": item.get("criticidade", item.get("crit", "Média")),
            "prio": item.get("prioridade", item.get("prio", "P2")),
        } for item in confirmed_findings]
        import audit_engine
        if pending_count:
            parecer = "PENDENTE DE ADJUDICAÇÃO"
            kpis["iqd"] = "—"
        else:
            parecer = audit_engine.calculate_parecer(raw_confirmed, confirmed_findings)[0]
            _, kpis["iqd"], _ = audit_engine.calculate_iqd(raw_confirmed, kpis.get("iqd_denominador"))
        data_json["parecer"] = parecer
        total_achados = str(kpis["total_achados"])
        achados_confirmados = str(kpis["achados_confirmados"])
        pendentes_adjudicacao = str(kpis["achados_pendentes_adjudicacao"])
        criticos = str(kpis["criticos"])
        lacunas_n = str(kpis["lacunas"])
        estruturais_n = str(kpis.get("estruturais", 0))
        iqd = str(kpis.get("iqd", "100%"))
        resumo_html = _build_resumo_html(data_json)
        acoes_html = _build_acoes_html(data_json)
        lacunas_html = _build_lacunas_html(data_json)
        checklists_html = _build_checklists_html(data_json)
        rastrea_html = _build_rastrea_html(data_json, rel_dir=rel_dir)
    else:
        resumo_md = _read_md(rel_dir, '00_RESUMO_EXECUTIVO.md')
        pontos_md = _read_md(rel_dir, '01_PONTOS_DE_ATENCAO.md')
        acoes_md = _read_md(rel_dir, '02_ACOES_E_MINUTAS.md')
        rastrea_md = _read_md(rel_dir, '03_RASTREABILIDADE_E_LOG.md')
        lacunas_md = _read_md(rel_dir, '04_LACUNAS_E_RISCOS.md')
        checklists_md = _read_md(rel_dir, '05_CONFORMIDADE_CHECKLISTS.md')

        parecer = _extract_value(resumo_md, r'Parecer[^:]*:\s*\*?\*?([A-ZÁÉÍÓÚÃÕÇ /]+)\*?\*?', "APTO COM RESSALVAS")
        total_achados = _extract_value(resumo_md, r'Total de Achados\s*\|\s*\*\*(\d+)\*\*', "0")
        achados_confirmados = total_achados
        pendentes_adjudicacao = "0"
        criticos = _extract_value(resumo_md, r'Críticos[^|]*\|\s*\*\*(\d+)\*\*', "0")
        lacunas_n = _extract_value(resumo_md, r'Lacunas[^|]*\|\s*\*\*(\d+)\*\*', "0")
        iqd = _extract_value(resumo_md, r'IQD[^|]*\|\s*\*\*([0-9,.]+%|—)\*\*', "—")
        findings = _parse_findings(pontos_md)
        estruturais_n = str(sum(1 for f in findings if "sequência" in f.get("tipo", "").lower() or "estrutur" in f.get("tipo", "").lower() or "redac" in f.get("tipo", "").lower()))

        resumo_html = _md_to_html_simple(resumo_md, linkify_ids=True)
        acoes_html = _md_to_html_simple(acoes_md, linkify_ids=True)
        rastrea_html = _md_to_html_simple(rastrea_md, linkify_ids=False)
        lacunas_html = _md_to_html_simple(lacunas_md, linkify_ids=True)
        checklists_html = _md_to_html_simple(checklists_md, linkify_ids=False)

    # Classificação do Parecer
    if "NÃO APTO" in parecer.upper():
        parecer_class = "parecer-nao-apto"
        parecer_icon = "fa-triangle-exclamation"
    elif "RESSALVA" in parecer.upper():
        parecer_class = "parecer-ressalva"
        parecer_icon = "fa-circle-exclamation"
    elif "PENDENTE" in parecer.upper():
        parecer_class = "parecer-pendente"
        parecer_icon = "fa-hourglass-half"
    else:
        parecer_class = "parecer-apto"
        parecer_icon = "fa-circle-check"

    unique_docs = sorted(list(set(f["doc_origem"] for f in findings if f.get("doc_origem"))))
    doc_options_html = "".join([f'<option value="{d}">{d}</option>' for d in unique_docs])

    unique_cats = sorted(list(set(f["categoria"] for f in findings if f.get("categoria"))))
    cat_options_html = "".join([f'<option value="{c}">{c}</option>' for c in unique_cats])

    # Seção 2: Geração da Tabela Consolidada SSOT (Com Links Âncora por ID)
    ssot_table_rows = ""
    for f in findings:
        crit = f.get("criticidade", "Média")
        c_class = "crit-critica" if "crítica" in crit.lower() else \
                  "crit-alta" if "alta" in crit.lower() else \
                  "crit-media" if "média" in crit.lower() else \
                  "crit-baixa" if "baixa" in crit.lower() else "crit-info"

        prio = f.get("prioridade", "P2")
        tipo = f.get("tipo", "Técnico")
        fid = f.get("id", "ACH-000")
        adjudication_status = _adjudication_status(f)
        adjudication_label = ADJUDICATION_LABELS[adjudication_status]
        adjudication_class = "confirmado" if adjudication_status == "confirmado" else (
            "excluido" if adjudication_status in {"falso_positivo", "fora_de_escopo", "duplicado"} else "pendente")

        ssot_table_rows += f"""
        <tr>
          <td>
            <a href="#card-{fid}" class="ssot-link" title="Clique para ir ao detalhamento da Ficha 360°">
              <i class="fa-solid fa-circle-chevron-right"></i> <strong>{fid}</strong>
            </a>
          </td>
          <td><strong>{f.get('title','')}</strong></td>
          <td><code>{f.get('doc_origem','—')}</code></td>
          <td>{f.get('loc','—')}</td>
          <td>{f.get('categoria','—')}</td>
          <td><span class="badge-tipo">{tipo}</span></td>
          <td><span class="badge-crit {c_class}">{crit}</span></td>
          <td><span class="badge-prio">{prio}</span></td>
          <td><span class="badge-adjudication {adjudication_class}">{adjudication_label}</span></td>
          <td>{f.get('proprietario','—')}</td>
        </tr>"""

    ssot_table_html = f"""
    <div class="ssot-table-wrap">
      <div class="ssot-intro-note">
        <i class="fa-solid fa-circle-info"></i> <strong>Visão Panorâmica SSOT:</strong> Esta tabela consolida todos os {len(findings)} achados identificados nesta auditoria. Clique em qualquer ID para ir diretamente ao detalhamento da Ficha 360°.
      </div>
      <div class="table-responsive">
        <table class="rpt-table master-ssot-table">
          <thead>
            <tr>
              <th>ID Achado</th>
              <th>Título do Fato Observado</th>
              <th>Documento de Origem</th>
              <th>Localização</th>
              <th>Categoria</th>
              <th>Tipo</th>
              <th>Criticidade</th>
              <th>Prioridade</th>
              <th>Adjudicação</th>
              <th>Proprietário Sugerido</th>
            </tr>
          </thead>
          <tbody>
          {ssot_table_rows if ssot_table_rows else '<tr><td colspan="10">Nenhum achado registrado.</td></tr>'}
          </tbody>
        </table>
      </div>
    </div>
    """

    # Seção 4: Tabela Estruturada de Erratas (De → Para) com IDs Clicáveis
    erratas_findings = [f for f in findings if f.get("is_direct") or "→" in f.get("tipo","") or "grafia" in f.get("tipo","").lower() or "sequência" in f.get("tipo","").lower() or f.get("de")]
    erratas_rows_html = ""
    for f in erratas_findings:
        fid = f.get("id", "ACH-000")
        de_txt = f.get("de", "—")
        para_txt = f.get("para", "—")
        erratas_rows_html += f"""
        <tr>
          <td>
            <a href="#card-{fid}" class="ssot-link" title="Clique para ver a Ficha 360° de origem">
              <i class="fa-solid fa-arrow-right-to-bracket"></i> <strong>{fid}</strong>
            </a>
          </td>
          <td>{f.get('loc','—')}</td>
          <td><span class="de-content" style="display:inline-block; margin:0;">"{de_txt}"</span></td>
          <td><span class="para-content" id="err-para-{fid}" style="display:inline-block; margin:0;">"{para_txt}"</span></td>
          <td>{f.get('proprietario','—')}</td>
          <td>
            <button class="btn-copy" onclick="copySnippet('err-para-{fid}', this)"><i class="fa-solid fa-copy"></i> Copiar</button>
          </td>
        </tr>"""

    erratas_table_html = f"""
    <div class="table-responsive">
      <table class="rpt-table">
        <thead>
          <tr>
            <th>ID Achado</th>
            <th>Seção / Localização</th>
            <th>Texto Atual (Baseline)</th>
            <th>Redação Sugerida (Minuta Não Oficial)</th>
            <th>Proprietário Sugerido</th>
            <th>Ação</th>
          </tr>
        </thead>
        <tbody>
          {erratas_rows_html if erratas_rows_html else '<tr><td colspan="6">Nenhuma errata direta registrada.</td></tr>'}
        </tbody>
      </table>
    </div>
    """

    # Geração dos Cards Ficha 360° em HTML para a Seção 3 (com ID âncora id="card-{fid}")
    findings_cards_html = ""
    for f in findings:
        fid = f.get("id", "ACH-000")
        crit = f.get("criticidade", "Média")
        c_class = "crit-critica" if "crítica" in crit.lower() else \
                  "crit-alta" if "alta" in crit.lower() else \
                  "crit-media" if "média" in crit.lower() else \
                  "crit-baixa" if "baixa" in crit.lower() else "crit-info"

        prio = f.get("prioridade", "P2")
        tipo = f.get("tipo", "Técnico")
        cat = f.get("categoria", "Geral")
        adjudication_status = _adjudication_status(f)
        adjudication_label = ADJUDICATION_LABELS[adjudication_status]
        adjudication_class = "confirmado" if adjudication_status == "confirmado" else (
            "excluido" if adjudication_status in {"falso_positivo", "fora_de_escopo", "duplicado"} else "pendente")
        adjudication = f.get("adjudication") if isinstance(f.get("adjudication"), dict) else {}
        adjudication_rationale = html.escape(str(adjudication.get("rationale", "")))
        adjudication_detail_html = (
            f'<div class="ssot-intro-note"><strong>Adjudicação:</strong> {html.escape(adjudication_label)}'
            + (f" — {adjudication_rationale}" if adjudication_rationale else "") + "</div>"
        )
        is_direct = f.get("is_direct", False) or "→" in tipo or "grafia" in tipo.lower() or "sequência" in tipo.lower()
        de_txt = f.get("de", "")
        para_txt = f.get("para", "")

        solucao_box = ""
        if is_direct and (de_txt or para_txt):
            solucao_box = f"""
            <div class="de-para-box">
              <div class="de-col">
                <span class="de-label"><i class="fa-solid fa-file-lines"></i> Texto Atual (Baseline):</span>
                <div class="de-content">"{de_txt}"</div>
              </div>
              <div class="para-col">
                <span class="para-label"><i class="fa-solid fa-file-pen"></i> Redação Sugerida (Minuta Não Oficial):</span>
                <div class="para-content" id="para-{fid}">"{para_txt}"</div>
                <button class="btn-copy" onclick="copySnippet('para-{fid}', this)"><i class="fa-solid fa-copy"></i> Copiar Sugestão</button>
              </div>
            </div>"""
        elif f.get("solucao"):
            solucao_box = f"""
            <div class="solucao-box">
              <span class="solucao-label"><i class="fa-solid fa-list-check"></i> Plano de Solução Recomendado:</span>
              <div class="solucao-content">{f['solucao']}</div>
            </div>"""

        visual_evidence_html = ""
        visual_file = str(f.get("visual_file", ""))
        if visual_file.startswith("visuais/") and ".." not in visual_file.replace("\\", "/").split("/"):
            safe_visual_file = html.escape(visual_file, quote=True)
            visual_asset_id = html.escape(str(f.get("visual_asset_id", "")))
            visual_hash = html.escape(str(f.get("visual_sha256", "")))
            visual_page = f" · página {f.get('visual_page')}" if f.get("visual_page") else ""
            img_src = _resolve_image_data_uri_or_path(visual_file, rel_dir)
            if os.path.splitext(visual_file)[1].lower() in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"):
                visual_preview = f'<a href="./{safe_visual_file}" target="_blank" rel="noopener"><img src="{img_src}" alt="Evidência visual {visual_asset_id}" loading="lazy"></a>'
            else:
                visual_preview = f'<a href="./{safe_visual_file}" target="_blank" rel="noopener">Abrir artefato {visual_asset_id}</a>'

            confronto_html = ""
            texto_afirmado = f.get("texto_afirmado", "")
            diagrama_demonstrado = f.get("diagrama_demonstrado", "")
            if texto_afirmado or diagrama_demonstrado:
                confronto_html = f"""
                <div class="confronto-diagrama-box" style="margin-top:10px;border-radius:6px;overflow:hidden;border:1px solid #cbd5e1;">
                  <table style="width:100%;font-size:.82rem;margin:0;border-collapse:collapse;">
                    <tr style="background:#f8fafc;border-bottom:1px solid #cbd5e1;">
                      <th style="padding:6px 10px;text-align:left;width:50%;color:#475569;"><i class="fa-solid fa-file-lines"></i> Afirmação no Texto (Documento)</th>
                      <th style="padding:6px 10px;text-align:left;width:50%;color:#475569;"><i class="fa-solid fa-diagram-project"></i> Ilustração no Diagrama / Topologia</th>
                    </tr>
                    <tr>
                      <td style="padding:8px 10px;vertical-align:top;background:#fff;border-right:1px solid #cbd5e1;">{html.escape(str(texto_afirmado))}</td>
                      <td style="padding:8px 10px;vertical-align:top;background:#fff;">{html.escape(str(diagrama_demonstrado))}</td>
                    </tr>
                  </table>
                </div>"""

            visual_evidence_html = f"""
            <div class="visual-evidence">
              <strong>Evidência visual:</strong> {visual_asset_id}{visual_page}<br>
              {visual_preview}
              <small>SHA-256: <code>{visual_hash}</code></small>
              {confronto_html}
            </div>"""

        semantic_skill = str(f.get("semantic_skill", ""))
        semantic_badge_html = ""
        semantic_evidence_html = ""
        if semantic_skill:
            semantic_badge_html = (
                '<span class="badge-semantic" style="display:inline-block;padding:4px 8px;border-radius:999px;'
                'background:#eef2ff;color:#4338ca;font-size:.75rem;font-weight:700;">Revisão semântica · '
                f"{html.escape(semantic_skill)}</span>"
            )
            semantic_sources = []
            for source in f.get("evidence_sources", []):
                if not isinstance(source, dict):
                    continue
                source_path = html.escape(str(source.get("document_path", "")))
                source_location = html.escape(str(source.get("location", "Localização a confirmar")))
                source_quote = html.escape(str(source.get("quote", "")))
                source_hash = html.escape(str(source.get("sha256", "")))
                semantic_sources.append(
                    f"<li><strong>{source_path}</strong> · {source_location}<blockquote>“{source_quote}”</blockquote>"
                    + (f"<small>SHA-256: <code>{source_hash}</code></small>" if source_hash else "") + "</li>"
                )
            reference_links = []
            for reference in f.get("referencias", []):
                if not isinstance(reference, dict):
                    continue
                ref_title = html.escape(str(reference.get("titulo", "Referência técnica")))
                ref_url_raw = str(reference.get("url", ""))
                ref_url = html.escape(ref_url_raw, quote=True)
                ref_note = html.escape(str(reference.get("nota", "")))
                if ref_url_raw.startswith(("https://", "http://")):
                    reference_links.append(f'<li><a href="{ref_url}" target="_blank" rel="noopener">{ref_title}</a> {ref_note}</li>')
                else:
                    reference_links.append(f"<li>{ref_title} {ref_note}</li>")
            semantic_evidence_html = (
                '<div class="semantic-evidence" style="margin:14px 0;padding:12px 14px;border-left:3px solid #6366f1;'
                'background:#f8faff;border-radius:6px;">'
                '<strong>Rastreabilidade semântica:</strong> '
                f"{html.escape(semantic_skill)} · {html.escape(str(f.get('evidencia', 'E1')))}"
                + (f"<ul>{''.join(semantic_sources)}</ul>" if semantic_sources else "")
                + (f"<strong>Referências corroborativas</strong><ul>{''.join(reference_links)}</ul>" if reference_links else "")
                + "</div>"
            )

        findings_cards_html += f"""
        <div class="finding-card {c_class}"
             id="card-{fid}"
             data-id="{fid}"
             data-doc="{f.get('doc_origem', '')}"
             data-crit="{crit}"
             data-prio="{prio}"
             data-tipo="{tipo}"
             data-cat="{cat}"
             data-adjudication="{adjudication_status}"
             data-search="{fid} {f['title']} {f.get('doc_origem','')} {f.get('loc','')} {f.get('fato','')} {cat}">
          <div class="card-top">
            <div class="top-tags">
              <span class="badge-id">{fid}</span>
              <span class="badge-crit {c_class}">{crit}</span>
              <span class="badge-prio">{prio}</span>
              <span class="badge-tipo">{tipo}</span>
              <span class="badge-adjudication {adjudication_class}">{adjudication_label}</span>
              {semantic_badge_html}
            </div>
            <a href="#matriz-master" class="btn-back-ssot" title="Voltar para a Matriz SSOT"><i class="fa-solid fa-table-list"></i> Ver na Matriz SSOT</a>
          </div>

          <h3 class="finding-title">{f['title']}</h3>

          <div class="finding-meta-row">
            <span><i class="fa-solid fa-file-lines"></i> <strong>Doc:</strong> {f.get('doc_origem','—')}</span>
            <span><i class="fa-solid fa-location-dot"></i> <strong>Local:</strong> {f.get('loc','—')}</span>
            <span><i class="fa-solid fa-tag"></i> <strong>Categoria:</strong> {cat}</span>
          </div>

          {adjudication_detail_html}

          <div class="finding-body-grid">
            <div class="fato-box">
              <span class="box-title"><i class="fa-solid fa-eye"></i> Fato Observado (Baseline)</span>
              <p>{f.get('fato','')}</p>
            </div>
            <div class="impacto-box">
              <span class="box-title"><i class="fa-solid fa-shield-cat"></i> Impacto Potencial</span>
              <p>{f.get('impacto','')}</p>
            </div>
          </div>

          {solucao_box}

          {visual_evidence_html}
          {semantic_evidence_html}

          <div class="card-bottom">
            <span><i class="fa-solid fa-user-gear"></i> <strong>Proprietário Sugerido:</strong> {f.get('proprietario','—')}</span>
          </div>
        </div>"""

    # Template HTML Final Exaustivo (Sidebar Colapsado por Padrão & 8 Seções)
    html_template = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Relatório RTI — {lote_name}</title>
    <!-- Google Fonts & Font Awesome -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">

    <style>
        :root {{
            --primary: #005ca9;
            --primary-dark: #004077;
            --primary-light: #e6f0fa;
            --secondary: #0f172a;
            --accent: #f59e0b;
            --danger: #ef4444;
            --danger-light: #fef2f2;
            --warning: #f59e0b;
            --warning-light: #fffbeb;
            --success: #10b981;
            --success-light: #ecfdf5;
            --bg-body: #f8fafc;
            --bg-card: #ffffff;
            --text-main: #1e293b;
            --text-muted: #64748b;
            --border: #e2e8f0;
            --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
            --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.07), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        html {{ scroll-behavior: smooth; }}

        body {{
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-body);
            color: var(--text-main);
            line-height: 1.65;
            font-size: 14px;
        }}

        h1, h2, h3, h4, h5 {{
            font-family: 'Outfit', sans-serif;
            color: var(--secondary);
            font-weight: 700;
        }}

        /* Navbar Fixa Superior */
        .top-navbar {{
            position: sticky;
            top: 0;
            z-index: 1000;
            background: rgba(15, 23, 42, 0.96);
            backdrop-filter: blur(8px);
            color: #ffffff;
            padding: 12px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.15);
        }}

        .brand-title {{
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 1.1rem;
            font-weight: 700;
        }}
        .brand-title i {{ color: #38bdf8; font-size: 1.3rem; }}

        .actions-group {{ display: flex; align-items: center; gap: 10px; }}

        .btn-action {{
            background: var(--primary);
            color: #ffffff;
            border: none;
            padding: 8px 14px;
            border-radius: 6px;
            font-weight: 600;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s ease;
            font-size: 0.85rem;
            text-decoration: none;
        }}
        .btn-action:hover {{ background: #0284c7; transform: translateY(-1px); }}
        .btn-toggle-menu {{ background: #334155; }}
        .btn-toggle-menu:hover {{ background: #475569; }}
        .btn-print {{ background: #059669; }}
        .btn-print:hover {{ background: #10b981; }}
        .btn-master-home {{ background: #0284c7; }}

        /* Main Wrapper & Layout */
        .main-wrapper {{
            display: flex;
            max-width: 1440px;
            margin: 0 auto;
            padding: 24px;
            gap: 24px;
            transition: all 0.3s ease;
        }}

        /* Sidebar Colapsável (COLAPSADO POR PADRÃO) */
        .sidebar-nav {{
            width: 280px;
            flex-shrink: 0;
            position: sticky;
            top: 75px;
            height: calc(100vh - 100px);
            overflow-y: auto;
            background: var(--bg-card);
            border-radius: 12px;
            padding: 16px;
            border: 1px solid var(--border);
            box-shadow: var(--shadow);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }}
        .sidebar-nav.collapsed {{
            width: 0;
            padding: 0;
            margin-right: -24px;
            border: none;
            overflow: hidden;
            opacity: 0;
            pointer-events: none;
        }}

        .nav-title {{
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            margin-bottom: 12px;
            font-weight: 700;
        }}
        .nav-list {{ list-style: none; display: flex; flex-direction: column; gap: 4px; }}
        .nav-list a {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 12px;
            color: var(--text-main);
            text-decoration: none;
            border-radius: 6px;
            font-weight: 500;
            font-size: 0.85rem;
            transition: all 0.2s ease;
        }}
        .nav-list a:hover, .nav-list a.active {{
            background: var(--primary-light);
            color: var(--primary);
        }}

        /* Área de Conteúdo Main */
        .content-area {{
            flex-grow: 1;
            display: flex;
            flex-direction: column;
            gap: 24px;
            width: 100%;
        }}

        /* Hero Header Card */
        .hero-card {{
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: #ffffff;
            border-radius: 16px;
            padding: 28px;
            box-shadow: var(--shadow-lg);
            position: relative;
            overflow: hidden;
        }}
        .hero-tag {{
            display: inline-block;
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 8px;
            border: 1px solid rgba(56, 189, 248, 0.3);
        }}
        .hero-title {{ color: #ffffff; font-size: 1.7rem; margin-bottom: 6px; }}
        .hero-meta {{ color: #94a3b8; font-size: 0.9rem; margin-bottom: 20px; }}

        /* Status Banner Parecer */
        .parecer-badge {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 16px;
            border-radius: 8px;
            font-weight: 700;
            font-size: 0.9rem;
            text-transform: uppercase;
        }}
        .parecer-apto {{ background: #10b981; color: #ffffff; }}
        .parecer-ressalva {{ background: #f59e0b; color: #ffffff; }}
        .parecer-nao-apto {{ background: #ef4444; color: #ffffff; }}
        .parecer-pendente {{ background: #d97706; color: #ffffff; }}

        /* Grid de KPIs */
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 12px;
            margin-top: 20px;
        }}
        .metric-card {{
            background: rgba(255, 255, 255, 0.06);
            backdrop-filter: blur(4px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 14px;
        }}
        .metric-label {{ font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; font-weight: 600; }}
        .metric-val {{ font-size: 1.4rem; font-weight: 800; color: #ffffff; font-family: 'Outfit', sans-serif; }}
        .metric-val.red {{ color: #f87171; }}
        .metric-val.amber {{ color: #fbbf24; }}
        .metric-val.green {{ color: #34d399; }}

        /* Cards de Seção Geral */
        .section-card {{
            background: var(--bg-card);
            border-radius: 16px;
            padding: 24px;
            border: 1px solid var(--border);
            box-shadow: var(--shadow);
            scroll-margin-top: 85px;
        }}
        .section-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 18px;
            padding-bottom: 10px;
            border-bottom: 2px solid var(--primary-light);
        }}
        .section-icon {{
            width: 36px;
            height: 36px;
            background: var(--primary-light);
            color: var(--primary);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.1rem;
        }}
        .section-title {{ font-size: 1.25rem; color: var(--secondary); margin: 0; }}

        /* Link Âncora SSOT */
        .ssot-intro-note {{
            background: #e0f2fe;
            color: #0369a1;
            border: 1px solid #7dd3fc;
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 0.85rem;
            margin-bottom: 14px;
        }}
        .ssot-link {{
            color: var(--primary);
            font-weight: 700;
            text-decoration: none;
            background: var(--primary-light);
            padding: 3px 8px;
            border-radius: 4px;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            transition: all 0.2s ease;
        }}
        .ssot-link:hover {{
            background: var(--primary);
            color: #ffffff;
            transform: translateX(2px);
        }}
        .btn-back-ssot {{
            font-size: 0.75rem;
            color: var(--text-muted);
            text-decoration: none;
            background: #f1f5f9;
            padding: 2px 8px;
            border-radius: 4px;
            transition: all 0.2s ease;
        }}
        .btn-back-ssot:hover {{
            background: var(--border);
            color: var(--secondary);
        }}

        /* Toolbar de Filtros */
        .filter-toolbar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            background: #f1f5f9;
            padding: 12px 16px;
            border-radius: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}
        .filter-group {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
        .btn-filter {{
            background: #ffffff;
            color: var(--text-main);
            border: 1px solid var(--border);
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        .btn-filter:hover, .btn-filter.active {{
            background: var(--primary);
            color: #ffffff;
            border-color: var(--primary);
        }}
        .search-box {{ position: relative; min-width: 240px; }}
        .search-box input {{
            width: 100%;
            padding: 6px 12px 6px 32px;
            border-radius: 20px;
            border: 1px solid var(--border);
            font-size: 0.82rem;
            outline: none;
        }}
        .search-box i {{ position: absolute; left: 10px; top: 50%; transform: translateY(-50%); color: var(--text-muted); }}

        /* Card da Ficha 360° */
        .finding-card {{
            background: #ffffff;
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
            box-shadow: var(--shadow);
            border-left: 5px solid var(--primary);
            transition: all 0.2s ease;
            scroll-margin-top: 90px;
        }}
        .finding-card.crit-critica {{ border-left-color: var(--danger); }}
        .finding-card.crit-alta {{ border-left-color: var(--warning); }}
        .finding-card.crit-media {{ border-left-color: #3b82f6; }}
        .finding-card.crit-baixa {{ border-left-color: var(--success); }}

        .card-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }}
        .top-tags {{ display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }}

        .badge-id {{ background: var(--secondary); color: #fff; padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 0.75rem; }}
        .badge-crit {{ padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 0.75rem; color: #fff; }}
        .badge-crit.crit-critica {{ background: var(--danger); }}
        .badge-crit.crit-alta {{ background: var(--warning); }}
        .badge-crit.crit-media {{ background: #3b82f6; }}
        .badge-crit.crit-baixa {{ background: var(--success); }}

        .badge-prio {{ background: #e2e8f0; color: var(--secondary); padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 0.75rem; }}
        .badge-tipo {{ background: #e0f2fe; color: #0369a1; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-size: 0.75rem; }}
        .badge-adjudication {{ display:inline-block; padding:4px 8px; border-radius:999px; background:#fef3c7; color:#92400e; font-size:.75rem; font-weight:700; }}
        .badge-adjudication.confirmado {{ background:#dcfce7; color:#166534; }}
        .badge-adjudication.excluido {{ background:#e2e8f0; color:#475569; }}

        .finding-title {{ font-size: 1.1rem; color: var(--secondary); margin-bottom: 8px; }}
        .finding-meta-row {{ font-size: 0.8rem; color: var(--text-muted); display: flex; gap: 14px; margin-bottom: 14px; flex-wrap: wrap; }}

        .finding-body-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 14px; }}
        @media (max-width: 768px) {{ .finding-body-grid {{ grid-template-columns: 1fr; }} }}

        .fato-box, .impacto-box {{ background: #f8fafc; border: 1px solid var(--border); border-radius: 8px; padding: 12px; font-size: 0.85rem; }}
        .box-title {{ font-weight: 700; font-size: 0.78rem; text-transform: uppercase; color: var(--text-muted); display: block; margin-bottom: 4px; }}

        /* De-Para & Solução */
        .de-para-box {{ background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; padding: 14px; margin-top: 10px; }}
        .de-col, .para-col {{ margin-bottom: 8px; font-size: 0.85rem; }}
        .de-label, .para-label {{ font-weight: 700; font-size: 0.78rem; display: block; margin-bottom: 2px; }}
        .de-label {{ color: #991b1b; }}
        .para-label {{ color: #166534; }}
        .de-content {{ color: #991b1b; font-style: italic; background: #fee2e2; padding: 6px 10px; border-radius: 4px; margin-bottom: 6px; }}
        .para-content {{ color: #166534; font-weight: 600; background: #dcfce7; padding: 8px 10px; border-radius: 4px; position: relative; }}

        .solucao-box {{ background: #faf5ff; border: 1px solid #e9d5ff; border-radius: 8px; padding: 12px; margin-top: 10px; font-size: 0.85rem; }}
        .solucao-label {{ color: #6b21a8; font-weight: 700; font-size: 0.78rem; display: block; margin-bottom: 4px; }}

        .btn-copy {{
            background: #0284c7;
            color: #ffffff;
            border: none;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            cursor: pointer;
            margin-top: 6px;
        }}
        .btn-copy:hover {{ background: #0369a1; }}
        .btn-copy.copied {{ background: #10b981; }}

        .card-bottom {{ font-size: 0.8rem; color: var(--text-muted); border-top: 1px solid var(--border); padding-top: 8px; margin-top: 12px; }}

        /* Tabelas Genéricas */
        .table-responsive {{ overflow-x: auto; margin-top: 10px; }}
        .rpt-table {{ width: 100%; border-collapse: collapse; font-size: 0.83rem; }}
        .rpt-table th, .rpt-table td {{ padding: 8px 12px; border: 1px solid var(--border); text-align: left; }}
        .rpt-table th {{ background: #f1f5f9; font-weight: 700; color: var(--secondary); }}
        .rpt-table tr:nth-child(even) {{ background: #f8fafc; }}

        .visual-assets-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:14px; margin:14px 0 24px; }}
        .visual-asset-card {{ border:1px solid var(--border); border-radius:10px; padding:12px; background:#fff; overflow:hidden; font-size:.78rem; }}
        .visual-asset-card img {{ width:100%; max-height:260px; object-fit:contain; background:#f1f5f9; border-radius:6px; }}
        .visual-asset-card p {{ margin:6px 0; overflow-wrap:anywhere; }}
        .visual-asset-card code {{ overflow-wrap:anywhere; }}
        .visual-file-icon {{ min-height:90px; display:grid; place-items:center; background:#f1f5f9; border-radius:6px; color:var(--text-muted); }}
        .visual-evidence {{ margin:12px 0; border:1px solid var(--border); border-radius:8px; padding:10px; background:#f8fafc; }}
        .visual-evidence img {{ max-width:100%; max-height:280px; object-fit:contain; display:block; margin:8px auto; }}

        /* Print Styles */
        @media print {{
            .top-navbar, .sidebar-nav, .filter-toolbar, .btn-copy {{ display: none !important; }}
            .main-wrapper {{ padding: 0; max-width: 100%; }}
            .section-card {{ box-shadow: none; border: 1px solid #ccc; page-break-inside: avoid; }}
        }}
    </style>
</head>
<body>

    <!-- Navbar Superior -->
    <header class="top-navbar">
        <div class="brand-title">
            <i class="fa-solid fa-shield-halved"></i>
            <span>FCA-ENG-001 · Central de Revisão Técnica Independente</span>
        </div>
        <div class="actions-group">
            <a href="../../index.html" class="btn-action btn-master-home"><i class="fa-solid fa-house"></i> Central Master</a>
            <button class="btn-action btn-toggle-menu" onclick="toggleSidebar()"><i class="fa-solid fa-bars"></i> Menu</button>
            <button class="btn-action btn-print" onclick="window.print()"><i class="fa-solid fa-print"></i> Imprimir / PDF</button>
        </div>
    </header>

    <div class="main-wrapper">
        <!-- Sidebar Navigation (COLAPSADO POR PADRÃO) -->
        <aside class="sidebar-nav collapsed" id="sidebar">
            <div class="nav-title">Navegação da Análise</div>
            <ul class="nav-list">
                <li><a href="#resumo" class="active"><i class="fa-solid fa-chart-pie"></i> 1. Resumo Executivo</a></li>
                <li><a href="#matriz-master"><i class="fa-solid fa-table-list"></i> 2. Matriz Master SSOT ({len(findings)})</a></li>
                <li><a href="#fichas"><i class="fa-solid fa-list-check"></i> 3. Fichas 360° Detalhadas</a></li>
                <li><a href="#erratas"><i class="fa-solid fa-file-pen"></i> 4. Caderno De-Para (Erratas)</a></li>
                <li><a href="#acoes-perguntas"><i class="fa-solid fa-clipboard-question"></i> 5. Planos de Ação & Perguntas</a></li>
                <li><a href="#lacunas-riscos"><i class="fa-solid fa-triangle-exclamation"></i> 6. Lacunas & Riscos</a></li>
                <li><a href="#checklists"><i class="fa-solid fa-square-check"></i> 7. Conformidade Checklists</a></li>
                <li><a href="#rastreabilidade"><i class="fa-solid fa-fingerprint"></i> 8. Hashes & Rastreabilidade</a></li>
            </ul>
        </aside>

        <!-- Área de Conteúdo Principal -->
        <main class="content-area">

            <!-- Hero Header Card -->
            <section class="hero-card">
                <span class="hero-tag"><i class="fa-solid fa-folder-open"></i> Lote Analisado: {lote_name}</span>
                <h1 class="hero-title">Relatório Consolidado de Revisão Técnica Independente</h1>
                <div class="hero-meta">
                    <span><i class="fa-solid fa-clock"></i> Timestamp: <code>{timestamp}</code></span> &nbsp;|&nbsp;
                    <span><i class="fa-solid fa-calendar"></i> Data de Emissão: {data_fmt}</span>
                </div>

                <div class="parecer-badge {parecer_class}">
                    <i class="fa-solid {parecer_icon}"></i> Parecer Técnico: {parecer}
                </div>

                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-label">Total Achados</div>
                        <div class="metric-val">{total_achados}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Achados Críticos / P0</div>
                        <div class="metric-val red">{criticos}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Confirmados / Pendentes</div>
                        <div class="metric-val">{achados_confirmados} / {pendentes_adjudicacao}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Lacunas Mapeadas</div>
                        <div class="metric-val amber">{lacunas_n}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Estruturais / Sequência</div>
                        <div class="metric-val amber">{estruturais_n}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Índice IQD</div>
                        <div class="metric-val green">{iqd}</div>
                    </div>
                </div>
            </section>

            <!-- Seção 1: Resumo Executivo -->
            <section class="section-card" id="resumo">
                <div class="section-header">
                    <div class="section-icon"><i class="fa-solid fa-chart-pie"></i></div>
                    <h2 class="section-title">1. Resumo Executivo & Matriz de Skills</h2>
                </div>
                <div class="md-rendered-content">
                    {resumo_html}
                </div>
            </section>

            <!-- Seção 2: Matriz Master SSOT (Tabela Consolidada ANTES do Detalhamento) -->
            <section class="section-card" id="matriz-master">
                <div class="section-header">
                    <div class="section-icon"><i class="fa-solid fa-table-list"></i></div>
                    <h2 class="section-title">2. Matriz Master SSOT de Achados</h2>
                </div>
                <div class="md-rendered-content">
                    {ssot_table_html}
                </div>
            </section>

            <!-- Seção 3: Fichas 360° Detalhadas -->
            <section class="section-card" id="fichas">
                <div class="section-header">
                    <div class="section-icon"><i class="fa-solid fa-list-check"></i></div>
                    <h2 class="section-title">3. Caderno de Fichas 360° Detalhadas (Técnicas, Estruturais e Contratuais)</h2>
                </div>

                <!-- Toolbar de Busca e Filtros Avançados (Inclui Filtro por Categoria) -->
                <div class="filter-toolbar">
                    <div class="filter-group">
                        <span class="filter-label">Filtros:</span>
                        <button class="btn-filter active" onclick="filterByCrit('ALL', this)">Todos ({len(findings)})</button>
                        <button class="btn-filter" onclick="filterByCrit('Crítica', this)">Crítica</button>
                        <button class="btn-filter" onclick="filterByCrit('Alta', this)">Alta</button>
                        <button class="btn-filter" onclick="filterByCrit('Média', this)">Média</button>
                        <button class="btn-filter" onclick="filterByCrit('Baixa', this)">Baixa</button>
                        <button class="btn-filter" onclick="filterByTipo('Estrutur', this)">Estruturais / Numeração</button>
                    </div>

                    <div class="filter-group" style="margin-top: 6px;">
                        <select id="catSelect" class="btn-filter" onchange="applyFilters()" style="padding: 6px 12px;">
                            <option value="ALL">🏷️ Todas as Categorias</option>
                            {cat_options_html}
                        </select>

                        <select id="docSelect" class="btn-filter" onchange="applyFilters()" style="padding: 6px 12px;">
                            <option value="ALL">📄 Todos os Documentos</option>
                            {doc_options_html}
                        </select>

                        <select id="adjudicationSelect" class="btn-filter" onchange="applyFilters()" style="padding: 6px 12px;">
                            <option value="ALL">⚖️ Todos os Status</option>
                            <option value="pendente">Pendente de adjudicação</option>
                            <option value="confirmado">Confirmado</option>
                            <option value="falso_positivo">Falso positivo</option>
                            <option value="fora_de_escopo">Fora de escopo</option>
                            <option value="evidencia_insuficiente">Evidência insuficiente</option>
                            <option value="duplicado">Duplicado</option>
                        </select>
                    </div>

                    <div class="search-box" style="margin-top: 6px;">
                        <i class="fa-solid fa-magnifying-glass"></i>
                        <input type="text" id="findingSearch" placeholder="Buscar por ID, documento, texto..." onkeyup="applyFilters()">
                    </div>
                </div>

                <!-- Lista de Cards -->
                <div id="findingsContainer">
                    {findings_cards_html if findings_cards_html else '<p><em>Nenhum achado registrado.</em></p>'}
                </div>
            </section>

            <!-- Seção 4: Caderno de Erratas (De → Para) -->
            <section class="section-card" id="erratas">
                <div class="section-header">
                    <div class="section-icon"><i class="fa-solid fa-file-pen"></i></div>
                    <h2 class="section-title">4. Caderno de Erratas e Redações Sugeridas (De → Para)</h2>
                </div>
                <div class="md-rendered-content">
                    <div class="ssot-intro-note">
                        <i class="fa-solid fa-circle-info"></i> <strong>Substituições Redacionais Diretas:</strong> As propostas de redação abaixo constituem alternativas não oficiais para correções ortográficas, gramaticais, numéricas e estruturais diretas. Clique no ID do achado para acessar a Ficha 360° de origem.
                    </div>
                    {erratas_table_html}
                </div>
            </section>

            <!-- Seção 5: Planos de Ação & Perguntas Formais -->
            <section class="section-card" id="acoes-perguntas">
                <div class="section-header">
                    <div class="section-icon"><i class="fa-solid fa-clipboard-question"></i></div>
                    <h2 class="section-title">5. Planos de Ação & Perguntas Formais de Esclarecimento</h2>
                </div>
                <div class="md-rendered-content">
                    {acoes_html}
                </div>
            </section>

            <!-- Seção 6: Lacunas & Riscos -->
            <section class="section-card" id="lacunas-riscos">
                <div class="section-header">
                    <div class="section-icon"><i class="fa-solid fa-triangle-exclamation"></i></div>
                    <h2 class="section-title">6. Mapeamento de Lacunas Estratégicas & Matriz de Riscos</h2>
                </div>
                <div class="md-rendered-content">
                    {lacunas_html}
                </div>
            </section>

            <!-- Seção 7: Conformidade Checklists -->
            <section class="section-card" id="checklists">
                <div class="section-header">
                    <div class="section-icon"><i class="fa-solid fa-square-check"></i></div>
                    <h2 class="section-title">7. Status de Conformidade por Checklist de Domínio</h2>
                </div>
                <div class="md-rendered-content">
                    {checklists_html}
                </div>
            </section>

            <!-- Seção 8: Rastreabilidade de Baseline & Hashes SHA-256 (Capítulo Final Isolado) -->
            <section class="section-card" id="rastreabilidade">
                <div class="section-header">
                    <div class="section-icon"><i class="fa-solid fa-fingerprint"></i></div>
                    <h2 class="section-title">8. Rastreabilidade de Baseline, Hashes SHA-256 & Log de Execução</h2>
                </div>
                <div class="md-rendered-content">
                    {rastrea_html}
                </div>
            </section>

        </main>
    </div>

    <!-- Scripts de Interatividade -->
    <script>
        let currentCritFilter = 'ALL';
        let currentTipoFilter = 'ALL';

        function toggleSidebar() {{
            const sidebar = document.getElementById('sidebar');
            sidebar.classList.toggle('collapsed');
        }}

        function filterByCrit(crit, btn) {{
            currentCritFilter = crit;
            currentTipoFilter = 'ALL';
            document.querySelectorAll('.filter-toolbar .btn-filter').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            applyFilters();
        }}

        function filterByTipo(tipoSub, btn) {{
            currentTipoFilter = tipoSub;
            currentCritFilter = 'ALL';
            document.querySelectorAll('.filter-toolbar .btn-filter').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            applyFilters();
        }}

        function applyFilters() {{
            const search = document.getElementById('findingSearch').value.toLowerCase();
            const docVal = document.getElementById('docSelect').value;
            const catVal = document.getElementById('catSelect').value;
            const adjudicationVal = document.getElementById('adjudicationSelect').value;
            const cards = document.querySelectorAll('.finding-card');

            cards.forEach(card => {{
                const searchData = (card.dataset.search || '').toLowerCase();
                const cardCrit = card.dataset.crit || '';
                const cardDoc = card.dataset.doc || '';
                const cardTipo = card.dataset.tipo || '';
                const cardCat = card.dataset.cat || '';
                const cardAdjudication = card.dataset.adjudication || 'pendente';

                const matchSearch = !search || searchData.includes(search);
                const matchDoc = (docVal === 'ALL') || (cardDoc === docVal);
                const matchCat = (catVal === 'ALL') || (cardCat === catVal);
                const matchAdjudication = (adjudicationVal === 'ALL') || (cardAdjudication === adjudicationVal);
                const matchCrit = (currentCritFilter === 'ALL') || (cardCrit === currentCritFilter);
                const matchTipo = (currentTipoFilter === 'ALL') || (cardTipo.toLowerCase().includes(currentTipoFilter.toLowerCase()));

                if (matchSearch && matchDoc && matchCat && matchAdjudication && matchCrit && matchTipo) {{
                    card.style.display = 'block';
                }} else {{
                    card.style.display = 'none';
                }}
            }});
        }}

        function copySnippet(elementId, btn) {{
            const text = document.getElementById(elementId).innerText.replace(/^"|"$/g, '');
            navigator.clipboard.writeText(text).then(() => {{
                const originalText = btn.innerHTML;
                btn.innerHTML = '<i class="fa-solid fa-check"></i> Copiado!';
                btn.classList.add('copied');
                setTimeout(() => {{
                    btn.innerHTML = originalText;
                    btn.classList.remove('copied');
                }}, 2000);
            }});
        }}
    </script>
</body>
</html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_template)

    return f"HTML compilado com sucesso em: {output_path} ({len(html_template)} bytes, {len(findings)} achados integrados)"


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        ts = sys.argv[1]
        print(compile_timestamp_html(ts))
    else:
        print("Uso: python3 html_compiler.py <timestamp>")
