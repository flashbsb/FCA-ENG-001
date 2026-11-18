"""Contrato canônico de schema (SSOT) do dados_analise.json — FCA-ENG-001."""
from __future__ import annotations

import re
from typing import Any, TypedDict

SCHEMA_VERSION = "2.3"

VALID_ADJUDICATION_STATUSES = (
    "pendente",
    "confirmado",
    "falso_positivo",
    "fora_de_escopo",
    "evidencia_insuficiente",
    "duplicado",
)

VALID_CRITICIDADES = ("Crítica", "Alta", "Média", "Baixa", "Informativa")
VALID_PRIORIDADES = ("P0", "P1", "P2", "P3")

CANONICAL_ALIAS_PAIRS = (
    ("title", "titulo"),
    ("doc_origem", "documento"),
    ("loc", "localizacao"),
    ("categoria", "cat"),
    ("evidencia", "evid"),
    ("criticidade", "crit"),
    ("prioridade", "prio"),
    ("citacao", "evidencia_literal"),
)


class EvidenceSourceSchema(TypedDict, total=False):
    document_path: str
    document_name: str
    location: str
    quote: str
    sha256: str
    evidence_role: str


class ReferenceSchema(TypedDict, total=False):
    titulo: str
    url: str
    nota: str


class AdjudicationSchema(TypedDict, total=False):
    status: str
    rationale: str
    reviewer: str
    adjudicated_at: str
    related_finding_id: str


class FindingSchema(TypedDict, total=False):
    id: str
    rule_id: str
    title: str
    titulo: str
    doc_origem: str
    documento: str
    doc_path: str
    loc: str
    localizacao: str
    localizacao_exata: str
    categoria: str
    cat: str
    tipo: str
    evidencia: str
    evid: str
    criticidade: str
    crit: str
    prioridade: str
    prio: str
    fato: str
    impacto: str
    solucao: str
    citacao: str
    evidencia_literal: str
    de: str
    para: str
    is_direct: bool
    proprietario: str
    semantic_skill: str
    source_kind: str
    visual_asset_id: str
    visual_file: str
    visual_sha256: str
    visual_page: int
    texto_afirmado: str
    diagrama_demonstrado: str
    adjudication_status: str
    adjudication: AdjudicationSchema
    evidence_sources: list[EvidenceSourceSchema]
    referencias: list[ReferenceSchema]


class ChecklistItemSchema(TypedDict, total=False):
    verificacao: str
    status: str
    achado: str
    evidencia: str


class ChecklistStatusSchema(TypedDict, total=False):
    conformidade: str
    observacao: str
    itens: list[ChecklistItemSchema]


class KPIsSchema(TypedDict, total=False):
    total_achados: int
    achados_confirmados: int
    achados_pendentes_adjudicacao: int
    achados_excluidos: int
    criticos: int
    altos: int
    medios: int
    baixos: int
    estruturais: int
    lacunas: int
    riscos: int
    redacoes: int
    perguntas: int
    iqd: str
    iqd_denominador: int


class DadosAnaliseSchema(TypedDict, total=False):
    schema_version: str
    title: str
    timestamp: str
    parecer: str
    parecer_badge: str
    decision_status: str
    adjudication_summary: dict[str, int]
    kpis: KPIsSchema
    baseline_files: list[dict[str, Any]]
    external_inputs: list[dict[str, Any]]
    review_comments: list[dict[str, Any]]
    skills_ativas: list[str]
    findings: list[FindingSchema]
    lacunas: list[dict[str, Any]]
    riscos: list[dict[str, Any]]
    redacoes: list[dict[str, Any]]
    erratas: list[dict[str, Any]]
    esclarecimentos: list[dict[str, Any]]
    checklists_status: dict[str, ChecklistStatusSchema]
    cobertura_extracao: dict[str, Any]
    execucao_skills: list[dict[str, Any]]
    visual_inventory: dict[str, Any]
    visual_analysis: dict[str, Any]
    semantic_analysis: dict[str, Any]
    audit_trail: list[dict[str, Any]]
    parent_analysis: dict[str, Any]
    version_reconciliation: dict[str, Any]
    metadata: dict[str, Any]


