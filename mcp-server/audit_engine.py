#!/usr/bin/env python3
"""
Motor de Geração de Relatórios RTI — FCA-ENG-001 v2.0
Gera 6 relatórios Markdown com conteúdo DISTINTO (sem cópias) a partir dos dados dos achados.
Calcula IQD dinamicamente. Nenhum valor hardcoded.
"""

import os
import re
import math
import json
import schemas
from audit_pipeline import sanitize_batch_isolation, clean_unicode_text


def compute_checklist_denominator(root_dir: str, active_checklists: list[str], num_files: int = 1) -> int:
    """Calcula o denominador do IQD a partir dos itens aplicáveis dos checklists ativos."""
    total_items = 0
    sep_rx = re.compile(r"^\|(?:\s*:?-+:?\s*\|)+\s*$")
    for chk in active_checklists or []:
        chk_path = os.path.join(root_dir, "framework", "checklists", str(chk)) if root_dir else ""
        if not chk_path or not os.path.isfile(chk_path):
            continue
        try:
            with open(chk_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.read().splitlines()
        except Exception:
            continue
        for idx, raw in enumerate(lines):
            stripped = raw.strip()
            if not stripped.startswith("|") or sep_rx.match(stripped):
                continue
            if idx + 1 < len(lines) and sep_rx.match(lines[idx + 1].strip()):
                continue
            total_items += 1
    if total_items > 0:
        return max(total_items, max(num_files, 1) * 10, 30)
    return max(max(num_files, 1) * 15, 30)



def calculate_iqd(achados: list, total_verificaveis: int = None) -> tuple:
    """
    Calcula o IQD real com base nos achados.
    IQD = 100 × (itens conformes verificáveis / itens aplicáveis verificados)
    Retorna (valor_float, string_formatada, denominador_usado)
    """
    if not achados and (total_verificaveis is None or total_verificaveis == 0):
        return 100.0, "100.0%", 0

    # Conta achados por criticidade (impactam o IQD negativamente)
    pesos = {"Crítica": 4, "Alta": 3, "Média": 2, "Baixa": 1, "Informativa": 0}
    impacto_total = sum(pesos.get(a.get('crit') or a.get('criticidade', 'Média'), 2) for a in achados)

    # Denominador: total de itens verificáveis (estimado se não fornecido)
    denom = total_verificaveis if total_verificaveis and total_verificaveis > 0 else max(len(achados) * 5, 20)

    # Máximo impacto possível (todos críticos)
    max_impacto = denom * pesos["Crítica"]

    if max_impacto == 0:
        return 100.0, "100.0%", denom

    iqd_val = max(0.0, 100.0 * (1.0 - (impacto_total / max_impacto)))
    iqd_val = round(iqd_val, 1)
    return iqd_val, f"{iqd_val}%", denom


def calculate_parecer(achados: list, lacunas: list) -> tuple:
    """
    Calcula o parecer RTI conforme Seção 24 do FCA-ENG-001.
    Retorna (parecer_extenso, parecer_badge)
    """
    criticos_p0 = [a for a in achados
                   if (a.get('crit') or a.get('criticidade', '')).upper() == 'CRÍTICA'
                   and (a.get('prio') or a.get('prioridade', '')).upper() == 'P0']

    if criticos_p0:
        return "NÃO APTO PARA DECISÃO", "NÃO APTO"

    if achados or lacunas:
        return "APTO COM RESSALVAS", "APTO COM RESSALVAS"

    return "APTO PARA DECISÃO", "APTO"


def _safe(val: any, fallback: str = "não disponível") -> str:
    """Retorna o valor como string ou o fallback se vazio."""
    s = str(val).strip() if val is not None else ""
    return s if s and s.lower() not in ("none", "null", "") else fallback


def generate_6_reports(rel_dir: str, data: dict) -> str:
    """
    Gera a base de dados estruturada SSOT (dados_analise.json) da RTI em rel_dir.
    Nota: A partir da v2.1 (Fase 1), relatórios em formato Markdown (.md) foram descontinuados.
    Toda a entrega é realizada exclusivamente via dados_analise.json e compilada em index.html.
    """
    os.makedirs(rel_dir, exist_ok=True)
    
    # Aplica o isolamento por lote em todo o dicionário de dados
    data = sanitize_batch_isolation(data)

    title = _safe(data.get("title"), "Revisão Técnica Independente")
    timestamp = _safe(data.get("timestamp"), "—")
    baseline_files = data.get("baseline_files", [])
    achados = data.get("achados", [])
    lacunas = data.get("lacunas", [])
    riscos = data.get("riscos", [])
    redacoes = data.get("redacoes", [])
    erratas = data.get("erratas", [])
    esclarecimentos = data.get("esclarecimentos", [])
    checklists_status = data.get("checklists_status", {})
    skills_ativas = data.get("skills_ativas", ["analisar-documento"])
    iqd_denominador = data.get("iqd_denominador", 0)

    # Garante IDs sequenciais nos esclarecimentos
    for idx, esc in enumerate(esclarecimentos, 1):
        if not esc.get('id') or esc['id'] == "não disponível":
            esc['id'] = f"Q-{idx:03d}"

    # ──────────────────────────────────────────────────
    # Normalização dos Achados e Estrutura dos Dados
    # ──────────────────────────────────────────────────
    normalized_findings = []
    for a in achados:
        de_txt = _safe(a.get("de", a.get("texto_atual", "")), "")
        para_txt = _safe(a.get("para", a.get("texto_sugerido", "")), "")
        tipo_str = _safe(a.get("tipo", "Erro Técnico"))
        is_dir = bool(de_txt or para_txt or "→" in tipo_str or "grafia" in tipo_str.lower() or "sequência" in tipo_str.lower())
        item = {
            "id": a.get("id", "ACH-000"),
            "title": _safe(a.get("title", a.get("titulo", ""))),
            "doc_origem": _safe(a.get("doc_origem", a.get("documento", ""))),
            "loc": _safe(a.get("loc", a.get("localizacao", ""))),
            "categoria": _safe(a.get("cat", a.get("categoria", "Geral"))),
            "tipo": tipo_str,
            "evidencia": _safe(a.get("evid", a.get("evidencia", "E2 (Corroborado)"))),
            "citacao": _safe(a.get("citacao", a.get("evidencia_literal", "")), ""),
            "evidencia_literal": _safe(a.get("evidencia_literal", a.get("citacao", "")), ""),
            "localizacao_exata": _safe(a.get("localizacao_exata", a.get("loc", "")), ""),
            "doc_path": _safe(a.get("doc_path", a.get("doc_origem", "")), ""),
            "rule_id": _safe(a.get("rule_id", a.get("id", "")), ""),
            "criticidade": _safe(a.get("crit", a.get("criticidade", "Média"))),
            "prioridade": _safe(a.get("prio", a.get("prioridade", "P2"))),
            "fato": _safe(a.get("fato", "")),
            "impacto": _safe(a.get("impacto", "")),
            "solucao": _safe(a.get("solucao", a.get("mitigacao", "")), ""),
            "de": de_txt,
            "para": para_txt,
            "is_direct": is_dir,
            "proprietario": _safe(a.get("proprietario", "Proprietário Técnico")),
            "visual_asset_id": _safe(a.get("visual_asset_id", ""), ""),
            "visual_file": _safe(a.get("visual_file", ""), ""),
            "visual_sha256": _safe(a.get("visual_sha256", ""), ""),
            "visual_page": a.get("visual_page"),
            "semantic_skill": _safe(a.get("semantic_skill", ""), ""),
            "source_kind": _safe(a.get("source_kind", ""), ""),
            "evidence_sources": a.get("evidence_sources", []),
            "referencias": a.get("referencias", []),
        }
        for optional_key in ("adjudication", "adjudication_status", "texto_afirmado", "diagrama_demonstrado"):
            if optional_key in a and a[optional_key] is not None:
                item[optional_key] = a[optional_key]
        item = schemas.ensure_canonical_finding_fields(item)
        normalized_findings.append(item)

    valid_adjudication_statuses = {
        "pendente", "confirmado", "falso_positivo", "fora_de_escopo",
        "evidencia_insuficiente", "duplicado",
    }
    adj_counts = {s: 0 for s in valid_adjudication_statuses}
    confirmed = []
    for item in normalized_findings:
        adj = item.get("adjudication")
        st = adj.get("status") if isinstance(adj, dict) else item.get("adjudication_status")
        if not isinstance(st, str) or st not in valid_adjudication_statuses:
            st = "pendente"
        if st == "pendente" and not isinstance(adj, dict):
            item["adjudication_status"] = "pendente"
        adj_counts[st] += 1
        if st == "confirmado":
            confirmed.append(item)

    pending_count = adj_counts["pendente"] + adj_counts["evidencia_insuficiente"]
    excluded_count = adj_counts["falso_positivo"] + adj_counts["fora_de_escopo"] + adj_counts["duplicado"]

    lacunas_conf = [a for a in confirmed if "lacuna" in str(a.get("tipo", "")).lower()]
    riscos_conf = [a for a in confirmed if "risco" in str(a.get("tipo", "")).lower()]
    lacunas_out = lacunas_conf if normalized_findings else lacunas
    riscos_out = riscos_conf if normalized_findings else riscos

    if pending_count > 0:
        parecer_ext, parecer_badge = "PENDENTE DE ADJUDICAÇÃO", "PENDENTE"
        iqd_str = "—"
        denom = iqd_denominador if iqd_denominador and iqd_denominador > 0 else max(len(confirmed) * 5, 20)
        decision_status = "pendente_adjudicacao"
    else:
        parecer_ext, parecer_badge = calculate_parecer(confirmed, lacunas_out)
        _, iqd_str, denom = calculate_iqd(confirmed, iqd_denominador)
        decision_status = "concluido"

    # Contagens para KPIs baseadas em achados confirmados
    n_achados = len(normalized_findings)
    n_lacunas = len(lacunas_out)
    n_riscos = len(riscos_out)
    n_redacoes = len(redacoes) + len(erratas)
    n_perguntas = len(esclarecimentos)

    criticos = [a for a in confirmed if str(a.get("criticidade", "")).upper() == "CRÍTICA"]
    altos = [a for a in confirmed if str(a.get("criticidade", "")).upper() == "ALTA"]
    medios = [a for a in confirmed if str(a.get("criticidade", "")).upper() in ("MÉDIA", "MEDIA")]
    baixos = [a for a in confirmed if str(a.get("criticidade", "")).upper() in ("BAIXA", "INFORMATIVA")]
    estruturais = [
        a for a in confirmed
        if any(
            kw in (str(a.get("tipo", "")) + " " + str(a.get("categoria", ""))).casefold()
            for kw in ("estrutur", "redacional", "rfc 2119", "iso 29148")
        )
    ]

    json_payload = {
        "schema_version": data.get("schema_version", "2.1"),
        "cobertura_extracao": data.get("cobertura_extracao", {}),
        "execucao_skills": data.get("execucao_skills", []),
        "visual_inventory": data.get("visual_inventory", {}),
        "visual_analysis": data.get("visual_analysis", {}),
        "semantic_analysis": data.get("semantic_analysis", {}),
        "title": title,
        "timestamp": timestamp,
        "parecer": parecer_ext,
        "parecer_badge": parecer_badge,
        "decision_status": decision_status,
        "adjudication_summary": adj_counts,
        "kpis": {
            "total_achados": n_achados,
            "achados_confirmados": len(confirmed),
            "achados_pendentes_adjudicacao": pending_count,
            "achados_excluidos": excluded_count,
            "criticos": len(criticos),
            "altos": len(altos),
            "medios": len(medios),
            "baixos": len(baixos),
            "estruturais": len(estruturais),
            "lacunas": n_lacunas,
            "riscos": n_riscos,
            "redacoes": n_redacoes,
            "perguntas": n_perguntas,
            "iqd": iqd_str,
            "iqd_denominador": denom
        },
        "baseline_files": baseline_files,
        "skills_ativas": skills_ativas,
        "findings": normalized_findings,
        "lacunas": lacunas_out,
        "riscos": riscos_out,
        "redacoes": redacoes,
        "erratas": erratas,
        "esclarecimentos": esclarecimentos,
        "checklists_status": checklists_status
    }
    for extra_key in (
        "audit_trail",
        "parent_analysis",
        "version_reconciliation",
        "external_inputs",
        "metadata",
    ):
        if extra_key in data and data[extra_key] is not None:
            json_payload[extra_key] = data[extra_key]

    def _clean_surrogates(obj):
        if isinstance(obj, str):
            return re.sub(r'[\ud800-\udfff]', '', obj)
        elif isinstance(obj, dict):
            return {k: _clean_surrogates(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_clean_surrogates(v) for v in obj]
        return obj

    json_payload = _clean_surrogates(json_payload)

    with open(os.path.join(rel_dir, "dados_analise.json"), "w", encoding="utf-8") as f:
        json.dump(json_payload, f, indent=2, ensure_ascii=False)

    return parecer_badge


def detect_document_versions(filenames: list[str]) -> dict:
    """
    Analisa uma lista de nomes de arquivos dentro de um lote e agrupa por documento base.
    Identifica se há múltiplos arquivos que representam versões sucessivas (série histórica).
    Retorna um dicionário {doc_base: [{'filename': ..., 'version': ..., 'order': ...}, ...]}.
    """
    version_regex = re.compile(
        r'(?:^|[_ \-])(?:v|ver|vers[aã]o|rev)[_ \-]*(\d+(?:\.\d+)*)|[_ \-](\d+\.\d+(?:\.\d+)*)$',
        re.IGNORECASE,
    )
    groups = {}

    for fname in sorted(filenames):
        # Remove extensão
        base_name, _ = os.path.splitext(fname)
        # Tenta extrair a versão
        match = version_regex.search(base_name)
        if match:
            ver_str = match.group(1) or match.group(2)
            # Chave do documento removendo o marcador de versão encontrado
            stripped = (base_name[:match.start()] + base_name[match.end():]).strip('_- ')
            canonical_key = re.sub(r'[_\s-]+', '_', stripped or base_name).upper()
            try:
                # Transforma '1.8' em (1, 8) para ordenação correta
                parts = tuple(int(p) for p in ver_str.split('.') if p.isdigit())
            except Exception:
                parts = (0,)
            info = {
                "filename": fname,
                "version_str": ver_str,
                "version_tuple": parts,
                "is_versioned": True
            }
        else:
            canonical_key = re.sub(r'\s+', '_', base_name).upper()
            info = {
                "filename": fname,
                "version_str": "1.0",
                "version_tuple": (1, 0),
                "is_versioned": False
            }

        groups.setdefault(canonical_key, []).append(info)

    # Ordena cada grupo pela tupla de versão
    for key in groups:
        groups[key].sort(key=lambda x: x["version_tuple"])

    return groups


def reconcile_versions(
    json_antigo: dict,
    json_novo: dict,
    summary_notes: str = "",
    external_audit_disposition: list[dict] = None,
) -> dict:
    """
    Confronta a base de auditoria de uma versão anterior com a versão nova do mesmo lote/documento.
    Classifica os achados ativos em:
      - Sanados / Expurgados (resolvidos ou removidos por foco de escopo na nova versão)
      - Reincidentes (persistem entre versões, destacando os Refinados/Reancorados)
      - Novos (introduzidos na nova versão)
    Calcula taxa de resolução, comparativo de KPIs, sumário de alterações e delta de IQD.
    """
    raw_antigos = json_antigo.get("findings", []) or []
    raw_novos = json_novo.get("findings", []) or []

    def _adj_info(item: dict) -> tuple[str, str]:
        adj = item.get("adjudication")
        if isinstance(adj, dict):
            return str(adj.get("status") or item.get("adjudication_status") or ""), str(adj.get("rationale") or "")
        return str(item.get("adjudication_status") or ""), ""

    def _active_findings(raw: list[dict]) -> list[dict]:
        has_confirmed = any(_adj_info(item)[0] == "confirmado" for item in raw)
        has_any_adj = any(_adj_info(item)[0] for item in raw)
        if has_confirmed or has_any_adj:
            return [item for item in raw if _adj_info(item)[0] == "confirmado"]
        return list(raw)

    findings_antigos = _active_findings(raw_antigos)
    findings_novos = _active_findings(raw_novos)
    raw_novos_by_id = {str(fn.get("id", "")): fn for fn in raw_novos if fn.get("id")}

    def _simplify(s: str) -> str:
        s = (s or "").lower()
        return re.sub(r'[^a-z0-9]', '', s)

    reincidentes = []
    refinados = []
    sanados = []
    expurgados_escopo = []
    novos = []
    matched_new_ids = set()

    for fa in findings_antigos:
        fa_id = fa.get("id", "")
        fa_tit_raw = fa.get("title") or fa.get("titulo") or ""
        fa_tit = _simplify(fa_tit_raw)
        fa_cat = fa.get("categoria") or fa.get("cat") or ""
        fa_loc = fa.get("loc") or fa.get("localizacao") or ""
        fa_doc = str(fa.get("doc_origem") or fa.get("documento") or "—")

        matched_fn = None
        for fn in findings_novos:
            fn_id = fn.get("id", "")
            if fn_id in matched_new_ids:
                continue
            fn_tit_raw = fn.get("title") or fn.get("titulo") or ""
            fn_tit = _simplify(fn_tit_raw)
            fn_cat = fn.get("categoria") or fn.get("cat") or ""

            prev_ref_match = bool(fa_id and fn.get("previous_finding_id") and fn.get("previous_finding_id") == fa_id)
            id_match = bool(fa_id and fn_id and fa_id == fn_id)
            title_match = bool(
                fa_cat and fn_cat and fa_cat == fn_cat
                and fa_tit and fn_tit
                and (fa_tit in fn_tit or fn_tit in fa_tit)
            )
            if prev_ref_match or id_match or title_match:
                matched_fn = fn
                matched_new_ids.add(fn_id)
                break

        if matched_fn:
            fn_tit_raw = matched_fn.get("title") or matched_fn.get("titulo") or fa_tit_raw
            fn_loc = matched_fn.get("loc") or matched_fn.get("localizacao") or ""
            fn_doc = str(matched_fn.get("doc_origem") or matched_fn.get("documento") or fa_doc)

            changes = []
            if fa_doc and fn_doc and fa_doc != fn_doc:
                changes.append(f"Reancorado de `{fa_doc}` para `{fn_doc}`")
            if fa_tit_raw != fn_tit_raw:
                changes.append("Título refinado")
            fa_fato = str(fa.get("fato") or "").strip()
            fn_fato = str(matched_fn.get("fato") or "").strip()
            if fa_fato and fn_fato and fa_fato != fn_fato:
                changes.append("Descrição factual/evidências enriquecidas")
            fa_evs = len(fa.get("evidence_sources") or [])
            fn_evs = len(matched_fn.get("evidence_sources") or [])
            if fn_evs > fa_evs:
                changes.append(f"Fontes de evidência ampliadas ({fa_evs} → {fn_evs})")
            foi_refinado = bool(changes)
            detalhe_refinamento = "; ".join(changes)

            entry = {
                "id_anterior": fa_id,
                "id_atual": matched_fn.get("id", ""),
                "title": fn_tit_raw,
                "titulo": fn_tit_raw,
                "doc_origem": fn_doc,
                "doc_anterior": fa_doc,
                "doc_atual": fn_doc,
                "criticidade": matched_fn.get("criticidade", matched_fn.get("crit", "Média")),
                "prioridade": matched_fn.get("prioridade", matched_fn.get("prio", "P2")),
                "categoria": matched_fn.get("categoria", matched_fn.get("cat", fa_cat)),
                "loc_anterior": fa_loc,
                "loc_atual": fn_loc,
                "localizacao_anterior": fa_loc,
                "localizacao_atual": fn_loc,
                "foi_refinado": foi_refinado,
                "detalhe_refinamento": detalhe_refinamento,
                "status": "reincidente"
            }
            reincidentes.append(entry)
            if foi_refinado:
                refinados.append(entry)
        else:
            fn_excl = raw_novos_by_id.get(fa_id)
            excl_st, excl_rationale = _adj_info(fn_excl) if fn_excl else ("", "")
            is_scope_expunged = excl_st in ("fora_de_escopo", "falso_positivo", "duplicado")
            motivo_saida = "expurgado_escopo" if is_scope_expunged else "saneado_na_baseline"
            san_entry = {
                "id_anterior": fa_id,
                "id_atual": fn_excl.get("id", fa_id) if fn_excl else "",
                "title": fa_tit_raw,
                "titulo": fa_tit_raw,
                "doc_origem": fa_doc,
                "criticidade": fa.get("criticidade", fa.get("crit", "Média")),
                "prioridade": fa.get("prioridade", fa.get("prio", "P2")),
                "categoria": fa_cat,
                "loc": fa_loc,
                "localizacao": fa_loc,
                "motivo_saida": motivo_saida,
                "status_adjudicacao": excl_st,
                "justificativa": excl_rationale,
                "status": "sanado"
            }
            sanados.append(san_entry)
            if is_scope_expunged:
                expurgados_escopo.append(san_entry)

    for fn in findings_novos:
        fn_id = fn.get("id", "")
        if fn_id not in matched_new_ids:
            fn_tit_raw = fn.get("title") or fn.get("titulo") or ""
            fn_loc = fn.get("loc") or fn.get("localizacao") or ""
            novos.append({
                "id_atual": fn_id,
                "title": fn_tit_raw,
                "titulo": fn_tit_raw,
                "doc_origem": str(fn.get("doc_origem") or fn.get("documento") or "—"),
                "criticidade": fn.get("criticidade", fn.get("crit", "Média")),
                "prioridade": fn.get("prioridade", fn.get("prio", "P2")),
                "categoria": fn.get("categoria", fn.get("cat", "")),
                "evidencia": fn.get("evidencia") or fn.get("evid") or "—",
                "origem_verificacao": str(fn.get("origin_note") or fn.get("rule_id") or "—"),
                "loc": fn_loc,
                "localizacao": fn_loc,
                "status": "novo"
            })

    total_ant = len(findings_antigos)
    total_novo = len(findings_novos)
    n_sanados = len(sanados)
    n_reincidentes = len(reincidentes)
    n_refinados = len(refinados)
    n_expurgados = len(expurgados_escopo)
    n_novos = len(novos)

    taxa_resolucao = round((n_sanados / total_ant * 100), 1) if total_ant > 0 else 100.0

    kpis_ant = json_antigo.get("kpis", {}) or {}
    kpis_novo = json_novo.get("kpis", {}) or {}
    iqd_ant_str = str(kpis_ant.get("iqd", "0%"))
    iqd_novo_str = str(kpis_novo.get("iqd", "0%"))

    try:
        iqd_ant_num = float(re.sub(r'[^0-9.]', '', iqd_ant_str))
        iqd_novo_num = float(re.sub(r'[^0-9.]', '', iqd_novo_str))
        delta_iqd = round(iqd_novo_num - iqd_ant_num, 1)
        delta_iqd_str = f"{'+' if delta_iqd >= 0 else ''}{delta_iqd}%"
    except Exception:
        delta_iqd_str = "—"

    v_ant = json_antigo.get("timestamp", "anterior")
    v_atu = json_novo.get("timestamp", "atual")
    auto_summary = (
        f"Evolução da análise de {v_ant} para {v_atu}: {n_novos} novo(s) achado(s) incorporado(s), "
        f"{n_refinados} achado(s) refinado(s)/reancorado(s), {n_sanados} achado(s) removido(s) "
        f"({n_expurgados} expurgado(s) por foco de escopo) e {n_reincidentes} achado(s) mantido(s). "
        f"IQD: {iqd_ant_str} → {iqd_novo_str} ({delta_iqd_str})."
    )

    def _int_kpi(kdict: dict, key: str, default: int = 0) -> int:
        try:
            return int(kdict.get(key, default) or 0)
        except (TypeError, ValueError):
            return default

    ant_conf = _int_kpi(kpis_ant, "achados_confirmados", total_ant)
    novo_conf = _int_kpi(kpis_novo, "achados_confirmados", total_novo)
    ant_crit = _int_kpi(kpis_ant, "criticos", 0)
    novo_crit = _int_kpi(kpis_novo, "criticos", 0)
    ant_alt = _int_kpi(kpis_ant, "altos", 0)
    novo_alt = _int_kpi(kpis_novo, "altos", 0)
    ant_lac = _int_kpi(kpis_ant, "lacunas", 0)
    novo_lac = _int_kpi(kpis_novo, "lacunas", 0)
    ant_perg = _int_kpi(kpis_ant, "perguntas", 0)
    novo_perg = _int_kpi(kpis_novo, "perguntas", 0)

    def _delta_int(a: int, b: int) -> str:
        d = b - a
        return f"{'+' if d > 0 else ''}{d}"

    return {
        "versao_anterior": v_ant,
        "versao_atual": v_atu,
        "total_anteriores": total_ant,
        "total_atuais": total_novo,
        "achados_sanados_count": n_sanados,
        "achados_expurgados_escopo_count": n_expurgados,
        "achados_reincidentes_count": n_reincidentes,
        "achados_refinados_count": n_refinados,
        "novos_achados_count": n_novos,
        "taxa_resolucao_pct": taxa_resolucao,
        "iqd_anterior": iqd_ant_str,
        "iqd_atual": iqd_novo_str,
        "delta_iqd": delta_iqd_str,
        "parecer_anterior": json_antigo.get("parecer_badge", json_antigo.get("parecer", "—")),
        "parecer_atual": json_novo.get("parecer_badge", json_novo.get("parecer", "—")),
        "sumario_alteracoes": summary_notes.strip() if summary_notes and summary_notes.strip() else auto_summary,
        "kpi_comparison": {
            "confirmados": {"anterior": ant_conf, "atual": novo_conf, "delta": _delta_int(ant_conf, novo_conf)},
            "criticos": {"anterior": ant_crit, "atual": novo_crit, "delta": _delta_int(ant_crit, novo_crit)},
            "altos": {"anterior": ant_alt, "atual": novo_alt, "delta": _delta_int(ant_alt, novo_alt)},
            "lacunas": {"anterior": ant_lac, "atual": novo_lac, "delta": _delta_int(ant_lac, novo_lac)},
            "perguntas": {"anterior": ant_perg, "atual": novo_perg, "delta": _delta_int(ant_perg, novo_perg)},
            "iqd": {"anterior": iqd_ant_str, "atual": iqd_novo_str, "delta": delta_iqd_str},
        },
        "sanados": sanados,
        "expurgados_escopo": expurgados_escopo,
        "reincidentes": reincidentes,
        "refinados": refinados,
        "novos": novos,
        "rastreabilidade_insumos_externos": list(external_audit_disposition or []),
    }


