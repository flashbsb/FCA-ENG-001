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
from audit_pipeline import sanitize_batch_isolation, clean_unicode_text

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
    """Converte Markdown inline para tags HTML, linkando IDs de achado quando ativado."""
    if not text:
        return ""
    text = clean_unicode_text(text)
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)

    if linkify_ids:
        text = re.sub(
            r'\b([A-Z]{2,7}-[A-Z0-9]{3,10})\b',
            r'<a href="#card-\1" class="ssot-link"><i class="fa-solid fa-arrow-right-to-bracket"></i> \1</a>',
            text,
        )

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


def build_executive_email_model(data_json: dict) -> dict:
    """Constroi a minuta estruturada de e-mail executivo (Markdown + texto + estrutura HTML) a partir do SSOT."""
    resumo_exec = data_json.get("resumo_executivo") if isinstance(data_json.get("resumo_executivo"), dict) else {}
    kpis = data_json.get("kpis") if isinstance(data_json.get("kpis"), dict) else {}
    findings = data_json.get("findings") if isinstance(data_json.get("findings"), list) else []
    confirmed = _confirmed_findings(findings)
    if not confirmed and not data_json.get("adjudication_summary"):
        confirmed = list(findings)

    baseline_files = data_json.get("baseline_files") if isinstance(data_json.get("baseline_files"), list) else []
    review_comments = data_json.get("review_comments") if isinstance(data_json.get("review_comments"), list) else []
    parecer = clean_unicode_text(str(data_json.get("parecer") or "APTO COM RESSALVAS"))
    timestamp = clean_unicode_text(str(data_json.get("timestamp") or "—"))
    title = clean_unicode_text(str(data_json.get("title") or "Revisão Técnica Independente"))
    meta = data_json.get("metadata") if isinstance(data_json.get("metadata"), dict) else {}
    versao_doc = clean_unicode_text(str(meta.get("versao_documento") or ""))

    targets = [
        str(bf.get("name") or os.path.basename(str(bf.get("path", ""))))
        for bf in baseline_files
        if str(bf.get("role") or "alvo_principal") == "alvo_principal"
    ] or [str(bf.get("name") or os.path.basename(str(bf.get("path", "")))) for bf in baseline_files]
    supports = [
        str(bf.get("name") or os.path.basename(str(bf.get("path", ""))))
        for bf in baseline_files
        if str(bf.get("role") or "") == "apoio_cruzamento"
    ]
    main_doc_label = ", ".join(targets[:2]) if targets else title
    if len(targets) > 2:
        main_doc_label += f" (+{len(targets) - 2})"

    confirmados_n = int(kpis.get("achados_confirmados", len(confirmed)) or 0)
    criticos_n = int(kpis.get("criticos", sum(1 for a in confirmed if str(a.get("criticidade", a.get("crit", ""))).casefold() in ("crítica", "critica"))) or 0)
    altos_n = int(kpis.get("altos", sum(1 for a in confirmed if str(a.get("criticidade", a.get("crit", ""))).casefold() == "alta")) or 0)
    medios_n = int(kpis.get("medios", sum(1 for a in confirmed if str(a.get("criticidade", a.get("crit", ""))).casefold() in ("média", "media"))) or 0)
    baixos_n = int(kpis.get("baixos", sum(1 for a in confirmed if str(a.get("criticidade", a.get("crit", ""))).casefold() in ("baixa", "informativa"))) or 0)
    pendentes_n = int(kpis.get("achados_pendentes_adjudicacao", 0) or 0)
    perguntas_n = int(kpis.get("perguntas", len(data_json.get("esclarecimentos") or [])) or 0)
    iqd_val = clean_unicode_text(str(kpis.get("iqd", "—")))

    assunto = clean_unicode_text(str(
        resumo_exec.get("assunto_email")
        or f"Parecer Técnico — Revisão Técnica Independente: {main_doc_label} ({parecer})"
    ))
    destinatario = clean_unicode_text(str(
        resumo_exec.get("destinatario_sugerido")
        or "[Responsável pela demanda / Coordenação Técnica do Projeto]"
    ))

    referencias = [f"Documento(s)-alvo avaliado(s): `{main_doc_label}`" + (f" ({versao_doc})" if versao_doc else "")]
    if supports:
        referencias.append(f"Documentos de correlação avaliados no lote: {', '.join(f'`{s}`' for s in supports)}")
    referencias.append(f"Relatório Técnico Consolidado (HTML): `analise/{timestamp}/relatorios/index.html`")
    if review_comments:
        referencias.append(f"Anotações de revisão trianguladas: {len(review_comments)} item(ns) `COM-001..{len(review_comments):03d}` (Seção 8 do `index.html`)")

    kpis_line = (
        f"**{confirmados_n} achados válidos** (`{criticos_n} Críticos`, `{altos_n} Altos`, `{medios_n} Médios`, `{baixos_n} Baixos`), "
        f"**{perguntas_n} perguntas técnicas formais**"
        + (f" e **{len(review_comments)} anotações trianguladas**" if review_comments else "")
        + (f" *(atenção: {pendentes_n} achado(s) pendente(s) de adjudicação)*" if pendentes_n else "")
    )

    avaliacao_maturidade = clean_unicode_text(str(
        resumo_exec.get("avaliacao_maturidade")
        or resumo_exec.get("justificativa_parecer")
        or (
            f"Auditoria executada conforme procedimento FCA-ENG-001 sobre {len(baseline_files)} arquivo(s) da baseline, "
            f"resultando no parecer {parecer} (IQD {iqd_val}). "
            + (
                f"Foram confirmados {criticos_n} achado(s) crítico(s) e {altos_n} de alta severidade que exigem saneamento antes da aprovação."
                if criticos_n or altos_n else
                "Foram identificados apontamentos pontuais para endereçamento e registro formal."
            )
        )
    ))

    conclusao_executiva = clean_unicode_text(str(
        resumo_exec.get("conclusao_executiva")
        or (
            f"Com parecer {parecer}, recomenda-se o endereçamento integral dos achados Críticos (P0) e Altos (P1) listados no relatório HTML antes de submissão para aprovação definitiva ou avanço para implantação/LLD."
            if "NÃO APTO" in parecer.upper() else
            f"O parecer atual é {parecer}. Consulte as Fichas 360° e planos de ação no relatório HTML para fechamento das ressalvas e esclarecimentos formais."
        )
    ))

    pontos_fortes_raw = resumo_exec.get("pontos_fortes")
    pontos_fortes = [clean_unicode_text(str(p).strip()) for p in pontos_fortes_raw if str(p).strip()] if isinstance(pontos_fortes_raw, list) else []
    if not pontos_fortes:
        checklists_status = data_json.get("checklists_status") if isinstance(data_json.get("checklists_status"), dict) else {}
        for chk_name, chk_info in checklists_status.items():
            if not isinstance(chk_info, dict):
                continue
            conf_txt = str(chk_info.get("conformidade") or chk_info.get("conformidade_pct") or "").casefold()
            if "conforme" in conf_txt and "não" not in conf_txt and "nao" not in conf_txt:
                pontos_fortes.append(f"Conformidade verificada nos controles do domínio `{chk_name}` ({chk_info.get('observacao', 'requisitos básicos atendidos')}).")
            if len(pontos_fortes) >= 4:
                break
        if not pontos_fortes:
            pontos_fortes = [
                "Rastreabilidade formal garantida por baseline congelada com hashes SHA-256 e correlação cruzada entre documentos do lote.",
                f"Cobertura estruturada aplicada com {len(data_json.get('skills_ativas') or [])} skill(s) especializada(s) do framework FCA-ENG-001.",
            ]

    frag_raw = resumo_exec.get("fragilidades_por_dominio")
    fragilidades: list[dict] = []
    if isinstance(frag_raw, list) and frag_raw:
        for grp in frag_raw:
            if not isinstance(grp, dict):
                continue
            dom = clean_unicode_text(str(grp.get("dominio") or "Achados Técnicos e Estruturais").strip())
            ids = [clean_unicode_text(str(x).strip()) for x in (grp.get("ids") or []) if str(x).strip()]
            itens = [clean_unicode_text(str(x).strip()) for x in (grp.get("itens") or []) if str(x).strip()]
            if dom and (itens or ids):
                fragilidades.append({"dominio": dom, "ids": ids, "itens": itens})

    if not fragilidades:
        sev_rank = {"crítica": 0, "critica": 0, "alta": 1, "média": 2, "media": 2, "baixa": 3, "informativa": 4}
        sorted_conf = sorted(
            confirmed,
            key=lambda a: (
                sev_rank.get(str(a.get("criticidade", a.get("crit", "Média"))).casefold(), 5),
                str(a.get("id", "")),
            ),
        )
        grouped: dict[str, dict] = {}
        for a in sorted_conf[:18]:
            cat = clean_unicode_text(str(a.get("categoria") or a.get("cat") or "Geral"))
            fid = clean_unicode_text(str(a.get("id") or "ACH-000"))
            ftitle = clean_unicode_text(str(a.get("title") or a.get("titulo") or ""))
            crit_lbl = clean_unicode_text(str(a.get("criticidade") or a.get("crit") or "Média"))
            loc_lbl = clean_unicode_text(str(a.get("loc") or a.get("localizacao") or ""))
            bucket = grouped.setdefault(cat, {"dominio": cat, "ids": [], "itens": []})
            bucket["ids"].append(fid)
            item_desc = f"**[{crit_lbl}] {ftitle}** (`{fid}`)" + (f" — {loc_lbl}" if loc_lbl else "")
            bucket["itens"].append(item_desc)
        fragilidades = list(grouped.values())

    acoes_raw = resumo_exec.get("acoes_exigidas")
    acoes_exigidas = [clean_unicode_text(str(a).strip()) for a in acoes_raw if str(a).strip()] if isinstance(acoes_raw, list) else []
    if not acoes_exigidas:
        seen_sols = set()
        sev_rank = {"crítica": 0, "critica": 0, "alta": 1, "média": 2, "media": 2, "baixa": 3, "informativa": 4}
        for a in sorted(
            confirmed,
            key=lambda x: sev_rank.get(str(x.get("criticidade", x.get("crit", "Média"))).casefold(), 5),
        ):
            sol = clean_unicode_text(str(a.get("solucao") or "").strip())
            fid = clean_unicode_text(str(a.get("id") or ""))
            ftit = clean_unicode_text(str(a.get("title") or ""))
            if sol and sol not in seen_sols:
                seen_sols.add(sol)
                acoes_exigidas.append(f"**{ftit} (`{fid}`):** {sol}")
            if len(acoes_exigidas) >= 6:
                break
        if not acoes_exigidas:
            acoes_exigidas = ["Revisar integralmente as Fichas 360° e responder às perguntas formais na Seção 5 do relatório HTML."]

    # Monta versao Markdown completa
    md_lines = [
        f"**Assunto:** {assunto}  ",
        f"**Para:** {destinatario}  ",
        "**Referências:**  ",
    ]
    for r in referencias:
        md_lines.append(f"- {r}  ")
    md_lines.extend([
        "",
        "---",
        "",
        "Prezados(as),",
        "",
        f"Encaminhamos o Relatório Consolidado da Revisão Técnica Independente (RTI) referente ao lote **{title}** (`{main_doc_label}`), acompanhado deste sumário executivo com pontos fortes, fragilidades críticas identificadas e ações exigidas antes de aprovação/avanço.",
        "",
        "## 1. Parecer Executivo",
        "",
        f"- **Status na RTI consolidada (`index.html`):** **{parecer}**",
        f"- **Indicador de Qualidade Documental (IQD):** **{iqd_val}**",
        f"- **Achados confirmados na matriz do relatório:** {kpis_line}",
        f"- **Avaliação de maturidade documental:** {avaliacao_maturidade}",
        "",
        f"> **Conclusão Executiva:** {conclusao_executiva}",
        "",
        "---",
        "",
        "## 2. Pontos Fortes Identificados",
        "",
    ])
    for idx, pf in enumerate(pontos_fortes, 1):
        md_lines.append(f"{idx}. {pf}")
    md_lines.extend([
        "",
        "---",
        "",
        "## 3. Pontos Fracos, Lacunas Críticas e Riscos Identificados",
        "",
    ])
    if fragilidades:
        for idx, grp in enumerate(fragilidades, 1):
            ids_str = f" ({', '.join(f'`{i}`' for i in grp['ids'])})" if grp["ids"] else ""
            md_lines.append(f"### 3.{idx}. {grp['dominio']}{ids_str}")
            for it in grp["itens"]:
                md_lines.append(f"- {it}")
            md_lines.append("")
    else:
        md_lines.append("- Nenhum achado crítico/alto confirmado nesta análise.\n")
    md_lines.extend([
        "---",
        "",
        "## 4. Ações Exigidas antes de Nova Submissão / Aprovação",
        "",
    ])
    for idx, ac in enumerate(acoes_exigidas, 1):
        md_lines.append(f"{idx}. {ac}")
    md_lines.extend([
        "",
        "Permanecemos à disposição para reunião técnica de alinhamento.",
        "",
        "Atenciosamente,  ",
        "**[Sua Assinatura / Equipe de Engenharia e Revisão Técnica]**",
    ])
    markdown_txt = "\n".join(md_lines)

    # Monta versao texto limpo para colagem direta no cliente de e-mail
    def _strip_md(s: str) -> str:
        s = re.sub(r'\*\*(.+?)\*\*', r'\1', s)
        s = re.sub(r'\*(.+?)\*', r'\1', s)
        s = re.sub(r'`([^`]+)`', r'\1', s)
        return s

    plain_lines = [
        f"Assunto: {assunto}",
        f"Para: {destinatario}",
        "Referências:",
    ] + [f"  - {_strip_md(r)}" for r in referencias] + [
        "",
        "Prezados(as),",
        "",
        f"Encaminhamos o Relatório Consolidado da Revisão Técnica Independente (RTI) referente ao lote {title} ({main_doc_label}), acompanhado deste sumário executivo.",
        "",
        "1. PARECER EXECUTIVO",
        f"- Status na RTI: {parecer}",
        f"- Índice de Qualidade Documental (IQD): {iqd_val}",
        f"- Achados confirmados: {_strip_md(kpis_line)}",
        f"- Avaliação de maturidade: {_strip_md(avaliacao_maturidade)}",
        f"- Conclusão executiva: {_strip_md(conclusao_executiva)}",
        "",
        "2. PONTOS FORTES IDENTIFICADOS",
    ] + [f"{idx}. {_strip_md(pf)}" for idx, pf in enumerate(pontos_fortes, 1)] + [
        "",
        "3. PONTOS FRACOS, LACUNAS CRÍTICAS E RISCOS IDENTIFICADOS",
    ]
    for idx, grp in enumerate(fragilidades, 1):
        ids_str = f" ({', '.join(grp['ids'])})" if grp["ids"] else ""
        plain_lines.append(f"3.{idx}. {grp['dominio']}{ids_str}")
        for it in grp["itens"]:
            plain_lines.append(f"  - {_strip_md(it)}")
    plain_lines.extend([
        "",
        "4. AÇÕES EXIGIDAS ANTES DE NOVA SUBMISSÃO / APROVAÇÃO",
    ])
    for idx, ac in enumerate(acoes_exigidas, 1):
        plain_lines.append(f"{idx}. {_strip_md(ac)}")
    plain_lines.extend([
        "",
        "Permanecemos à disposição para reunião técnica de alinhamento.",
        "",
        "Atenciosamente,",
        "[Sua Assinatura / Equipe de Engenharia e Revisão Técnica]",
    ])
    plain_txt = "\n".join(plain_lines)

    return {
        "assunto": assunto,
        "destinatario": destinatario,
        "referencias": referencias,
        "parecer": parecer,
        "iqd": iqd_val,
        "kpis_line": kpis_line,
        "avaliacao_maturidade": avaliacao_maturidade,
        "conclusao_executiva": conclusao_executiva,
        "pontos_fortes": pontos_fortes,
        "fragilidades_por_dominio": fragilidades,
        "acoes_exigidas": acoes_exigidas,
        "markdown": markdown_txt,
        "plain_text": plain_txt,
    }


