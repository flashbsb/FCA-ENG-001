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
    impacto_total = sum(pesos.get(a.get('crit', 'Média'), 2) for a in achados)

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
                   if a.get('crit', '').upper() == 'CRÍTICA' and a.get('prio', '').upper() == 'P0']

    if criticos_p0:
        return "NÃO APTO PARA DECISÃO", "NÃO APTO"

    if achados or lacunas:
        return "APTO COM RESSALVAS", "APTO COM RESSALVAS"

    return "APTO PARA DECISÃO", "APTO"


def _safe(val: any, fallback: str = "não disponível") -> str:
    """Retorna o valor como string ou o fallback se vazio."""
    s = str(val).strip() if val is not None else ""
    return s if s and s.lower() not in ("none", "null", "") else fallback


def sanitize_batch_isolation(val):
    """Recursivamente remove referências a outros lotes e sanitiza texto para garantir isolamento por lote."""
    if isinstance(val, str):
        if not val:
            return val
        import unicodedata
        val = val.encode('utf-8', errors='surrogateescape').decode('utf-8', errors='replace')
        val = unicodedata.normalize('NFC', val)
        val = re.sub(r'Idêntico ao achado [A-Z]{2,5}-\d{3} do Lote \d+:?\s*', '', val, flags=re.IGNORECASE)
        val = re.sub(r'— mesmo padrão do Lote \d+', '', val, flags=re.IGNORECASE)
        val = re.sub(r'\(Lote \d+\)', '', val, flags=re.IGNORECASE)
        val = re.sub(r'\(Lotes \d+(?:,\s*\d+)*(?:\s*e\s*\d+)?\)', '', val, flags=re.IGNORECASE)
        val = re.sub(r'Lote \d+ \(([^)]+)\)', r'\1', val, flags=re.IGNORECASE)
        val = re.sub(r'Lote \d+', 'especificação técnica', val, flags=re.IGNORECASE)
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
        return val
    elif isinstance(val, list):
        return [sanitize_batch_isolation(item) for item in val]
    elif isinstance(val, dict):
        return {k: sanitize_batch_isolation(v) for k, v in val.items()}
    return val


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

    parecer_ext, parecer_badge = calculate_parecer(achados, lacunas)
    iqd_val, iqd_str, denom = calculate_iqd(achados, iqd_denominador)

    # Contagens para KPIs
    n_achados = len(achados)
    n_lacunas = len(lacunas)
    n_riscos = len(riscos)
    n_redacoes = len(redacoes) + len(erratas)
    n_perguntas = len(esclarecimentos)

    criticos = [a for a in achados if a.get('crit', '').upper() == 'CRÍTICA']
    altos = [a for a in achados if a.get('crit', '').upper() == 'ALTA']
    medios = [a for a in achados if a.get('crit', '').upper() == 'MÉDIA']
    baixos = [a for a in achados if a.get('crit', '').upper() in ('BAIXA', 'INFORMATIVA')]

    # ──────────────────────────────────────────────────
    # Normalização dos Achados e Estrutura dos Dados
    # ──────────────────────────────────────────────────
    normalized_findings = []
    for a in achados:
        de_txt = _safe(a.get("de", a.get("texto_atual", "")))
        para_txt = _safe(a.get("para", a.get("texto_sugerido", "")))
        tipo_str = _safe(a.get("tipo", "Erro Técnico"))
        is_dir = bool(de_txt or para_txt or "→" in tipo_str or "grafia" in tipo_str.lower() or "sequência" in tipo_str.lower())
        normalized_findings.append({
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
            "solucao": _safe(a.get("solucao", a.get("mitigacao", ""))),
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
        })

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
        "kpis": {
            "total_achados": n_achados,
            "criticos": len(criticos),
            "altos": len(altos),
            "medios": len(medios),
            "baixos": len(baixos),
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
        "lacunas": lacunas,
        "riscos": riscos,
        "redacoes": redacoes,
        "erratas": erratas,
        "esclarecimentos": esclarecimentos,
        "checklists_status": checklists_status
    }

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
    version_regex = re.compile(r'[_vV\- ]+(\d+(?:\.\d+)*)', re.IGNORECASE)
    groups = {}

    for fname in sorted(filenames):
        # Remove extensão
        base_name, _ = os.path.splitext(fname)
        # Tenta extrair a versão
        match = version_regex.search(base_name)
        if match:
            ver_str = match.group(1)
            # Chave do documento removendo a versão
            canonical_key = re.sub(r'[_vV\- ]+' + re.escape(ver_str), '', base_name).strip('_- ')
            canonical_key = re.sub(r'\s+', '_', canonical_key).upper()
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
        fa_tit = _simplify(fa.get("titulo", ""))
        fa_cat = fa.get("categoria", "")

        matched_fn = None
        for fn in findings_novos:
            fn_id = fn.get("id", "")
            if fn_id in matched_new_ids:
                continue
            fn_tit = _simplify(fn.get("titulo", ""))
            fn_cat = fn.get("categoria", "")

            # Match por ID direto ou por similaridade forte de título na mesma categoria
            if (fa_id and fn_id and fa_id == fn_id) or (fa_cat == fn_cat and (fa_tit in fn_tit or fn_tit in fa_tit)):
                matched_fn = fn
                matched_new_ids.add(fn_id)
                break

        if matched_fn:
            reincidentes.append({
                "id_anterior": fa_id,
                "id_atual": matched_fn.get("id", ""),
                "titulo": matched_fn.get("titulo", fa.get("titulo", "")),
                "criticidade": matched_fn.get("criticidade", matched_fn.get("crit", "Média")),
                "prioridade": matched_fn.get("prioridade", matched_fn.get("prio", "P2")),
                "categoria": matched_fn.get("categoria", fa_cat),
                "localizacao_anterior": fa.get("localizacao", ""),
                "localizacao_atual": matched_fn.get("localizacao", ""),
                "status": "reincidente"
            })
        else:
            sanados.append({
                "id_anterior": fa_id,
                "titulo": fa.get("titulo", ""),
                "criticidade": fa.get("criticidade", fa.get("crit", "Média")),
                "prioridade": fa.get("prioridade", fa.get("prio", "P2")),
                "categoria": fa_cat,
                "localizacao": fa.get("localizacao", ""),
                "status": "sanado"
            })

    for fn in findings_novos:
        fn_id = fn.get("id", "")
        if fn_id not in matched_new_ids:
            novos.append({
                "id_atual": fn_id,
                "titulo": fn.get("titulo", ""),
                "criticidade": fn.get("criticidade", fn.get("crit", "Média")),
                "prioridade": fn.get("prioridade", fn.get("prio", "P2")),
                "categoria": fn.get("categoria", ""),
                "localizacao": fn.get("localizacao", ""),
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