def ensure_canonical_finding_fields(finding: dict[str, Any]) -> dict[str, Any]:
    """Sincroniza chaves canônicas e apelidos legados de um achado sem descartar dados."""
    normalized = dict(finding) if isinstance(finding, dict) else {}
    for canonical, legacy in CANONICAL_ALIAS_PAIRS:
        can_val = normalized.get(canonical)
        leg_val = normalized.get(legacy)
        can_present = can_val is not None and str(can_val).strip() != ""
        leg_present = leg_val is not None and str(leg_val).strip() != ""
        if not can_present and leg_present:
            normalized[canonical] = leg_val
        elif can_present and not leg_present:
            normalized[legacy] = can_val

    if not isinstance(normalized.get("evidence_sources"), list):
        normalized["evidence_sources"] = []
    if not isinstance(normalized.get("referencias"), list):
        normalized["referencias"] = []
    return normalized


def validate_dados_analise_schema(data: Any) -> list[str]:
    """Valida invariantes estruturais e normativos do payload SSOT dados_analise.json."""
    if not isinstance(data, dict):
        return ["O conteúdo de dados_analise.json deve ser um objeto JSON válido."]

    issues: list[str] = []
    required_top = (
        "title",
        "timestamp",
        "parecer",
        "kpis",
        "baseline_files",
        "skills_ativas",
        "findings",
    )
    for key in required_top:
        if key not in data or data.get(key) is None:
            issues.append(f"Campo obrigatório ausente no SSOT: '{key}'.")

    kpis = data.get("kpis")
    if kpis is not None and not isinstance(kpis, dict):
        issues.append("O campo 'kpis' no SSOT deve ser um objeto JSON.")
    elif isinstance(kpis, dict):
        required_kpis = (
            "total_achados",
            "achados_confirmados",
            "achados_pendentes_adjudicacao",
            "criticos",
            "lacunas",
            "iqd",
            "iqd_denominador",
        )
        for kkey in required_kpis:
            if kkey not in kpis:
                issues.append(f"Indicador obrigatório ausente em 'kpis': '{kkey}'.")

        try:
            pending_n = int(kpis.get("achados_pendentes_adjudicacao", 0) or 0)
        except (TypeError, ValueError):
            pending_n = 0
            issues.append("Valor inválido para 'kpis.achados_pendentes_adjudicacao'.")

        if pending_n > 0:
            parecer_txt = str(data.get("parecer", "") or "")
            if "PENDENTE DE ADJUDICAÇÃO" not in parecer_txt.upper():
                issues.append(
                    "Invariante fail-safe violado: há achados pendentes de adjudicação, "
                    "mas o campo 'parecer' não está como 'PENDENTE DE ADJUDICAÇÃO'."
                )
            if str(kpis.get("iqd", "")) != "—":
                issues.append(
                    "Invariante fail-safe violado: enquanto houver achados pendentes de adjudicação, "
                    "'kpis.iqd' deve permanecer bloqueado como '—'."
                )

    findings = data.get("findings")
    if findings is not None and not isinstance(findings, list):
        issues.append("O campo 'findings' no SSOT deve ser uma lista.")
    elif isinstance(findings, list):
        required_finding_fields = ("id", "title", "tipo", "criticidade", "prioridade", "fato", "impacto")
        for idx, raw_finding in enumerate(findings):
            if not isinstance(raw_finding, dict):
                issues.append(f"Achado na posição {idx} não é um objeto JSON válido.")
                continue
            f = ensure_canonical_finding_fields(raw_finding)
            fid = str(f.get("id") or f"#{idx}")
            for fkey in required_finding_fields:
                val = f.get(fkey)
                if val is None or str(val).strip() == "":
                    issues.append(f"Achado '{fid}' sem campo obrigatório preenchido: '{fkey}'.")

            adj = raw_finding.get("adjudication")
            adj_status = adj.get("status") if isinstance(adj, dict) else raw_finding.get("adjudication_status", "pendente")
            if not isinstance(adj_status, str) or adj_status not in VALID_ADJUDICATION_STATUSES:
                issues.append(f"Achado '{fid}' possui status de adjudicação inválido: '{adj_status}'.")
                adj_status = "pendente"

            crit_cf = str(f.get("criticidade", "")).strip().casefold()
            if adj_status == "confirmado" and crit_cf in ("crítica", "critica", "alta"):
                ev_str = str(f.get("evidencia", "") or "").strip().upper()
                if not re.match(r"^E[23]\b", ev_str):
                    issues.append(
                        f"Achado confirmado '{fid}' com criticidade '{f.get('criticidade')}' "
                        f"exige grau de evidência E2 ou E3 (encontrado: '{f.get('evidencia', '')}')."
                    )

    return issues