def _build_resumo_html(data_json: dict) -> str:
    resumo_md = data_json.get("resumo_md", "").strip()
    if resumo_md and not data_json.get("adjudication_summary"):
        return _md_to_html_simple(resumo_md, linkify_ids=True)

    parecer = html.escape(str(data_json.get("parecer", "APTO COM RESSALVAS")))
    kpis = data_json.get("kpis", {})
    baseline_files = data_json.get("baseline_files", [])
    skills_ativas = data_json.get("skills_ativas", ["analisar-documento"])
    timestamp = html.escape(str(data_json.get("timestamp", "—")))
    title = html.escape(str(data_json.get("title", "Revisão Técnica Independente")))
    coverage = data_json.get("cobertura_extracao", {})
    coverage_html = (
        f"<tr><td>Arquivos extraídos com texto</td><td><strong>{int(coverage.get('extraidos', 0))}</strong> "
        f"de {int(coverage.get('total_arquivos', len(baseline_files)))}</td></tr>"
        f"<tr><td>Arquivos não verificáveis</td><td><strong>{int(coverage.get('nao_verificaveis', 0))}</strong></td></tr>"
    )
    semantic = data_json.get("semantic_analysis", {})
    semantic_status = html.escape(str(semantic.get("status", "não iniciada")))
    semantic_reviewed = int(semantic.get("reviewed_scope_count", len(semantic.get("reviewed_scopes", [])) or 0))
    semantic_expected = int(semantic.get("expected_scope_count", len(semantic.get("required_scopes", [])) or 0))
    semantic_html = f"<tr><td>Revisão semântica especializada</td><td><strong>{semantic_status}</strong> · {semantic_reviewed} de {semantic_expected} escopos</td></tr>"
    pending = int(kpis.get("achados_pendentes_adjudicacao", 0))
    adjudication_note = (
        f'<div class="ssot-intro-note"><strong>Adjudicação:</strong> {int(kpis.get("achados_confirmados", 0))} confirmado(s), '
        f'{pending} pendente(s) e {int(kpis.get("achados_excluidos", 0))} excluído(s) com justificativa. '
        + ("O parecer permanece pendente; candidatos não revisados não contam como riscos confirmados." if pending else "O parecer considera somente achados confirmados.")
        + "</div>"
    )

    skills_badges = "".join([
        f'<span class="badge-skill" style="display:inline-block; margin:4px; padding:6px 12px; background:var(--primary-light); color:var(--primary); border-radius:6px; font-weight:600;"><i class="fa-solid fa-microchip"></i> {html.escape(str(s))}</span>'
        for s in skills_ativas
    ])

    email_model = build_executive_email_model(data_json)
    known_ids = {str(f.get("id", "")) for f in (data_json.get("findings") or []) if f.get("id")}

    def _render_email_line(txt: str) -> str:
        safe = _inline_md(html.escape(txt), linkify_ids=False)
        for fid in sorted(known_ids, key=len, reverse=True):
            esc_fid = html.escape(fid)
            href_fid = html.escape(fid, quote=True)
            safe = re.sub(
                rf'(?<![A-Za-z0-9_-]){re.escape(esc_fid)}(?![A-Za-z0-9_-])',
                f'<a href="#card-{href_fid}" class="ssot-link">{esc_fid}</a>',
                safe,
            )
        return safe

    refs_html = "".join(f"<li>{_render_email_line(r)}</li>" for r in email_model["referencias"])
    pf_html = "".join(f"<li>{_render_email_line(pf)}</li>" for pf in email_model["pontos_fortes"])
    frag_html = ""
    for idx, grp in enumerate(email_model["fragilidades_por_dominio"], 1):
        id_badges = " ".join(
            (
                f'<a href="#card-{html.escape(i, quote=True)}" class="ssot-link">{html.escape(i)}</a>'
                if i in known_ids else f'<code>{html.escape(i)}</code>'
            )
            for i in grp.get("ids", [])
        )
        itens_li = "".join(f"<li>{_render_email_line(it)}</li>" for it in grp.get("itens", []))
        frag_html += (
            f"<div class='email-domain-block'>"
            f"<h5>3.{idx}. {html.escape(grp['dominio'])}{' — ' + id_badges if id_badges else ''}</h5>"
            f"<ul>{itens_li}</ul></div>"
        )
    acoes_li = "".join(f"<li>{_render_email_line(ac)}</li>" for ac in email_model["acoes_exigidas"])

    email_box_html = f"""
        <div id="minuta-email-executivo" class="email-executivo-box">
            <div class="email-executivo-header">
                <div>
                    <h4 style="margin:0; color:var(--secondary);"><i class="fa-solid fa-envelope-open-text" style="color:#0d9488;"></i> Minuta de E-mail Executivo para Encaminhamento</h4>
                    <small style="color:var(--text-muted);">Gerada automaticamente a partir do SSOT atual ({html.escape(email_model['parecer'])} · IQD {html.escape(email_model['iqd'])}).</small>
                </div>
                <div class="email-executivo-actions">
                    <button class="btn-copy" onclick="copySnippet('emailPlainText', this)"><i class="fa-solid fa-copy"></i> Copiar para E-mail (Texto)</button>
                    <button class="btn-copy" style="background:#0f766e;" onclick="copySnippet('emailMarkdownText', this)"><i class="fa-solid fa-file-lines"></i> Copiar em Markdown (.md)</button>
                </div>
            </div>
            <div class="email-executivo-preview">
                <p><strong>Assunto:</strong> {html.escape(email_model['assunto'])}</p>
                <p><strong>Para:</strong> {html.escape(email_model['destinatario'])}</p>
                <p><strong>Referências:</strong></p>
                <ul>{refs_html}</ul>
                <hr class="md-hr">
                <p><strong>1. Parecer Executivo:</strong> <strong>{html.escape(email_model['parecer'])}</strong> · IQD <strong>{html.escape(email_model['iqd'])}</strong> · {_render_email_line(email_model['kpis_line'])}</p>
                <p><strong>Maturidade Documental:</strong> {_render_email_line(email_model['avaliacao_maturidade'])}</p>
                <blockquote class="md-quote"><strong>Conclusão Executiva:</strong> {_render_email_line(email_model['conclusao_executiva'])}</blockquote>
                <p style="margin-top:12px;"><strong>2. Pontos Fortes Identificados:</strong></p>
                <ol>{pf_html}</ol>
                <p style="margin-top:12px;"><strong>3. Pontos Fracos, Lacunas Críticas e Riscos Identificados:</strong></p>
                {frag_html}
                <p style="margin-top:12px;"><strong>4. Ações Exigidas antes de Nova Submissão / Aprovação:</strong></p>
                <ol>{acoes_li}</ol>
            </div>
            <pre id="emailPlainText" style="display:none;">{html.escape(email_model['plain_text'])}</pre>
            <pre id="emailMarkdownText" style="display:none;">{html.escape(email_model['markdown'])}</pre>
        </div>
    """

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
                <tr><td>Índice IQD (Qualidade Documental)</td><td><strong style="color:var(--success);">{html.escape(str(kpis.get("iqd", "100%")))}</strong></td></tr>
                {coverage_html}
                {semantic_html}
            </tbody>
        </table>
        
        <div class="ssot-intro-note" style="margin-top:22px;">
            <i class="fa-solid fa-fingerprint"></i> <strong>Baseline Auditada:</strong> {len(baseline_files)} arquivo(s) congelado(s) com hash criptográfico.
            <a href="#rastreabilidade" class="ssot-link">Consultar inventário completo e hashes SHA-256 na Seção 8</a>
        </div>
        
        <h4 style="margin-top:25px;">Skills e Agentes Especializados Ativados</h4>
        <div class="skills-grid" style="margin-top:10px;">
            {skills_badges}
        </div>
        {email_box_html}
    </div>
    """


def _build_acoes_html(data_json: dict) -> str:
    acoes_md = data_json.get("acoes_md", "").strip()
    if acoes_md and not data_json.get("adjudication_summary"):
        return _md_to_html_simple(acoes_md, linkify_ids=True)

    findings = data_json.get("findings", [])
    confirmed_ids = {str(item.get("id", "")) for item in _confirmed_findings(findings)}
    redacoes = [item for item in data_json.get("redacoes", []) if str(item.get("achado_id", item.get("achado", ""))) in confirmed_ids]
    esclarecimentos = [
        item for item in data_json.get("esclarecimentos", [])
        if not item.get("finding_id") or str(item.get("finding_id", "")) in confirmed_ids
    ]

    act_rows = ""
    if redacoes:
        for idx, r in enumerate(redacoes, 1):
            aid = html.escape(str(r.get("id", f"ACT-{idx:03d}")))
            achado_id_raw = str(r.get("achado_id", r.get("achado", "—")))
            achado_link = (
                f'<a href="#card-{html.escape(achado_id_raw, quote=True)}" class="ssot-link">{html.escape(achado_id_raw)}</a>'
                if achado_id_raw != "—" else "—"
            )
            desc = html.escape(str(r.get("acao", r.get("descricao", "—"))))
            prio = html.escape(str(r.get("prio", r.get("prioridade", "P2"))))
            resp = html.escape(str(r.get("responsavel", r.get("proprietario", "Equipe Técnica"))))
            act_rows += f"<tr><td><strong>{aid}</strong></td><td>{achado_link}</td><td>{desc}</td><td><span class='badge-prio'>{prio}</span></td><td>{resp}</td></tr>"
    else:
        for idx, f in enumerate(_confirmed_findings(findings), 1):
            if f.get("solucao"):
                fid_raw = str(f.get("id", "ACH-000"))
                fid_esc = html.escape(fid_raw)
                fid_href = html.escape(fid_raw, quote=True)
                sol_txt = html.escape(str(f["solucao"]))
                prio_txt = html.escape(str(f.get("prioridade", "P2")))
                prop_txt = html.escape(str(f.get("proprietario", "Proprietário Técnico")))
                act_rows += f"<tr><td><strong>ACT-{idx:03d}</strong></td><td><a href='#card-{fid_href}' class='ssot-link'>{fid_esc}</a></td><td>{sol_txt}</td><td><span class='badge-prio'>{prio_txt}</span></td><td>{prop_txt}</td></tr>"

    if not act_rows:
        act_rows = '<tr><td colspan="5">Nenhum plano de ação registrado separadamente. Consulte as Fichas 360°.</td></tr>'

    q_rows = ""
    for idx, esc in enumerate(esclarecimentos, 1):
        qid = html.escape(str(esc.get("id") or esc.get("id_pergunta") or f"Q-{idx:03d}"))
        fid_raw = str(esc.get("finding_id") or "").strip()
        fid_link = (
            f'<a href="#card-{html.escape(fid_raw, quote=True)}" class="ssot-link">{html.escape(fid_raw)}</a>'
            if fid_raw else "—"
        )
        doc = str(esc.get("doc") or esc.get("doc_ref") or esc.get("documento") or "—")
        secao = str(esc.get("secao_ref") or "")
        doc_display = html.escape(f"{doc} ({secao})" if secao and secao != doc and secao not in doc else doc)
        perg = html.escape(str(esc.get("pergunta") or "—"))
        imp = html.escape(str(esc.get("impacto") or esc.get("justificativa") or esc.get("contexto") or "—"))
        dest = html.escape(str(esc.get("destinatario") or "Comissão Técnica"))
        q_rows += f"<tr><td><strong>{qid}</strong></td><td>{fid_link}</td><td><code>{doc_display}</code></td><td>{perg}</td><td>{imp}</td><td>{dest}</td></tr>"

    if not q_rows:
        q_rows = '<tr><td colspan="6">Nenhuma pergunta formal registrada nesta auditoria.</td></tr>'

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
                        <th>Achado Vinculado</th>
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

    lac_items = lacunas if lacunas else [
        f for f in _confirmed_findings(findings)
        if "lacuna" in str(f.get("tipo", "")).lower()
        or "lacuna" in str(f.get("categoria", "")).lower()
        or "omissão" in str(f.get("tipo", "")).lower()
    ]
    lac_rows = ""
    for idx, lac in enumerate(lac_items, 1):
        lid_raw = str(lac.get("id") or f"LAC-{idx:03d}")
        lid_esc = html.escape(lid_raw)
        lid_href = html.escape(lid_raw, quote=True)
        lid_cell = f'<a href="#card-{lid_href}" class="ssot-link">{lid_esc}</a>' if lac.get("id") else f'<strong>{lid_esc}</strong>'
        doc_raw = str(lac.get("doc_origem") or lac.get("doc") or lac.get("documento") or "—")
        loc_raw = str(lac.get("loc") or lac.get("localizacao") or "").strip()
        doc_display = html.escape(f"{doc_raw} ({loc_raw})" if loc_raw and loc_raw != "—" and loc_raw not in doc_raw else doc_raw)
        title_txt = str(lac.get("title") or lac.get("descricao") or lac.get("titulo") or "").strip()
        fato_txt = str(lac.get("fato") or "").strip()
        desc_raw = f"{title_txt} — {fato_txt}" if (title_txt and fato_txt and title_txt != fato_txt) else (title_txt or fato_txt or "—")
        desc = html.escape(desc_raw)
        crit_raw = str(lac.get("criticidade") or lac.get("crit") or "Média")
        crit = html.escape(crit_raw)
        c_class = (
            "crit-critica" if "crítica" in crit_raw.lower()
            else "crit-alta" if "alta" in crit_raw.lower()
            else "crit-media" if ("média" in crit_raw.lower() or "media" in crit_raw.lower())
            else "crit-baixa"
        )
        mitig = html.escape(str(lac.get("solucao") or lac.get("mitigacao") or lac.get("acao_sugerida") or "Solicitar esclarecimento formal."))
        lac_rows += f"<tr><td>{lid_cell}</td><td><code>{doc_display}</code></td><td>{desc}</td><td><span class='badge-crit {c_class}'>{crit}</span></td><td>{mitig}</td></tr>"

    if not lac_rows:
        lac_rows = '<tr><td colspan="5">Nenhuma lacuna confirmada registrada nesta análise.</td></tr>'

    rsc_items = riscos if riscos else [
        f for f in _confirmed_findings(findings)
        if "risco" in str(f.get("tipo", "")).lower() or "risco" in str(f.get("categoria", "")).lower()
    ]
    rsc_rows = ""
    for idx, rsc in enumerate(rsc_items, 1):
        rid_raw = str(rsc.get("id") or f"RSC-{idx:03d}")
        rid_esc = html.escape(rid_raw)
        rid_href = html.escape(rid_raw, quote=True)
        rid_cell = f'<a href="#card-{rid_href}" class="ssot-link">{rid_esc}</a>' if rsc.get("id") else f'<strong>{rid_esc}</strong>'
        ev = html.escape(str(rsc.get("evento") or rsc.get("title") or rsc.get("titulo") or "—"))
        prob = html.escape(str(rsc.get("prob") or rsc.get("probabilidade") or rsc.get("criticidade") or "Média"))
        imp = html.escape(str(rsc.get("impacto") or "Médio"))
        mitig = html.escape(str(rsc.get("solucao") or rsc.get("mitigacao") or "—"))
        rsc_rows += f"<tr><td>{rid_cell}</td><td>{ev}</td><td>{prob}</td><td>{imp}</td><td>{mitig}</td></tr>"

    if not rsc_rows:
        rsc_rows = '<tr><td colspan="5">Nenhum risco confirmado registrado separadamente. Consulte as Fichas 360°.</td></tr>'

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
        safe_chk = html.escape(str(chk_name))
        html_out += f"<div class='checklist-card' style='margin-bottom:25px;'><h4 style='color:var(--primary);'><i class='fa-solid fa-square-check'></i> Checklist: <code>{safe_chk}</code></h4>"
        if isinstance(chk_data, dict):
            conf_raw = str(chk_data.get("conformidade") or chk_data.get("conformidade_pct") or "—")
            conf_esc = html.escape(conf_raw)
            obs_esc = html.escape(str(chk_data.get("observacao") or "Checklist verificado."))
            conf_cf = conf_raw.casefold()
            conf_cls = (
                "crit-baixa" if ("conforme" in conf_cf and "não" not in conf_cf and "nao" not in conf_cf)
                else ("crit-critica" if ("não conforme" in conf_cf or "nao conforme" in conf_cf) else "crit-media")
            )
            html_out += f"<p style='margin:6px 0 10px;'><strong>Status:</strong> <span class='badge-crit {conf_cls}'>{conf_esc}</span> &nbsp;|&nbsp; <strong>Observação:</strong> {obs_esc}</p>"
            itens = chk_data.get("itens") or []
            if itens:
                html_out += """<div class='table-responsive'><table class='rpt-table'>
                    <thead><tr><th>Verificação</th><th>Status</th><th>Achado Vinculado</th><th>Evidência</th></tr></thead><tbody>"""
                for item in itens:
                    st = str(item.get("status", "")).lower().replace(" ", "_")
                    badge_st = '<span class="badge-crit crit-baixa">Conforme</span>' if "conforme" in st and "nao" not in st and "não" not in st else \
                               '<span class="badge-crit crit-critica">Não Conforme</span>' if ("nao_conforme" in st or "não_conforme" in st) else \
                               '<span class="badge-crit crit-info">N/A</span>'
                    achado_raw = str(item.get("achado", "—"))
                    achado_link = (
                        f'<a href="#card-{html.escape(achado_raw, quote=True)}" class="ssot-link">{html.escape(achado_raw)}</a>'
                        if achado_raw and achado_raw != "—" else "—"
                    )
                    verif_esc = html.escape(str(item.get("verificacao", "—")))
                    evid_esc = html.escape(str(item.get("evidencia", "—")))
                    html_out += f"<tr><td>{verif_esc}</td><td>{badge_st}</td><td>{achado_link}</td><td>{evid_esc}</td></tr>"
                html_out += "</tbody></table></div>"
        html_out += "</div>"
    html_out += "</div>"
    return html_out


def _build_rastrea_html(data_json: dict, rel_dir: str = None) -> str:
    rastrea_md = data_json.get("rastrea_md", "").strip()
    if rastrea_md:
        return _md_to_html_simple(rastrea_md, linkify_ids=False)

    baseline_files = data_json.get("baseline_files", [])
    timestamp = html.escape(str(data_json.get("timestamp", "—")))
    skills_ativas = data_json.get("skills_ativas", ["analisar-documento"])
    kpis = data_json.get("kpis", {})
    findings = data_json.get("findings", [])

    def _role_badge_html(role_value: str) -> str:
        role_cf = str(role_value or "alvo_principal").strip()
        if role_cf == "apoio_cruzamento":
            return '<span class="badge-crit crit-media">🔗 Apoio / Confronto Cruzado</span>'
        if role_cf == "insumo_externo":
            return '<span class="badge-crit crit-alta">🔍 Insumo Externo (Não Fonte de Verdade)</span>'
        return '<span class="badge-crit crit-baixa">🎯 Documento-Alvo Principal</span>'

    role_by_ref = {}
    b_rows = ""
    for bf in baseline_files:
        name_raw = str(bf.get("name", bf.get("filename", "—")))
        path_raw = str(bf.get("path", name_raw))
        role_raw = str(bf.get("role") or "alvo_principal").strip()
        role_by_ref[path_raw] = role_raw
        role_by_ref[name_raw] = role_raw
        name = html.escape(name_raw)
        role_badge = _role_badge_html(role_raw)
        size = int(bf.get("size_bytes", bf.get("size", 0)) or 0)
        h = html.escape(str(bf.get("sha256", "—")))
        b_rows += f"<tr><td><code>{name}</code></td><td>{role_badge}</td><td>{size} bytes</td><td><code>{h}</code></td></tr>"

    if not b_rows:
        b_rows = '<tr><td colspan="4">Nenhum arquivo de baseline registrado.</td></tr>'

    external_inputs = data_json.get("external_inputs", []) or []
    external_inputs_html = ""
    if external_inputs:
        ext_rows = ""
        for ei in external_inputs:
            ei_name = html.escape(str(ei.get("name", ei.get("path", "—"))))
            ei_size = int(ei.get("size_bytes", ei.get("size", 0)) or 0)
            ei_hash = html.escape(str(ei.get("sha256", "—")))
            ei_note = html.escape(str(ei.get("nota", "Insumo não normativo — não considerado fonte de verdade.")))
            ext_rows += (
                f"<tr><td><code>{ei_name}</code></td>"
                f"<td>{_role_badge_html('insumo_externo')}</td>"
                f"<td>{ei_size} bytes</td><td><code>{ei_hash}</code></td><td>{ei_note}</td></tr>"
            )
        external_inputs_html = f"""
        <h3 style="margin-top:35px;">Insumos Externos de Auditoria Cruzada (Não-Normativos — Não Fonte de Verdade)</h3>
        <div class="ssot-intro-note">
            <i class="fa-solid fa-triangle-exclamation"></i> Os arquivos abaixo não integram a baseline normativa e não são tratados como fonte de verdade; eventuais hipóteses originadas deles exigem comprovação literal nos documentos da baseline.
        </div>
        <div class="table-responsive">
            <table class="rpt-table">
                <thead>
                    <tr>
                        <th>Nome do Arquivo</th>
                        <th>Classificação</th>
                        <th>Tamanho</th>
                        <th>Hash SHA-256</th>
                        <th>Regra de Custódia</th>
                    </tr>
                </thead>
                <tbody>
                    {ext_rows}
                </tbody>
            </table>
        </div>"""

    review_comments = data_json.get("review_comments", []) or []
    review_comments_html = ""
    if review_comments:
        com_rows = ""
        for com in review_comments:
            cid = html.escape(str(com.get("id_anotacao", "COM-000")))
            cdoc = html.escape(str(com.get("documento", "—")))
            cloc = html.escape(str(com.get("pagina_ou_secao", "—")))
            cauth = html.escape(str(com.get("autor", "Revisor")))
            cref = str(com.get("item_referenciado", "") or "").strip()
            ctext = str(com.get("comentario", "") or "").strip()
            cbody = html.escape(ctext)
            if cref:
                cbody = f"<strong>Trecho:</strong> <em>{html.escape(cref)}</em><br>{cbody}"
            cst_raw = str(com.get("status_triangulacao", "PENDENTE"))
            cst_cf = cst_raw.casefold()
            cst_cls = (
                "crit-baixa" if "procedente" in cst_cf and "im" not in cst_cf and "parcial" not in cst_cf
                else "crit-media" if "parcial" in cst_cf or "refin" in cst_cf or "duvida" in cst_cf or "dúvida" in cst_cf
                else "crit-critica" if "improcedente" in cst_cf or "rejeit" in cst_cf
                else "crit-info"
            )
            ach_id = str(com.get("achado_id_associado") or "").strip()
            if ach_id and ach_id != "—":
                ach_links = ", ".join(
                    f'<a href="#card-{html.escape(part.strip(), quote=True)}" class="ssot-link">{html.escape(part.strip())}</a>'
                    for part in ach_id.split(",") if part.strip()
                )
            else:
                ach_links = "—"
            cparecer = html.escape(str(com.get("parecer_triangulacao", "") or "—"))
            com_rows += (
                f"<tr><td><code>{cid}</code></td><td><code>{cdoc}</code><br><small>{cloc}</small></td>"
                f"<td>{cauth}</td><td>{cbody}</td>"
                f"<td><span class='badge-crit {cst_cls}'>{html.escape(cst_raw)}</span></td>"
                f"<td>{ach_links}</td><td>{cparecer}</td></tr>"
            )
        review_comments_html = f"""
        <h3 style="margin-top:35px;">Triangulação de Comentários e Anotações de Revisão (COM-XXX — Não Fonte de Verdade)</h3>
        <div class="ssot-intro-note">
            <i class="fa-solid fa-comments"></i> Anotações e comentários extraídos de arquivos de revisão foram triangulados tecnicamente contra a baseline normativa antes da consolidação dos achados.
        </div>
        <div class="table-responsive">
            <table class="rpt-table">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Documento / Localização</th>
                        <th>Autor</th>
                        <th>Comentário / Anotação</th>
                        <th>Status de Triangulação</th>
                        <th>Achado Vinculado</th>
                        <th>Parecer Técnico</th>
                    </tr>
                </thead>
                <tbody>
                    {com_rows}
                </tbody>
            </table>
        </div>"""

    # Cobertura de Extração por Arquivo
    coverage = data_json.get("cobertura_extracao", {})
    cov_files = coverage.get("arquivos", []) if isinstance(coverage, dict) else []
    cov_rows = ""
    for cf in cov_files:
        c_file_raw = str(cf.get("arquivo", "—"))
        c_file = html.escape(c_file_raw)
        c_role = cf.get("role") or role_by_ref.get(c_file_raw) or role_by_ref.get(os.path.basename(c_file_raw)) or "alvo_principal"
        c_role_badge = _role_badge_html(c_role)
        c_fmt = html.escape(str(cf.get("formato", "—")))
        c_st = html.escape(str(cf.get("status", "—")))
        c_chars = int(cf.get("caracteres_extraidos", 0) or 0)
        c_aviso = html.escape(str(cf.get("aviso", "") or "—"))
        cov_rows += f"<tr><td><code>{c_file}</code></td><td>{c_role_badge}</td><td><code>{c_fmt}</code></td><td>{c_st}</td><td>{c_chars}</td><td>{c_aviso}</td></tr>"
    coverage_table_html = ""
    if cov_files:
        coverage_table_html = f"""
        <h3 style="margin-top:35px;">Cobertura de Extração por Arquivo da Baseline</h3>
        <div class="table-responsive">
            <table class="rpt-table">
                <thead>
                    <tr>
                        <th>Arquivo</th>
                        <th>Papel no Lote</th>
                        <th>Formato</th>
                        <th>Status de Extração</th>
                        <th>Caracteres Extraídos</th>
                        <th>Observação / Aviso</th>
                    </tr>
                </thead>
                <tbody>
                    {cov_rows}
                </tbody>
            </table>
        </div>"""

    # Matriz de Escopos da Revisão Semântica
    semantic = data_json.get("semantic_analysis", {})
    scope_results = semantic.get("scope_results", {}) if isinstance(semantic, dict) else {}
    required_scopes = semantic.get("required_scopes", []) if isinstance(semantic, dict) else []
    reviewed_scopes_set = set(semantic.get("reviewed_scopes", []) if isinstance(semantic, dict) else [])
    all_scope_keys = sorted(set(required_scopes) | set(scope_results.keys()))
    scope_rows = ""
    for key in all_scope_keys:
        if "::" in key:
            sk_name, doc_p = key.split("::", 1)
        else:
            sk_name, doc_p = key, "—"
        info = scope_results.get(key, {})
        st_val = info.get("status", "revisado" if key in reviewed_scopes_set else "pendente")
        just_val = info.get("justificativa") or "—"
        scope_rows += (
            f"<tr><td><code>{html.escape(sk_name)}</code></td>"
            f"<td><code>{html.escape(doc_p)}</code></td>"
            f"<td>{html.escape(str(st_val))}</td>"
            f"<td>{html.escape(str(just_val))}</td></tr>"
        )
    semantic_matrix_html = ""
    if all_scope_keys:
        semantic_matrix_html = f"""
        <h3 style="margin-top:35px;">Matriz de Escopos da Revisão Semântica (Skill × Documento)</h3>
        <div class="table-responsive">
            <table class="rpt-table">
                <thead>
                    <tr>
                        <th>Skill</th>
                        <th>Documento</th>
                        <th>Status</th>
                        <th>Justificativa</th>
                    </tr>
                </thead>
                <tbody>
                    {scope_rows}
                </tbody>
            </table>
        </div>"""

    # Memória de Cálculo do IQD
    target_count = sum(1 for bf in baseline_files if bf.get("role", "alvo_principal") == "alvo_principal") or len(baseline_files)
    denom = int(kpis.get("iqd_denominador") or max(target_count * 15, 30))
    pesos = {"Crítica": 4, "Alta": 3, "Média": 2, "Baixa": 1, "Informativa": 0}
    confirmed_list = _confirmed_findings(findings)
    pending_n = int(kpis.get("achados_pendentes_adjudicacao", 0))
    impacto_ponderado = sum(pesos.get(a.get("criticidade", a.get("crit", "Média")), 2) for a in confirmed_list)
    max_impacto = denom * 4
    iqd_res = html.escape(str(kpis.get("iqd", "—")))
    iqd_obs = (
        f"Há {pending_n} achado(s) pendente(s) de adjudicação; o IQD exibe '—' até a conclusão da adjudicação."
        if pending_n > 0 else
        f"Calculado sobre {len(confirmed_list)} achado(s) confirmado(s): impacto ponderado = {impacto_ponderado} de máximo {max_impacto} (denominador {denom})."
    )
    iqd_memory_html = f"""
    <h3 style="margin-top:35px;">Memória de Cálculo do Índice de Qualidade Documental (IQD)</h3>
    <div class="table-responsive">
        <table class="rpt-table">
            <thead>
                <tr>
                    <th>Parâmetro</th>
                    <th>Valor / Fórmula</th>
                </tr>
            </thead>
            <tbody>
                <tr><td>Fórmula Aplicada</td><td><code>IQD = max(0, 100 × (1 − Impacto Ponderado / (Denominador × 4)))</code></td></tr>
                <tr><td>Pesos por Criticidade</td><td>Crítica = 4 · Alta = 3 · Média = 2 · Baixa = 1 · Informativa = 0</td></tr>
                <tr><td>Denominador Aplicável</td><td><strong>{denom}</strong> itens (impacto máximo = {max_impacto})</td></tr>
                <tr><td>População Auditada</td><td>{len(confirmed_list)} confirmado(s) · {pending_n} pendente(s) · {int(kpis.get("achados_excluidos", 0))} excluído(s)</td></tr>
                <tr><td>Impacto Ponderado</td><td><strong>{impacto_ponderado if pending_n == 0 else "Aguardando adjudicação"}</strong></td></tr>
                <tr><td>IQD Resultante</td><td><strong>{iqd_res}</strong> — {html.escape(iqd_obs)}</td></tr>
            </tbody>
        </table>
    </div>"""

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
        <p><strong>Estado da interpretação visual:</strong> {html.escape(str(visual_status))} · {len(visual_assets)} ativo(s) extraído(s) · {int(inventory.get('rendered_pdf_pages', 0))} página(s) de PDF renderizada(s).</p>
        <div class="visual-assets-grid">{''.join(visual_cards)}</div>
        """
    else:
        visual_inventory_html = f"<h3 style=\"margin-top:35px;\">Inventário de Imagens e Diagramas</h3><p>Nenhum ativo visual extraído. Estado: {html.escape(str(visual_status))}.</p>"

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
                        <th>Papel no Lote</th>
                        <th>Tamanho</th>
                        <th>Hash SHA-256</th>
                    </tr>
                </thead>
                <tbody>
                    {b_rows}
                </tbody>
            </table>
        </div>

        {external_inputs_html}
        {review_comments_html}
        {coverage_table_html}
        {semantic_matrix_html}
        {iqd_memory_html}
        {visual_inventory_html}

        <h3 style="margin-top:35px;">Log Auditável de Execução da RTI</h3>
        <ul class="audit-log-list" style="line-height:1.8;">
            <li><strong>Timestamp de Execução:</strong> <code>{timestamp}</code></li>
            <li><strong>Skills Ativadas:</strong> {", ".join([f"<code>{html.escape(str(s))}</code>" for s in skills_ativas])}</li>
            {semantic_html}
            <li><strong>Total de Arquivos Analisados:</strong> {len(baseline_files)}</li>
            <li><strong>Total de Achados Auditados:</strong> {kpis.get("total_achados", 0)}</li>
            <li><strong>Índice IQD Resultante:</strong> <strong>{iqd_res}</strong></li>
            <li><strong>Parecer Final Emitido:</strong> <strong>{html.escape(str(data_json.get("parecer", "APTO COM RESSALVAS")))}</strong></li>
        </ul>
    </div>
    """


def compile_timestamp_html(timestamp: str, root_dir: str = None) -> str:
    """Compila a Central Executiva HTML a partir de dados_analise.json ou Markdown."""
    if root_dir is None:
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    clean_ts = (timestamp or "").strip().replace('\\', '/')
    analise_root = os.path.join(root_dir, 'analise')
    direct_rel = os.path.join(analise_root, clean_ts, 'relatorios')

    if os.path.isdir(direct_rel):
        rel_dir = direct_rel
    else:
        # Busca recursiva caso tenha sido passado apenas o timestamp da folha
        rel_dir = direct_rel
        target_leaf = clean_ts.split('/')[-1]
        for dirpath, dirnames, _ in os.walk(analise_root):
            if os.path.basename(dirpath) == target_leaf and 'relatorios' in dirnames:
                candidate = os.path.join(dirpath, 'relatorios')
                if os.path.exists(candidate):
                    rel_dir = candidate
                    break

    output_path = os.path.join(rel_dir, 'index.html')
    json_path = os.path.join(rel_dir, 'dados_analise.json')

    if not os.path.exists(rel_dir):
        return f"Diretório não encontrado: {rel_dir}"

    leaf_name = clean_ts.split('/')[-1]
    lote_name = leaf_name.split('_', 2)[2].replace('_', ' ') if len(leaf_name.split('_', 2)) > 2 else leaf_name
    data_fmt = f"{leaf_name[6:8]}/{leaf_name[4:6]}/{leaf_name[:4]}" if len(leaf_name) >= 8 and leaf_name[:8].isdigit() else leaf_name

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
        kpis["estruturais"] = sum(
            1
            for item in confirmed_findings
            if any(
                token in f"{item.get('tipo', '')} {item.get('categoria', item.get('cat', ''))}".casefold()
                for token in ("estrutur", "errata", "redacional", "rfc", "29148")
            )
        )
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
    doc_options_html = "".join([
        f'<option value="{html.escape(str(d), quote=True)}">{html.escape(str(d))}</option>'
        for d in unique_docs
    ])

    unique_cats = sorted(list(set(f["categoria"] for f in findings if f.get("categoria"))))
    cat_options_html = "".join([
        f'<option value="{html.escape(str(c), quote=True)}">{html.escape(str(c))}</option>'
        for c in unique_cats
    ])

    try:
        master_href = os.path.relpath(os.path.join(analise_root, 'index.html'), rel_dir).replace('\\', '/')
    except Exception:
        master_href = "../../index.html"

    evolution_nav_btn = ""
    local_evo_path = os.path.join(rel_dir, "evolucao.html")
    version_evo_path = os.path.join(os.path.dirname(os.path.dirname(rel_dir)), "evolucao.html")
    has_evolution_meta = bool(
        data_json
        and (
            data_json.get("version_reconciliation")
            or data_json.get("parent_analysis")
            or data_json.get("audit_trail")
        )
    )
    if os.path.isfile(local_evo_path) or has_evolution_meta:
        evo_href = "./evolucao.html"
        evolution_nav_btn = (
            f'<a href="{evo_href}" class="btn-action" style="background:#7c3aed;">'
            f'<i class="fa-solid fa-code-compare"></i> Evolução de Versões</a>'
        )
    elif os.path.isfile(version_evo_path):
        try:
            evo_href = os.path.relpath(version_evo_path, rel_dir).replace('\\', '/')
        except Exception:
            evo_href = "../../evolucao.html"
        evolution_nav_btn = (
            f'<a href="{html.escape(evo_href, quote=True)}" class="btn-action" style="background:#7c3aed;">'
            f'<i class="fa-solid fa-code-compare"></i> Evolução de Versões</a>'
        )

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
            <a href="#card-{html.escape(str(fid), quote=True)}" class="ssot-link" title="Clique para ir ao detalhamento da Ficha 360°">
              <i class="fa-solid fa-circle-chevron-right"></i> <strong>{html.escape(str(fid))}</strong>
            </a>
          </td>
          <td><strong>{html.escape(str(f.get('title','') or ''))}</strong></td>
          <td><code>{html.escape(str(f.get('doc_origem') or '—'))}</code></td>
          <td>{html.escape(str(f.get('loc') or '—'))}</td>
          <td>{html.escape(str(f.get('categoria') or f.get('cat') or '—'))}</td>
          <td><span class="badge-tipo">{html.escape(str(tipo))}</span></td>
          <td><span class="badge-crit {c_class}">{html.escape(str(crit))}</span></td>
          <td><span class="badge-prio">{html.escape(str(prio))}</span></td>
          <td><span class="badge-adjudication {adjudication_class}">{html.escape(str(adjudication_label))}</span></td>
          <td>{html.escape(str(f.get('proprietario') or '—'))}</td>
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
    _empty_errata_vals = {"", "—", "-", "não disponível", "nao disponivel", "n/a"}
    erratas_findings = [
        f
        for f in findings
        if _adjudication_status(f) not in {"falso_positivo", "fora_de_escopo", "duplicado"}
        and (
            str(f.get("de", "") or "").strip().casefold() not in _empty_errata_vals
            or str(f.get("para", "") or "").strip().casefold() not in _empty_errata_vals
        )
        and (
            f.get("is_direct")
            or "→" in str(f.get("tipo", ""))
            or "grafia" in str(f.get("tipo", "")).lower()
            or "sequência" in str(f.get("tipo", "")).lower()
            or str(f.get("de", "") or "").strip().casefold() not in _empty_errata_vals
        )
    ]
    erratas_rows_html = ""
    for f in erratas_findings:
        fid = f.get("id", "ACH-000")
        safe_fid = html.escape(str(fid), quote=True)
        esc_fid = html.escape(str(fid))
        esc_loc = html.escape(str(f.get('loc') or '—'))
        esc_de = html.escape(str(f.get("de") or "—"))
        esc_para = html.escape(str(f.get("para") or "—"))
        esc_prop = html.escape(str(f.get('proprietario') or '—'))
        erratas_rows_html += f"""
        <tr>
          <td>
            <a href="#card-{safe_fid}" class="ssot-link" title="Clique para ver a Ficha 360° de origem">
              <i class="fa-solid fa-arrow-right-to-bracket"></i> <strong>{esc_fid}</strong>
            </a>
          </td>
          <td>{esc_loc}</td>
          <td><span class="de-content" style="display:inline-block; margin:0;">"{esc_de}"</span></td>
          <td><span class="para-content" id="err-para-{safe_fid}" style="display:inline-block; margin:0;">"{esc_para}"</span></td>
          <td>{esc_prop}</td>
          <td>
            <button class="btn-copy" onclick="copySnippet('err-para-{safe_fid}', this)"><i class="fa-solid fa-copy"></i> Copiar</button>
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
        cat = f.get("categoria") or f.get("cat") or "Geral"
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
        is_direct = f.get("is_direct", False) or "→" in str(tipo) or "grafia" in str(tipo).lower() or "sequência" in str(tipo).lower()
        de_txt = str(f.get("de", "") or "")
        para_txt = str(f.get("para", "") or "")
        safe_fid = html.escape(str(fid), quote=True)

        solucao_box = ""
        if is_direct and (de_txt or para_txt):
            solucao_box = f"""
            <div class="de-para-box">
              <div class="de-col">
                <span class="de-label"><i class="fa-solid fa-file-lines"></i> Texto Atual (Baseline):</span>
                <div class="de-content">"{html.escape(de_txt)}"</div>
              </div>
              <div class="para-col">
                <span class="para-label"><i class="fa-solid fa-file-pen"></i> Redação Sugerida (Minuta Não Oficial):</span>
                <div class="para-content" id="para-{safe_fid}">"{html.escape(para_txt)}"</div>
                <button class="btn-copy" onclick="copySnippet('para-{safe_fid}', this)"><i class="fa-solid fa-copy"></i> Copiar Sugestão</button>
              </div>
            </div>"""
        elif f.get("solucao"):
            solucao_box = f"""
            <div class="solucao-box">
              <span class="solucao-label"><i class="fa-solid fa-list-check"></i> Plano de Solução Recomendado:</span>
              <div class="solucao-content">{html.escape(str(f['solucao']))}</div>
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

        ev_raw = str(f.get("evidencia") or f.get("evidencia_nivel") or "E1").strip()
        ev_match = re.match(r"^(E[123])\b", ev_raw, re.I)
        ev_short = ev_match.group(1).upper() if ev_match else html.escape(ev_raw.split()[0] if ev_raw else "E1")

        evidence_sources_html = []
        for source in f.get("evidence_sources", []):
            if not isinstance(source, dict):
                continue
            source_path = html.escape(str(source.get("document_path", "")))
            source_location = html.escape(str(source.get("location", "Localização a confirmar")))
            source_quote = html.escape(str(source.get("quote", "")))
            source_hash = html.escape(str(source.get("sha256", "")))
            evidence_sources_html.append(
                f"<li><strong>{source_path}</strong> · {source_location}<blockquote>“{source_quote}”</blockquote>"
                + (f"<small>SHA-256: <code>{source_hash}</code></small>" if source_hash else "") + "</li>"
            )
        citacao_raw = str(f.get("citacao") or "").strip()
        if not evidence_sources_html and citacao_raw:
            cit_doc = html.escape(str(f.get("doc_origem") or "Documento da baseline"))
            cit_loc = html.escape(str(f.get("loc") or "Localização não informada"))
            evidence_sources_html.append(
                f"<li><strong>{cit_doc}</strong> · {cit_loc}<blockquote>“{html.escape(citacao_raw)}”</blockquote></li>"
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

        semantic_skill = str(f.get("semantic_skill", ""))
        semantic_badge_html = ""
        semantic_evidence_html = ""
        if semantic_skill:
            semantic_badge_html = (
                '<span class="badge-semantic" style="display:inline-block;padding:4px 8px;border-radius:999px;'
                'background:#eef2ff;color:#4338ca;font-size:.75rem;font-weight:700;">Revisão semântica · '
                f"{html.escape(semantic_skill)}</span>"
            )
            semantic_evidence_html = (
                '<div class="semantic-evidence" style="margin:14px 0;padding:12px 14px;border-left:3px solid #6366f1;'
                'background:#f8faff;border-radius:6px;">'
                '<strong>Rastreabilidade semântica:</strong> '
                f"{html.escape(semantic_skill)} · {html.escape(ev_raw or 'E1')}"
                + (f"<ul>{''.join(evidence_sources_html)}</ul>" if evidence_sources_html else "")
                + (f"<strong>Referências corroborativas</strong><ul>{''.join(reference_links)}</ul>" if reference_links else "")
                + "</div>"
            )
        elif evidence_sources_html or reference_links:
            semantic_evidence_html = (
                '<div class="semantic-evidence" style="margin:14px 0;padding:12px 14px;border-left:3px solid #6366f1;'
                'background:#f8faff;border-radius:6px;">'
                '<strong>Evidência Documental (Baseline):</strong> '
                f"{html.escape(ev_raw or 'E1')}"
                + (f"<ul>{''.join(evidence_sources_html)}</ul>" if evidence_sources_html else "")
                + (f"<strong>Referências Normativas</strong><ul>{''.join(reference_links)}</ul>" if reference_links else "")
                + "</div>"
            )

        safe_fid = html.escape(str(fid), quote=True)
        safe_doc = html.escape(str(f.get('doc_origem', '') or ''), quote=True)
        safe_crit = html.escape(str(crit), quote=True)
        safe_prio = html.escape(str(prio), quote=True)
        safe_tipo = html.escape(str(tipo), quote=True)
        safe_cat = html.escape(str(cat), quote=True)
        safe_search = html.escape(
            f"{fid} {f.get('title', '')} {f.get('doc_origem', '')} {f.get('loc', '')} {f.get('fato', '')} {cat}",
            quote=True,
        )

        esc_fid = html.escape(str(fid))
        esc_crit = html.escape(str(crit))
        esc_prio = html.escape(str(prio))
        esc_tipo = html.escape(str(tipo))
        esc_cat = html.escape(str(cat))
        esc_title = html.escape(str(f.get('title', '') or ''))
        esc_doc = html.escape(str(f.get('doc_origem') or '—'))
        esc_loc = html.escape(str(f.get('loc') or '—'))
        esc_fato = html.escape(str(f.get('fato', '') or ''))
        esc_impacto = html.escape(str(f.get('impacto', '') or ''))
        esc_prop = html.escape(str(f.get('proprietario') or '—'))

        findings_cards_html += f"""
        <div class="finding-card {c_class}"
             id="card-{safe_fid}"
             data-id="{safe_fid}"
             data-doc="{safe_doc}"
             data-crit="{safe_crit}"
             data-prio="{safe_prio}"
             data-tipo="{safe_tipo}"
             data-cat="{safe_cat}"
             data-adjudication="{adjudication_status}"
             data-search="{safe_search}">
          <div class="card-top">
            <div class="top-tags">
              <span class="badge-id">{esc_fid}</span>
              <span class="badge-crit {c_class}">{esc_crit}</span>
              <span class="badge-prio">{esc_prio}</span>
              <span class="badge-prio" title="Grau de Evidência">{ev_short}</span>
              <span class="badge-tipo">{esc_tipo}</span>
              <span class="badge-adjudication {adjudication_class}">{html.escape(str(adjudication_label))}</span>
              {semantic_badge_html}
            </div>
            <a href="#matriz-master" class="btn-back-ssot" title="Voltar para a Matriz SSOT"><i class="fa-solid fa-table-list"></i> Ver na Matriz SSOT</a>
          </div>

          <h3 class="finding-title">{esc_title}</h3>

          <div class="finding-meta-row">
            <span><i class="fa-solid fa-file-lines"></i> <strong>Doc:</strong> {esc_doc}</span>
            <span><i class="fa-solid fa-location-dot"></i> <strong>Local:</strong> {esc_loc}</span>
            <span><i class="fa-solid fa-tag"></i> <strong>Categoria:</strong> {esc_cat}</span>
          </div>

          {adjudication_detail_html}

          <div class="finding-body-grid">
            <div class="fato-box">
              <span class="box-title"><i class="fa-solid fa-eye"></i> Fato Observado (Baseline)</span>
              <p>{esc_fato}</p>
            </div>
            <div class="impacto-box">
              <span class="box-title"><i class="fa-solid fa-shield-cat"></i> Impacto Potencial</span>
              <p>{esc_impacto}</p>
            </div>
          </div>

          {solucao_box}

          {visual_evidence_html}
          {semantic_evidence_html}

          <div class="card-bottom">
            <span><i class="fa-solid fa-user-gear"></i> <strong>Proprietário Sugerido:</strong> {esc_prop}</span>
          </div>
        </div>"""

    # Template HTML Final Exaustivo (Sidebar Colapsado por Padrão & 8 Seções)
    html_template = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Relatório RTI — {html.escape(str(lote_name))}</title>

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
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background-color: var(--bg-body);
            color: var(--text-main);
            line-height: 1.65;
            font-size: 14px;
        }}

        h1, h2, h3, h4, h5 {{
            font-family: 'Outfit', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            color: var(--secondary);
            font-weight: 700;
        }}

        /* Ícones offline (autossuficiente sem dependências CDN) */
        .fa-solid {{
            display: inline-block;
            font-style: normal;
            font-variant: normal;
            text-rendering: auto;
            line-height: 1;
            vertical-align: middle;
        }}
        .fa-shield-halved::before {{ content: "🛡"; }}
        .fa-house::before {{ content: "🏠"; }}
        .fa-bars::before {{ content: "☰"; }}
        .fa-print::before {{ content: "⎙"; }}
        .fa-chart-pie::before {{ content: "◔"; }}
        .fa-table-list::before {{ content: "▦"; }}
        .fa-list-check::before {{ content: "☑"; }}
        .fa-file-pen::before {{ content: "✎"; }}
        .fa-clipboard-question::before {{ content: "❓"; }}
        .fa-triangle-exclamation::before {{ content: "⚠"; }}
        .fa-square-check::before {{ content: "✔"; }}
        .fa-fingerprint::before {{ content: "❖"; }}
        .fa-folder-open::before {{ content: "📁"; }}
        .fa-clock::before {{ content: "⏱"; }}
        .fa-calendar::before {{ content: "📅"; }}
        .fa-circle-exclamation::before {{ content: "⚠"; }}
        .fa-hourglass-half::before {{ content: "⏳"; }}
        .fa-circle-check::before {{ content: "✔"; }}
        .fa-magnifying-glass::before {{ content: "🔍"; }}
        .fa-circle-info::before {{ content: "ℹ"; }}
        .fa-circle-chevron-right::before {{ content: "›"; }}
        .fa-arrow-right-to-bracket::before {{ content: "→"; }}
        .fa-copy::before {{ content: "⧉"; }}
        .fa-check::before {{ content: "✓"; }}
        .fa-file-lines::before {{ content: "📄"; }}
        .fa-diagram-project::before {{ content: "❖"; }}
        .fa-location-dot::before {{ content: "📍"; }}
        .fa-tag::before {{ content: "🏷"; }}
        .fa-eye::before {{ content: "👁"; }}
        .fa-shield-cat::before {{ content: "🛡"; }}
        .fa-user-gear::before {{ content: "⚙"; }}
        .fa-microchip::before {{ content: "⚙"; }}
        .fa-code-compare::before {{ content: "⇄"; }}
        .fa-envelope::before {{ content: "✉"; }}
        .fa-envelope-open-text::before {{ content: "✉"; }}
        .fa-comments::before {{ content: "💬"; }}

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

        .email-executivo-box {{ margin-top: 28px; background: #f8fafc; border: 1px solid #cbd5e1; border-left: 5px solid #0d9488; border-radius: 10px; padding: 18px; }}
        .email-executivo-header {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; padding-bottom: 12px; border-bottom: 1px solid var(--border); margin-bottom: 14px; }}
        .email-executivo-actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
        .email-executivo-preview p, .email-executivo-preview li {{ font-size: 0.86rem; line-height: 1.55; margin-bottom: 4px; }}
        .email-executivo-preview ul, .email-executivo-preview ol {{ margin-left: 20px; margin-bottom: 10px; }}
        .email-domain-block {{ margin-top: 10px; padding: 10px 12px; background: #ffffff; border: 1px solid var(--border); border-radius: 8px; }}
        .email-domain-block h5 {{ margin-bottom: 6px; font-size: 0.9rem; color: var(--secondary); }}

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
            {evolution_nav_btn}
            <a href="#minuta-email-executivo" class="btn-action" style="background:#0d9488;"><i class="fa-solid fa-envelope"></i> Minuta E-mail</a>
            <a href="{master_href}" class="btn-action btn-master-home"><i class="fa-solid fa-house"></i> Central Master</a>
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
                <span class="hero-tag"><i class="fa-solid fa-folder-open"></i> Lote Analisado: {html.escape(str(lote_name))}</span>
                <h1 class="hero-title">Relatório Consolidado de Revisão Técnica Independente</h1>
                <div class="hero-meta">
                    <span><i class="fa-solid fa-clock"></i> Timestamp: <code>{html.escape(str(timestamp))}</code></span> &nbsp;|&nbsp;
                    <span><i class="fa-solid fa-calendar"></i> Data de Emissão: {html.escape(str(data_fmt))}</span>
                </div>

                <div class="parecer-badge {parecer_class}">
                    <i class="fa-solid {parecer_icon}"></i> Parecer Técnico: {html.escape(str(parecer))}
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

            <footer class="fca-footer" style="margin-top: 40px; padding: 20px 10px; border-top: 1px solid var(--border, #e2e8f0); text-align: center; font-size: 0.75rem; color: var(--text-muted, #64748b);">
                <span>Relatório gerado pelo framework corporativo <strong>FCA-ENG-001</strong> (Revisão Técnica Independente) · Repositório oficial: <a href="https://github.com/flashbsb/FCA-ENG-001" target="_blank" rel="noopener noreferrer" style="color: inherit; text-decoration: underline;">https://github.com/flashbsb/FCA-ENG-001</a></span>
            </footer>

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
                const tipoLower = cardTipo.toLowerCase();
                const catLower = cardCat.toLowerCase();
                const matchTipo = (currentTipoFilter === 'ALL')
                    || tipoLower.includes(currentTipoFilter.toLowerCase())
                    || catLower.includes(currentTipoFilter.toLowerCase())
                    || (currentTipoFilter === 'Estrutur' && (
                        tipoLower.includes('errata')
                        || catLower.includes('redacional')
                        || catLower.includes('rfc')
                        || catLower.includes('29148')
                    ));

                if (matchSearch && matchDoc && matchCat && matchAdjudication && matchCrit && matchTipo) {{
                    card.style.display = 'block';
                }} else {{
                    card.style.display = 'none';
                }}
            }});
        }}

        function copySnippet(elementId, btn) {{
            const el = document.getElementById(elementId);
            if (!el) return;
            const raw = (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') ? el.value : (el.textContent || el.innerText || '');
            const text = raw.replace(/^"|"$/g, '');
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


def compile_evolution_html(target_identifier: str, root_dir: str = None) -> dict:
    """
    Compila o painel HTML independente de Evolução e Controle de Versões da Análise (evolucao.html),
    reunindo a tabela de versionamento, o sumário executivo de alterações e o diff detalhado entre rodadas.
    Grava em analise/<lote>/<version>/evolucao.html e em <rodada>/relatorios/evolucao.html de cada rodada.
    """
    if root_dir is None:
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    analise_root = os.path.join(root_dir, 'analise')
    clean_id = (target_identifier or "").strip().replace('\\', '/').strip('/')
    if clean_id.startswith('analise/'):
        clean_id = clean_id[len('analise/'):]

    if not os.path.isdir(analise_root) or not clean_id:
        return {"status": "error", "message": "Diretório de análises ou identificador inválido."}

    def _find_run_dir(identifier: str) -> str | None:
        c = (identifier or "").strip().replace('\\', '/').strip('/')
        if c.startswith('analise/'):
            c = c[len('analise/'):]
        if not c:
            return None
        direct = os.path.join(analise_root, c)
        if os.path.isfile(os.path.join(direct, 'relatorios', 'dados_analise.json')):
            return direct
        target_leaf = c.split('/')[-1]
        for dirpath, _, filenames in os.walk(analise_root):
            if os.path.basename(dirpath) == target_leaf and os.path.isfile(os.path.join(dirpath, 'relatorios', 'dados_analise.json')):
                return dirpath
        return None

    candidate = os.path.join(analise_root, clean_id)
    version_dir = None
    lote_label = clean_id.split('/')[0]
    version_label = ""

    run_candidate = _find_run_dir(clean_id)
    if run_candidate:
        rel_run = os.path.relpath(run_candidate, analise_root).replace('\\', '/')
        parts = rel_run.split('/')
        if len(parts) >= 3:
            version_dir = os.path.dirname(run_candidate)
            lote_label = parts[0]
            version_label = parts[1]
        else:
            version_dir = run_candidate
            lote_label = parts[0]
            version_label = "v1.0"
    elif os.path.isdir(candidate):
        has_direct_runs = any(
            os.path.isfile(os.path.join(candidate, d, 'relatorios', 'dados_analise.json'))
            for d in os.listdir(candidate)
            if os.path.isdir(os.path.join(candidate, d))
        )
        if has_direct_runs:
            version_dir = candidate
            parts = clean_id.split('/')
            lote_label = parts[0]
            version_label = parts[1] if len(parts) >= 2 else "v1.0"
        else:
            sub_versions = sorted(
                os.path.join(candidate, d)
                for d in os.listdir(candidate)
                if os.path.isdir(os.path.join(candidate, d))
                and any(
                    os.path.isfile(os.path.join(candidate, d, sub, 'relatorios', 'dados_analise.json'))
                    for sub in os.listdir(os.path.join(candidate, d))
                    if os.path.isdir(os.path.join(candidate, d, sub))
                )
            )
            if sub_versions:
                version_dir = sub_versions[-1]
                lote_label = clean_id.split('/')[0]
                version_label = os.path.basename(version_dir)

    if not version_dir or not os.path.isdir(version_dir):
        return {"status": "error", "message": f"Diretório de versão não localizado para: {target_identifier}"}

    runs_by_real: dict[str, dict] = {}

    def _register_run_dir(rdir: str) -> dict | None:
        rreal = os.path.realpath(rdir)
        if rreal in runs_by_real:
            return runs_by_real[rreal]
        json_p = os.path.join(rdir, 'relatorios', 'dados_analise.json')
        if not os.path.isfile(json_p):
            return None
        try:
            with open(json_p, 'r', encoding='utf-8') as f:
                djson = json.load(f)
        except Exception:
            return None
        rel_r = os.path.relpath(rdir, analise_root).replace('\\', '/')
        leaf = os.path.basename(rdir)
        info = {
            "run_dir": rdir,
            "rel_dir": os.path.join(rdir, 'relatorios'),
            "index_abs": os.path.join(rdir, 'relatorios', 'index.html'),
            "rel_from_analise": rel_r,
            "leaf": leaf,
            "data": djson,
        }
        runs_by_real[rreal] = info
        return info

    if os.path.isfile(os.path.join(version_dir, 'relatorios', 'dados_analise.json')):
        _register_run_dir(version_dir)
    else:
        for entry in sorted(os.listdir(version_dir)):
            sub_dir = os.path.join(version_dir, entry)
            if os.path.isdir(sub_dir):
                _register_run_dir(sub_dir)

    # Inclui análises ancestrais referenciadas (mesmo se em caminho legado de 1 nível)
    pending_parents = list(runs_by_real.values())
    while pending_parents:
        cur = pending_parents.pop(0)
        djson = cur["data"]
        ancestors = []
        if djson.get("parent_analysis"):
            ancestors.append(str(djson["parent_analysis"]))
        vr_meta = djson.get("version_reconciliation")
        if isinstance(vr_meta, dict) and vr_meta.get("versao_anterior"):
            ancestors.append(str(vr_meta["versao_anterior"]))
        for anc_id in ancestors:
            anc_dir = _find_run_dir(anc_id)
            if anc_dir and os.path.realpath(anc_dir) not in runs_by_real:
                loaded = _register_run_dir(anc_dir)
                if loaded:
                    pending_parents.append(loaded)

    runs = sorted(runs_by_real.values(), key=lambda r: (r["leaf"], r["rel_from_analise"]))
    if not runs:
        return {"status": "error", "message": "Nenhuma análise encontrada para compilar evolução."}

    import audit_engine
    latest_run = runs[-1]
    latest_data = latest_run["data"]
    if not version_label:
        version_label = str(latest_data.get("metadata", {}).get("versao_documento") or "v1.0")
    display_title = clean_unicode_text(str(latest_data.get("title") or lote_label.replace("_", " ")))

    # Garante reconciliação entre a penúltima e a última versão se houver >= 2 rodadas
    latest_vr = latest_data.get("version_reconciliation")
    if (not isinstance(latest_vr, dict) or not latest_vr) and len(runs) >= 2:
        latest_vr = audit_engine.reconcile_versions(runs[-2]["data"], latest_data)

    # Coleta todas as reconciliações disponíveis em ordem cronológica (mais recente no topo)
    reconciliations_seq = []
    for idx in range(len(runs) - 1, 0, -1):
        r_curr = runs[idx]
        r_prev = runs[idx - 1]
        vr_item = r_curr["data"].get("version_reconciliation")
        if isinstance(vr_item, dict) and vr_item:
            reconciliations_seq.append((idx, idx + 1, r_prev, r_curr, vr_item))
        elif idx == len(runs) - 1 and isinstance(latest_vr, dict) and latest_vr:
            reconciliations_seq.append((idx, idx + 1, r_prev, r_curr, latest_vr))

    def _fmt_ts_date(ts_str: str) -> str:
        leaf = (ts_str or "").split("/")[-1]
        if len(leaf) >= 15 and leaf[:8].isdigit() and leaf[9:15].isdigit():
            return f"{leaf[6:8]}/{leaf[4:6]}/{leaf[:4]} {leaf[9:11]}:{leaf[11:13]}:{leaf[13:15]}"
        if len(leaf) >= 8 and leaf[:8].isdigit():
            return f"{leaf[6:8]}/{leaf[4:6]}/{leaf[:4]}"
        return ts_str or "—"

    def _parecer_badge_html(parecer_txt: str) -> str:
        up = (parecer_txt or "").upper()
        if "NÃO APTO" in up:
            cls = "crit-critica"
        elif "PENDENTE" in up:
            cls = "crit-alta"
        elif "RESSALVA" in up:
            cls = "crit-media"
        else:
            cls = "crit-baixa"
        return f'<span class="badge-crit {cls}">{html.escape(str(parecer_txt or "—"))}</span>'

    def _crit_badge_html(crit_txt: str) -> str:
        low = (crit_txt or "").casefold()
        cls = (
            "crit-critica" if "crítica" in low or "critica" in low
            else "crit-alta" if "alta" in low
            else "crit-media" if "média" in low or "media" in low
            else "crit-baixa"
        )
        return f'<span class="badge-crit {cls}">{html.escape(str(crit_txt or "Média"))}</span>'

    def _render_evolution_for_dir(output_dir: str) -> str:
        try:
            master_href = os.path.relpath(os.path.join(analise_root, "index.html"), output_dir).replace("\\", "/")
        except Exception:
            master_href = "../../index.html"
        try:
            latest_report_href = os.path.relpath(latest_run["index_abs"], output_dir).replace("\\", "/")
        except Exception:
            latest_report_href = "./index.html"

        # Seção 1: Tabela Master de Versionamento das Análises
        version_rows_html = ""
        for idx, run in enumerate(runs, 1):
            d = run["data"]
            k = d.get("kpis") or {}
            confirmed_list = _confirmed_findings(d.get("findings") or [])
            pendentes_n = int(k.get("achados_pendentes_adjudicacao", 0) or 0)
            confirmados_n = int(k.get("achados_confirmados", len(confirmed_list)) or 0)
            criticos_n = int(k.get("criticos", sum(1 for a in confirmed_list if str(a.get("criticidade", a.get("crit", ""))).casefold() in ("crítica", "critica"))) or 0)
            altos_n = int(k.get("altos", sum(1 for a in confirmed_list if str(a.get("criticidade", a.get("crit", ""))).casefold() == "alta")) or 0)
            lacunas_n = int(k.get("lacunas", len(d.get("lacunas") or [])) or 0)
            perguntas_n = int(k.get("perguntas", len(d.get("esclarecimentos") or [])) or 0)
            iqd_val = str(k.get("iqd", "—"))
            parecer_val = str(d.get("parecer", "—"))

            trail = d.get("audit_trail") or []
            if idx == 1 and not trail:
                origem_motivo = "Auditoria Inicial RTI (Baseline)"
            elif trail and isinstance(trail[-1], dict):
                origem_motivo = str(trail[-1].get("reason") or "Revisão Adjudicada")
            else:
                origem_motivo = "Rodada Evolutiva da Análise"

            ext_inps = d.get("external_inputs") or []
            if ext_inps:
                ext_names = ", ".join(str(ei.get("name", "")) for ei in ext_inps[:2])
                origem_motivo += f" (Insumo externo verificado: {ext_names})"

            bfiles = d.get("baseline_files") or []
            target_names = [
                str(bf.get("name") or os.path.basename(str(bf.get("path", ""))))
                for bf in bfiles
                if bf.get("role", "alvo_principal") == "alvo_principal"
            ] or [str(bf.get("name") or "") for bf in bfiles]
            alvo_disp = ", ".join(target_names[:2]) if target_names else "—"
            if len(target_names) > 2:
                alvo_disp += f" (+{len(target_names) - 2})"

            try:
                run_href = os.path.relpath(run["index_abs"], output_dir).replace("\\", "/")
            except Exception:
                run_href = "./index.html"

            rev_badge_style = "background:#dbeafe; color:#1e40af;" if idx == len(runs) else "background:#f1f5f9; color:#334155;"
            current_tag = " (Atual)" if idx == len(runs) else ""

            version_rows_html += f"""
            <tr>
                <td><span class="badge-crit" style="{rev_badge_style}"><strong>r{idx}{current_tag}</strong></span></td>
                <td><code>{html.escape(run['leaf'])}</code><br><small style="color:var(--text-muted);">{html.escape(_fmt_ts_date(run['leaf']))}</small></td>
                <td>{html.escape(origem_motivo)}</td>
                <td><code>{html.escape(alvo_disp)}</code></td>
                <td>{_parecer_badge_html(parecer_val)}</td>
                <td><strong style="color:var(--primary);">{html.escape(iqd_val)}</strong></td>
                <td><strong>{confirmados_n}</strong>{' <small>(pend: ' + str(pendentes_n) + ')</small>' if pendentes_n else ''}</td>
                <td><strong style="color:var(--danger);">{criticos_n}</strong></td>
                <td><strong style="color:var(--warning);">{altos_n}</strong></td>
                <td>{lacunas_n}</td>
                <td>{perguntas_n}</td>
                <td><a href="{html.escape(run_href, quote=True)}" class="ssot-link"><i class="fa-solid fa-arrow-right-to-bracket"></i> Abrir Relatório</a></td>
            </tr>"""

        # Hero metrics
        latest_kpis = latest_data.get("kpis") or {}
        hero_iqd = html.escape(str(latest_kpis.get("iqd", "—")))
        hero_parecer = str(latest_data.get("parecer", "—"))
        hero_delta = html.escape(str((latest_vr or {}).get("delta_iqd", "—")))
        hero_novos = int((latest_vr or {}).get("novos_achados_count", 0))
        hero_refinados = int((latest_vr or {}).get("achados_refinados_count", len((latest_vr or {}).get("refinados", []))))
        hero_sanados = int((latest_vr or {}).get("achados_sanados_count", 0))

        # Seção 2 & 3: Sumário Executivo das Alterações e Diff Estruturado
        transitions_html = ""
        for prev_num, curr_num, r_prev, r_curr, vr in reconciliations_seq:
            try:
                curr_href = os.path.relpath(r_curr["index_abs"], output_dir).replace("\\", "/")
            except Exception:
                curr_href = latest_report_href

            sumario_txt = html.escape(str(vr.get("sumario_alteracoes") or ""))
            if not sumario_txt:
                sumario_txt = html.escape(
                    f"Comparação entre r{prev_num} e r{curr_num}: "
                    f"{vr.get('novos_achados_count', 0)} novo(s) achado(s), "
                    f"{vr.get('achados_refinados_count', 0)} refinado(s)/reancorado(s), "
                    f"{vr.get('achados_sanados_count', 0)} saneado(s)/expurgado(s) e "
                    f"variação de IQD {vr.get('delta_iqd', '—')}."
                )

            kcmp = vr.get("kpi_comparison") or {}
            kpi_delta_rows = ""
            if isinstance(kcmp, dict) and kcmp:
                labels_map = [
                    ("confirmados", "Achados Confirmados"),
                    ("criticos", "Achados Críticos (P0)"),
                    ("altos", "Achados Altos (P1)"),
                    ("lacunas", "Lacunas Mapeadas"),
                    ("perguntas", "Perguntas Formais (Q-XXX)"),
                    ("iqd", "Índice IQD"),
                ]
                for key_k, lbl_k in labels_map:
                    row_k = kcmp.get(key_k)
                    if isinstance(row_k, dict):
                        kpi_delta_rows += (
                            f"<tr><td><strong>{lbl_k}</strong></td>"
                            f"<td>{html.escape(str(row_k.get('anterior', '—')))}</td>"
                            f"<td><strong>{html.escape(str(row_k.get('atual', '—')))}</strong></td>"
                            f"<td><code>{html.escape(str(row_k.get('delta', '—')))}</code></td></tr>"
                        )
            else:
                kpi_delta_rows = (
                    f"<tr><td><strong>Total de Achados Ativos</strong></td><td>{vr.get('total_anteriores', 0)}</td><td><strong>{vr.get('total_atuais', 0)}</strong></td><td>—</td></tr>"
                    f"<tr><td><strong>Índice IQD</strong></td><td>{html.escape(str(vr.get('iqd_anterior', '—')))}</td><td><strong>{html.escape(str(vr.get('iqd_atual', '—')))}</strong></td><td><code>{html.escape(str(vr.get('delta_iqd', '—')))}</code></td></tr>"
                )

            # Tabelas de mudanças detalhadas
            novos_rows = ""
            for item in vr.get("novos", []):
                nid_raw = str(item.get("id_atual", "—"))
                nid_esc = html.escape(nid_raw)
                n_link = (
                    f'<a href="{html.escape(curr_href, quote=True)}#card-{html.escape(nid_raw, quote=True)}" class="ssot-link">{nid_esc}</a>'
                    if nid_raw != "—" else "—"
                )
                novos_rows += (
                    f"<tr><td>{n_link}</td>"
                    f"<td><strong>{html.escape(str(item.get('title') or item.get('titulo') or '—'))}</strong></td>"
                    f"<td><code>{html.escape(str(item.get('doc_origem', '—')))}</code></td>"
                    f"<td>{html.escape(str(item.get('loc') or item.get('localizacao') or '—'))}</td>"
                    f"<td>{_crit_badge_html(item.get('criticidade', 'Média'))} <span class='badge-prio'>{html.escape(str(item.get('prioridade', 'P2')))}</span></td>"
                    f"<td>{html.escape(str(item.get('evidencia', '—')))}</td></tr>"
                )

            ref_rows = ""
            for item in vr.get("refinados", []):
                rid_raw = str(item.get("id_atual", "—"))
                rid_esc = html.escape(rid_raw)
                r_link = (
                    f'<a href="{html.escape(curr_href, quote=True)}#card-{html.escape(rid_raw, quote=True)}" class="ssot-link">{rid_esc}</a>'
                    if rid_raw != "—" else "—"
                )
                doc_trans = f"{item.get('doc_anterior', '—')} → {item.get('doc_atual', item.get('doc_origem', '—'))}"
                ref_rows += (
                    f"<tr><td>{r_link}</td>"
                    f"<td><strong>{html.escape(str(item.get('title') or item.get('titulo') or '—'))}</strong></td>"
                    f"<td><code>{html.escape(doc_trans)}</code></td>"
                    f"<td>{html.escape(str(item.get('detalhe_refinamento') or 'Refinamento de evidência'))}</td>"
                    f"<td>{_crit_badge_html(item.get('criticidade', 'Média'))}</td></tr>"
                )

            san_items = vr.get("expurgados_escopo") or []
            san_ids_seen = {item.get("id_anterior") for item in san_items}
            combined_removed = list(san_items) + [item for item in vr.get("sanados", []) if item.get("id_anterior") not in san_ids_seen]
            rem_rows = ""
            for item in combined_removed:
                motivo_raw = item.get("justificativa") or (
                    "Expurgado por foco de escopo (documento de apoio)" if item.get("motivo_saida") == "expurgado_escopo"
                    else "Saneado / não presente na versão atual"
                )
                rem_rows += (
                    f"<tr><td><code>{html.escape(str(item.get('id_anterior', '—')))}</code></td>"
                    f"<td>{html.escape(str(item.get('title') or item.get('titulo') or '—'))}</td>"
                    f"<td><code>{html.escape(str(item.get('doc_origem', '—')))}</code></td>"
                    f"<td>{_crit_badge_html(item.get('criticidade', 'Média'))}</td>"
                    f"<td>{html.escape(str(motivo_raw))}</td></tr>"
                )

            pers_items = [item for item in vr.get("reincidentes", []) if not item.get("foi_refinado")]
            pers_rows = ""
            for item in pers_items:
                pid_ant = html.escape(str(item.get("id_anterior", "—")))
                pid_atu_raw = str(item.get("id_atual", "—"))
                p_link = (
                    f'<a href="{html.escape(curr_href, quote=True)}#card-{html.escape(pid_atu_raw, quote=True)}" class="ssot-link">{html.escape(pid_atu_raw)}</a>'
                    if pid_atu_raw != "—" else "—"
                )
                pers_rows += (
                    f"<tr><td><code>{pid_ant}</code> → {p_link}</td>"
                    f"<td>{html.escape(str(item.get('title') or item.get('titulo') or '—'))}</td>"
                    f"<td>{_crit_badge_html(item.get('criticidade', 'Média'))}</td>"
                    f"<td>{html.escape(str(item.get('loc_atual') or item.get('localizacao_atual') or '—'))}</td></tr>"
                )

            # Seção 4 opcional: Disposição de Insumos Externos
            ext_disp_html = ""
            ext_disp = vr.get("rastreabilidade_insumos_externos") or []
            if ext_disp:
                ext_d_rows = ""
                for ed in ext_disp:
                    ed_item = html.escape(str(ed.get("item_externo") or ed.get("codigo") or "—"))
                    ed_tema = html.escape(str(ed.get("tema") or ed.get("titulo") or "—"))
                    ed_status_raw = str(ed.get("status") or "Verificado")
                    ed_st_cf = ed_status_raw.casefold()
                    ed_cls = (
                        "crit-baixa" if "incorporad" in ed_st_cf
                        else "crit-media" if "cobert" in ed_st_cf or "enriquec" in ed_st_cf
                        else "crit-critica" if "descart" in ed_st_cf or "rejeit" in ed_st_cf or "não" in ed_st_cf
                        else "crit-info"
                    )
                    fid_ref = str(ed.get("achado_id") or "").strip()
                    fid_cell = (
                        f'<a href="{html.escape(curr_href, quote=True)}#card-{html.escape(fid_ref, quote=True)}" class="ssot-link">{html.escape(fid_ref)}</a>'
                        if fid_ref and fid_ref != "—" else "—"
                    )
                    ed_just = html.escape(str(ed.get("justificativa") or "—"))
                    ext_d_rows += (
                        f"<tr><td><code>{ed_item}</code></td><td>{ed_tema}</td>"
                        f"<td><span class='badge-crit {ed_cls}'>{html.escape(ed_status_raw)}</span></td>"
                        f"<td>{fid_cell}</td><td>{ed_just}</td></tr>"
                    )
                ext_disp_html = f"""
                <section class="section-card" id="insumos-externos-r{curr_num}">
                    <div class="section-header">
                        <div class="section-icon"><i class="fa-solid fa-magnifying-glass"></i></div>
                        <h2 class="section-title">Auditoria Cruzada de Insumos Externos (r{prev_num} → r{curr_num})</h2>
                    </div>
                    <div class="ssot-intro-note">
                        <i class="fa-solid fa-triangle-exclamation"></i> <strong>Regra de Custódia:</strong> Relatórios complementares externos não constituem fonte de verdade. Cada apontamento externo abaixo foi confrontado diretamente contra a baseline normativa congelada antes de qualquer decisão.
                    </div>
                    <div class="table-responsive">
                        <table class="rpt-table">
                            <thead>
                                <tr>
                                    <th>Item Externo</th>
                                    <th>Tema / Hipótese Verificada</th>
                                    <th>Decisão FCA-ENG-001</th>
                                    <th>Achado Vinculado</th>
                                    <th>Evidência na Baseline / Justificativa</th>
                                </tr>
                            </thead>
                            <tbody>{ext_d_rows}</tbody>
                        </table>
                    </div>
                </section>"""

            transitions_html += f"""
            <section class="section-card" id="sumario-r{prev_num}-r{curr_num}">
                <div class="section-header">
                    <div class="section-icon"><i class="fa-solid fa-code-compare"></i></div>
                    <h2 class="section-title">Sumário Executivo de Alterações: r{prev_num} → r{curr_num}</h2>
                </div>
                <div class="ssot-intro-note">
                    <strong>Resumo das Mudanças Incorporadas:</strong> {sumario_txt}
                </div>
                <div class="table-responsive">
                    <table class="rpt-table">
                        <thead>
                            <tr>
                                <th>Indicador</th>
                                <th>Versão Anterior (r{prev_num})</th>
                                <th>Nova Versão (r{curr_num})</th>
                                <th>Variação (Δ)</th>
                            </tr>
                        </thead>
                        <tbody>{kpi_delta_rows}</tbody>
                    </table>
                </div>
            </section>

            <section class="section-card" id="diff-r{prev_num}-r{curr_num}">
                <div class="section-header">
                    <div class="section-icon"><i class="fa-solid fa-table-list"></i></div>
                    <h2 class="section-title">Detalhamento das Alterações Incorporadas (r{prev_num} → r{curr_num})</h2>
                </div>

                <h3 style="margin-top:10px; color:#047857;">🟢 Novos Achados Incorporados na Versão r{curr_num} ({len(vr.get('novos', []))})</h3>
                <div class="table-responsive">
                    <table class="rpt-table">
                        <thead>
                            <tr><th>ID</th><th>Título</th><th>Documento-Alvo</th><th>Localização</th><th>Severidade</th><th>Evidência</th></tr>
                        </thead>
                        <tbody>{novos_rows or '<tr><td colspan="6">Nenhum novo achado adicionado nesta transição.</td></tr>'}</tbody>
                    </table>
                </div>

                <h3 style="margin-top:26px; color:#1d4ed8;">🔵 Achados Refinados ou Reancorados no Documento-Alvo ({len(vr.get('refinados', []))})</h3>
                <div class="table-responsive">
                    <table class="rpt-table">
                        <thead>
                            <tr><th>ID</th><th>Título</th><th>Transição de Escopo</th><th>O que foi Ajustado</th><th>Criticidade</th></tr>
                        </thead>
                        <tbody>{ref_rows or '<tr><td colspan="5">Nenhum achado refinado/reancorado nesta transição.</td></tr>'}</tbody>
                    </table>
                </div>

                <h3 style="margin-top:26px; color:#b45309;">🧹 Achados Saneados ou Expurgados por Foco de Escopo ({len(combined_removed)})</h3>
                <div class="table-responsive">
                    <table class="rpt-table">
                        <thead>
                            <tr><th>ID Anterior</th><th>Título</th><th>Documento Anterior</th><th>Criticidade</th><th>Motivo / Justificativa</th></tr>
                        </thead>
                        <tbody>{rem_rows or '<tr><td colspan="5">Nenhum achado removido nesta transição.</td></tr>'}</tbody>
                    </table>
                </div>

                <details style="margin-top:24px;">
                    <summary style="cursor:pointer; font-weight:700; color:var(--secondary);">🟡 Achados Persistentes Mantidos Inalterados ({len(pers_items)})</summary>
                    <div class="table-responsive" style="margin-top:10px;">
                        <table class="rpt-table">
                            <thead><tr><th>ID Anterior → ID Atual</th><th>Título</th><th>Criticidade</th><th>Localização</th></tr></thead>
                            <tbody>{pers_rows or '<tr><td colspan="4">Nenhum achado persistente inalterado nesta transição.</td></tr>'}</tbody>
                        </table>
                    </div>
                </details>
            </section>
            {ext_disp_html}"""

        if not transitions_html:
            transitions_html = """
            <section class="section-card" id="sumario-unico">
                <div class="section-header">
                    <div class="section-icon"><i class="fa-solid fa-code-compare"></i></div>
                    <h2 class="section-title">Sumário de Versionamento</h2>
                </div>
                <div class="ssot-intro-note">
                    Esta versão do lote possui atualmente uma única rodada registrada. Novas rodadas ou reconciliações aparecerão comparadas automaticamente aqui.
                </div>
            </section>"""

        return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Evolução de Versões — {html.escape(display_title)}</title>
    <style>
        :root {{
            --primary: #005ca9;
            --primary-dark: #004077;
            --primary-light: #e6f0fa;
            --secondary: #0f172a;
            --accent: #f59e0b;
            --danger: #ef4444;
            --warning: #f59e0b;
            --success: #10b981;
            --bg-body: #f8fafc;
            --bg-card: #ffffff;
            --text-main: #1e293b;
            --text-muted: #64748b;
            --border: #e2e8f0;
            --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
            --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.07), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg-body); color: var(--text-main); line-height: 1.65; font-size: 14px; }}
        h1, h2, h3, h4 {{ font-family: 'Outfit', 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: var(--secondary); font-weight: 700; }}
        .fa-solid {{ display: inline-block; font-style: normal; line-height: 1; vertical-align: middle; }}
        .fa-shield-halved::before {{ content: "🛡"; }}
        .fa-house::before {{ content: "🏠"; }}
        .fa-print::before {{ content: "⎙"; }}
        .fa-code-compare::before {{ content: "⇄"; }}
        .fa-chart-column::before {{ content: "📊"; }}
        .fa-table-list::before {{ content: "▦"; }}
        .fa-arrow-right-to-bracket::before {{ content: "→"; }}
        .fa-magnifying-glass::before {{ content: "🔍"; }}
        .fa-triangle-exclamation::before {{ content: "⚠"; }}
        .fa-folder-open::before {{ content: "📁"; }}
        .top-navbar {{ position: sticky; top: 0; z-index: 1000; background: rgba(15, 23, 42, 0.96); color: #ffffff; padding: 12px 24px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 10px rgba(0,0,0,0.15); }}
        .brand-title {{ display: flex; align-items: center; gap: 12px; font-size: 1.05rem; font-weight: 700; }}
        .actions-group {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
        .btn-action {{ background: var(--primary); color: #ffffff; border: none; padding: 8px 14px; border-radius: 6px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 8px; font-size: 0.85rem; text-decoration: none; }}
        .btn-print {{ background: #059669; }}
        .wrap {{ max-width: 1440px; margin: 0 auto; padding: 24px; display: flex; flex-direction: column; gap: 24px; }}
        .hero-card {{ background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: #ffffff; border-radius: 16px; padding: 28px; box-shadow: var(--shadow-lg); }}
        .hero-tag {{ display: inline-block; background: rgba(167, 139, 250, 0.2); color: #c4b5fd; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; margin-bottom: 8px; border: 1px solid rgba(167, 139, 250, 0.35); }}
        .hero-title {{ color: #ffffff; font-size: 1.7rem; margin-bottom: 6px; }}
        .hero-meta {{ color: #94a3b8; font-size: 0.9rem; margin-bottom: 18px; }}
        .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-top: 16px; }}
        .metric-card {{ background: rgba(255, 255, 255, 0.06); border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 12px; padding: 14px; }}
        .metric-label {{ font-size: 0.75rem; color: #94a3b8; text-transform: uppercase; font-weight: 600; }}
        .metric-val {{ font-size: 1.4rem; font-weight: 800; color: #ffffff; }}
        .metric-val.green {{ color: #34d399; }}
        .metric-val.amber {{ color: #fbbf24; }}
        .metric-val.red {{ color: #f87171; }}
        .section-card {{ background: var(--bg-card); border-radius: 16px; padding: 24px; border: 1px solid var(--border); box-shadow: var(--shadow); }}
        .section-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 18px; padding-bottom: 10px; border-bottom: 2px solid var(--primary-light); }}
        .section-icon {{ width: 36px; height: 36px; background: var(--primary-light); color: var(--primary); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 1.1rem; }}
        .section-title {{ font-size: 1.25rem; color: var(--secondary); margin: 0; }}
        .ssot-intro-note {{ background: #e0f2fe; color: #0369a1; border: 1px solid #7dd3fc; padding: 10px 14px; border-radius: 8px; font-size: 0.88rem; margin-bottom: 14px; }}
        .ssot-link {{ color: var(--primary); font-weight: 700; text-decoration: none; background: var(--primary-light); padding: 3px 8px; border-radius: 4px; display: inline-flex; align-items: center; gap: 4px; }}
        .ssot-link:hover {{ background: var(--primary); color: #ffffff; }}
        .table-responsive {{ overflow-x: auto; margin-top: 10px; }}
        .rpt-table {{ width: 100%; border-collapse: collapse; font-size: 0.83rem; }}
        .rpt-table th, .rpt-table td {{ padding: 8px 12px; border: 1px solid var(--border); text-align: left; vertical-align: top; }}
        .rpt-table th {{ background: #f1f5f9; font-weight: 700; color: var(--secondary); }}
        .rpt-table tr:nth-child(even) {{ background: #f8fafc; }}
        .badge-crit {{ font-size: 0.72rem; font-weight: 700; padding: 3px 8px; border-radius: 6px; text-transform: uppercase; display: inline-block; }}
        .crit-critica {{ background: #fee2e2; color: #b91c1c; }}
        .crit-alta {{ background: #ffedd5; color: #c2410c; }}
        .crit-media {{ background: #fef9c3; color: #a16207; }}
        .crit-baixa {{ background: #dcfce7; color: #15803d; }}
        .crit-info {{ background: #e0f2fe; color: #0369a1; }}
        .badge-prio {{ background: #e2e8f0; color: #334155; padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: 700; }}
        @media print {{ .top-navbar {{ display: none !important; }} .wrap {{ padding: 0; max-width: 100%; }} }}
    </style>
</head>
<body>
    <header class="top-navbar">
        <div class="brand-title">
            <i class="fa-solid fa-code-compare"></i>
            <span>FCA-ENG-001 · Evolução e Controle de Versões da Análise</span>
        </div>
        <div class="actions-group">
            <a href="{html.escape(latest_report_href, quote=True)}" class="btn-action" style="background:#7c3aed;"><i class="fa-solid fa-chart-column"></i> Relatório Técnico Atual (r{len(runs)})</a>
            <a href="{html.escape(master_href, quote=True)}" class="btn-action"><i class="fa-solid fa-house"></i> Central Master</a>
            <button class="btn-action btn-print" onclick="window.print()"><i class="fa-solid fa-print"></i> Imprimir / PDF</button>
        </div>
    </header>

    <main class="wrap">
        <section class="hero-card">
            <span class="hero-tag"><i class="fa-solid fa-folder-open"></i> Controle de Versionamento Independente · {html.escape(str(lote_label))}</span>
            <h1 class="hero-title">Evolução das Análises Técnicas ({html.escape(str(version_label))})</h1>
            <div class="hero-meta">
                <span>Lote: <strong>{html.escape(display_title)}</strong></span> &nbsp;|&nbsp;
                <span>Versão Documental: <code>{html.escape(str(version_label))}</code></span> &nbsp;|&nbsp;
                <span>Parecer Atual (r{len(runs)}): <strong>{html.escape(hero_parecer)}</strong></span>
            </div>
            <div class="metrics-grid">
                <div class="metric-card"><div class="metric-label">Versões da Análise</div><div class="metric-val">{len(runs)}</div></div>
                <div class="metric-card"><div class="metric-label">IQD Atual</div><div class="metric-val green">{hero_iqd}</div></div>
                <div class="metric-card"><div class="metric-label">Variação IQD (Δ)</div><div class="metric-val">{hero_delta}</div></div>
                <div class="metric-card"><div class="metric-label">Novos Achados</div><div class="metric-val red">{hero_novos}</div></div>
                <div class="metric-card"><div class="metric-label">Refinados / Reancorados</div><div class="metric-val amber">{hero_refinados}</div></div>
                <div class="metric-card"><div class="metric-label">Saneados / Expurgados</div><div class="metric-val">{hero_sanados}</div></div>
            </div>
        </section>

        <section class="section-card" id="tabela-versionamento">
            <div class="section-header">
                <div class="section-icon"><i class="fa-solid fa-table-list"></i></div>
                <h2 class="section-title">Tabela Master de Versionamento das Análises</h2>
            </div>
            <div class="table-responsive">
                <table class="rpt-table">
                    <thead>
                        <tr>
                            <th>Versão</th>
                            <th>Timestamp / Data</th>
                            <th>Origem / Motivo da Versão</th>
                            <th>Documento-Alvo Principal</th>
                            <th>Parecer</th>
                            <th>IQD</th>
                            <th>Confirmados</th>
                            <th>P0 / Críticos</th>
                            <th>P1 / Altos</th>
                            <th>Lacunas</th>
                            <th>Perguntas</th>
                            <th>Relatório</th>
                        </tr>
                    </thead>
                    <tbody>{version_rows_html}</tbody>
                </table>
            </div>
        </section>

        {transitions_html}

        <footer class="fca-footer" style="margin-top: 40px; padding: 20px 10px; border-top: 1px solid var(--border, #e2e8f0); text-align: center; font-size: 0.75rem; color: var(--text-muted, #64748b);">
            <span>Relatório evolutivo gerado pelo framework corporativo <strong>FCA-ENG-001</strong> (Revisão Técnica Independente) · Repositório oficial: <a href="https://github.com/flashbsb/FCA-ENG-001" target="_blank" rel="noopener noreferrer" style="color: inherit; text-decoration: underline;">https://github.com/flashbsb/FCA-ENG-001</a></span>
        </footer>
    </main>
</body>
</html>"""

    written_run_files = []
    version_evo_rel = None
    if os.path.realpath(version_dir) != os.path.realpath(analise_root) and not os.path.isfile(os.path.join(version_dir, 'relatorios', 'dados_analise.json')):
        version_evo_abs = os.path.join(version_dir, "evolucao.html")
        with open(version_evo_abs, "w", encoding="utf-8") as f:
            f.write(_render_evolution_for_dir(version_dir))
        version_evo_rel = os.path.relpath(version_evo_abs, analise_root).replace("\\", "/")

    for run in runs:
        r_dir = run["rel_dir"]
        if os.path.isdir(r_dir):
            run_evo_abs = os.path.join(r_dir, "evolucao.html")
            with open(run_evo_abs, "w", encoding="utf-8") as f:
                f.write(_render_evolution_for_dir(r_dir))
            run_evo_rel = os.path.relpath(run_evo_abs, analise_root).replace("\\", "/")
            written_run_files.append(run_evo_rel)
            if version_evo_rel is None:
                version_evo_rel = run_evo_rel

    return {
        "status": "success",
        "version_dir": os.path.relpath(version_dir, analise_root).replace("\\", "/"),
        "evolution_html": version_evo_rel,
        "run_evolution_files": written_run_files,
        "total_versions": len(runs),
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        ts = sys.argv[1]
        print(compile_timestamp_html(ts))
    else:
        print("Uso: python3 html_compiler.py <timestamp>")
