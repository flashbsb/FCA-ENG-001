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


def reconcile_versions(json_antigo: dict, json_novo: dict) -> dict:
    """
    Confronta a base de auditoria de uma versão anterior com a versão nova do mesmo lote/documento.
    Classifica os achados em:
      - Sanados (resolvidos na nova versão)
      - Reincidentes (persistem sem correção)
      - Novos (introduzidos na nova versão)
    Calcula taxa de resolução e delta de IQD.
    """
    findings_antigos = json_antigo.get("findings", [])
    findings_novos = json_novo.get("findings", [])

    def _simplify(s: str) -> str:
        s = s.lower()
        return re.sub(r'[^a-z0-9]', '', s)

    reincidentes = []
    sanados = []
    novos = []
    matched_new_ids = set()

    for fa in findings_antigos:
        fa_id = fa.get("id", "")
        fa_tit_raw = fa.get("title") or fa.get("titulo") or ""
        fa_tit = _simplify(fa_tit_raw)
        fa_cat = fa.get("categoria") or fa.get("cat") or ""
        fa_loc = fa.get("loc") or fa.get("localizacao") or ""

        matched_fn = None
        for fn in findings_novos:
            fn_id = fn.get("id", "")
            if fn_id in matched_new_ids:
                continue
            fn_tit_raw = fn.get("title") or fn.get("titulo") or ""
            fn_tit = _simplify(fn_tit_raw)
            fn_cat = fn.get("categoria") or fn.get("cat") or ""

            # Match por ID direto ou por similaridade forte de título na mesma categoria
            id_match = bool(fa_id and fn_id and fa_id == fn_id)
            title_match = bool(
                fa_cat and fn_cat and fa_cat == fn_cat
                and fa_tit and fn_tit
                and (fa_tit in fn_tit or fn_tit in fa_tit)
            )
            if id_match or title_match:
                matched_fn = fn
                matched_new_ids.add(fn_id)
                break

        if matched_fn:
            fn_tit_raw = matched_fn.get("title") or matched_fn.get("titulo") or fa_tit_raw
            fn_loc = matched_fn.get("loc") or matched_fn.get("localizacao") or ""
            reincidentes.append({
                "id_anterior": fa_id,
                "id_atual": matched_fn.get("id", ""),
                "title": fn_tit_raw,
                "titulo": fn_tit_raw,
                "criticidade": matched_fn.get("criticidade", matched_fn.get("crit", "Média")),
                "prioridade": matched_fn.get("prioridade", matched_fn.get("prio", "P2")),
                "categoria": matched_fn.get("categoria", matched_fn.get("cat", fa_cat)),
                "loc_anterior": fa_loc,
                "loc_atual": fn_loc,
                "localizacao_anterior": fa_loc,
                "localizacao_atual": fn_loc,
                "status": "reincidente"
            })
        else:
            sanados.append({
                "id_anterior": fa_id,
                "title": fa_tit_raw,
                "titulo": fa_tit_raw,
                "criticidade": fa.get("criticidade", fa.get("crit", "Média")),
                "prioridade": fa.get("prioridade", fa.get("prio", "P2")),
                "categoria": fa_cat,
                "loc": fa_loc,
                "localizacao": fa_loc,
                "status": "sanado"
            })

    for fn in findings_novos:
        fn_id = fn.get("id", "")
        if fn_id not in matched_new_ids:
            fn_tit_raw = fn.get("title") or fn.get("titulo") or ""
            fn_loc = fn.get("loc") or fn.get("localizacao") or ""
            novos.append({
                "id_atual": fn_id,
                "title": fn_tit_raw,
                "titulo": fn_tit_raw,
                "criticidade": fn.get("criticidade", fn.get("crit", "Média")),
                "prioridade": fn.get("prioridade", fn.get("prio", "P2")),
                "categoria": fn.get("categoria", fn.get("cat", "")),
                "loc": fn_loc,
                "localizacao": fn_loc,
                "status": "novo"
            })

    total_ant = len(findings_antigos)
    total_novo = len(findings_novos)
    n_sanados = len(sanados)
    n_reincidentes = len(reincidentes)
    n_novos = len(novos)

    taxa_resolucao = round((n_sanados / total_ant * 100), 1) if total_ant > 0 else 100.0

    iqd_ant_str = str(json_antigo.get("kpis", {}).get("iqd", "0%"))
    iqd_novo_str = str(json_novo.get("kpis", {}).get("iqd", "0%"))

    try:
        iqd_ant_num = float(re.sub(r'[^0-9.]', '', iqd_ant_str))
        iqd_novo_num = float(re.sub(r'[^0-9.]', '', iqd_novo_str))
        delta_iqd = round(iqd_novo_num - iqd_ant_num, 1)
        delta_iqd_str = f"{'+' if delta_iqd >= 0 else ''}{delta_iqd}%"
    except Exception:
        delta_iqd_str = "—"

    return {
        "versao_anterior": json_antigo.get("timestamp", "anterior"),
        "versao_atual": json_novo.get("timestamp", "atual"),
        "total_anteriores": total_ant,
        "total_atuais": total_novo,
        "achados_sanados_count": n_sanados,
        "achados_reincidentes_count": n_reincidentes,
        "novos_achados_count": n_novos,
        "taxa_resolucao_pct": taxa_resolucao,
        "iqd_anterior": iqd_ant_str,
        "iqd_atual": iqd_novo_str,
        "delta_iqd": delta_iqd_str,
        "parecer_anterior": json_antigo.get("parecer_badge", json_antigo.get("parecer", "—")),
        "parecer_atual": json_novo.get("parecer_badge", json_novo.get("parecer", "—")),
        "sanados": sanados,
        "reincidentes": reincidentes,
        "novos": novos
    }


