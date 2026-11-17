import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
MCP_DIR = os.path.dirname(TESTS_DIR)
REPO_ROOT = os.path.dirname(MCP_DIR)
if MCP_DIR not in sys.path:
    sys.path.insert(0, MCP_DIR)

import audit_engine  # noqa: E402
import html_compiler  # noqa: E402
import server  # noqa: E402


def _make_finding(
    fid: str,
    title: str,
    doc_origem: str,
    crit: str = "Alta",
    prio: str = "P1",
    tipo: str = "Inconsistência",
    cat: str = "Arquitetura",
    loc: str = "Seção 3.1",
    evid: str = "Evidência literal de baseline.",
    status: str = "confirmado",
    rationale: str = "Confirmado na baseline.",
    origin_note: str = "",
) -> dict:
    return {
        "id": fid,
        "title": title,
        "titulo": title,
        "doc_origem": doc_origem,
        "documento": doc_origem,
        "criticidade": crit,
        "crit": crit,
        "prioridade": prio,
        "prio": prio,
        "tipo": tipo,
        "cat": cat,
        "categoria": cat,
        "loc": loc,
        "localizacao": loc,
        "evidencia": evid,
        "evid": evid,
        "status_resolucao": "Aberto",
        "adjudication_status": status,
        "adjudication_rationale": rationale,
        "adjudication_source": "teste_unitario",
        "adjudicated_at": "2026-11-17T10:00:00",
        "impacto": "Impacto operacional verificável.",
        "recomendacao": "Corrigir especificação normativa.",
        "origin_note": origin_note,
    }


def _seed_workspace(tmp_root: str) -> tuple[str, str]:
    """Cria estrutura mínima de workspace isolado com r1 consolidado."""
    tpl_src = os.path.join(REPO_ROOT, "framework", "templates")
    tpl_dst = os.path.join(tmp_root, "framework", "templates")
    shutil.copytree(tpl_src, tpl_dst)

    lote = "LOTE_EVOL"
    version = "v1.2"
    r1_ts = "20261117_100000_LOTE_EVOL"
    r1_relpath = f"{lote}/{version}/{r1_ts}"
    run_dir = os.path.join(tmp_root, "analise", lote, version, r1_ts)
    rel_dir = os.path.join(run_dir, "relatorios")
    ent_dir = os.path.join(run_dir, "entrada")
    os.makedirs(rel_dir, exist_ok=True)
    os.makedirs(ent_dir, exist_ok=True)

    principal_txt = os.path.join(ent_dir, "HLD_Principal.txt")
    apoio_txt = os.path.join(ent_dir, "HLD_Apoio.txt")
    with open(principal_txt, "w", encoding="utf-8") as f:
        f.write("SLA de disponibilidade 99.9% sem fuso horario.\nSessao BGP sem hold-timer.\n")
    with open(apoio_txt, "w", encoding="utf-8") as f:
        f.write("Documento auxiliar de gerencia sem parametro DCN.\n")

    findings_r1 = [
        _make_finding(
            "F-001",
            "Achado isolado em documento auxiliar de gerencia",
            "HLD_Apoio.txt",
            crit="Média",
            prio="P2",
            tipo="Lacuna",
            loc="Seção 2.1",
            evid="Documento auxiliar de gerencia sem parametro DCN.",
        ),
        _make_finding(
            "F-002",
            "Divergência de SLA entre documentos",
            "HLD_Apoio.txt",
            crit="Alta",
            prio="P1",
            tipo="Inconsistência",
            loc="Seção 4.0",
            evid="SLA de disponibilidade 99.9% sem fuso horario.",
        ),
        _make_finding(
            "F-003",
            "SLA sem fuso horário explícito",
            "HLD_Principal.txt",
            crit="Crítica",
            prio="P0",
            tipo="Ambiguidade",
            loc="Seção 1.1",
            evid="SLA de disponibilidade 99.9% sem fuso horario.",
        ),
    ]

    r1_data = {
        "timestamp": r1_relpath,
        "title": "Revisão Técnica — HLD SDWAN",
        "skills_ativas": ["analisar-documento", "analisar-hld"],
        "skills_omitidas": [],
        "baseline_files": [
            {"name": "HLD_Principal.txt", "path": "HLD_Principal.txt", "role": "alvo_principal", "hash_sha256": "aaa"},
            {"name": "HLD_Apoio.txt", "path": "HLD_Apoio.txt", "role": "apoio_cruzamento", "hash_sha256": "bbb"},
        ],
        "external_inputs": [],
        "metadata": {
            "timestamp": r1_ts,
            "lote": lote,
            "versao_documento": version,
            "data_analise": "2026-11-17T10:00:00",
            "escopo": "HLD",
        },
        "findings": findings_r1,
        "lacunas": [{"id": "LAC-001", "titulo": "Lacuna inicial"}],
        "esclarecimentos": [{"id": "Q-001", "pergunta": "Qual o fuso horário aplicável ao SLA?"}],
        "kpis": {
            "total_achados": 3,
            "achados_confirmados": 3,
            "achados_pendentes_adjudicacao": 0,
            "achados_excluidos": 0,
            "criticos": 1,
            "altos": 1,
            "medios": 1,
            "lacunas": 1,
            "perguntas": 1,
            "iqd": "78.0%",
        },
        "parecer": "NÃO APTO PARA DECISÃO",
        "parecer_badge": "NÃO APTO",
        "decision_status": "concluido",
        "adjudication_summary": {"confirmado": 3, "pendente": 0, "excluido": 0},
    }

    with open(os.path.join(rel_dir, "dados_analise.json"), "w", encoding="utf-8") as f:
        json.dump(r1_data, f, indent=2, ensure_ascii=False)

    html_compiler.compile_timestamp_html(r1_relpath, root_dir=tmp_root)
    return r1_relpath, run_dir


def _extract_local_hrefs(html_text: str) -> list[str]:
    return [
        h for h in re.findall(r'href="([^"]+)"', html_text)
        if not h.startswith(("http://", "https://", "mailto:", "javascript:", "#"))
    ]


class EvolutionHtmlTests(unittest.TestCase):
    def test_evolution_decoupled_from_report_and_compiles_standalone_html(self):
        with tempfile.TemporaryDirectory() as tmp_root:
            with patch.object(server, "get_workspace_root", return_value=tmp_root):
                r1_rel, r1_dir = _seed_workspace(tmp_root)

                rev_raw = server.tool_create_review_revision(
                    r1_rel,
                    reason="Foco em alvo principal e auditoria cruzada <script>alert(1)</script>",
                    reviewer="revisor_qa",
                )
                rev_info = json.loads(rev_raw)
                self.assertEqual(rev_info["status"], "success")
                r2_rel = rev_info["new_analysis_path"]
                r2_json_path = os.path.join(tmp_root, "analise", r2_rel, "relatorios", "dados_analise.json")

                with open(r2_json_path, "r", encoding="utf-8") as f:
                    r2_data = json.load(f)

                # Simula ajustes da r2: expurgo de apoio (F-001), refinamento/reancoragem (F-002),
                # manutenção (F-003) e novo achado verificado na baseline (F-004).
                for f_item in r2_data["findings"]:
                    if f_item["id"] == "F-001":
                        f_item["adjudication_status"] = "fora_de_escopo"
                        f_item["adjudication_rationale"] = "Expurgado: achado isolado em documento de apoio."
                    elif f_item["id"] == "F-002":
                        f_item["doc_origem"] = "HLD_Principal.txt"
                        f_item["documento"] = "HLD_Principal.txt"
                        f_item["loc"] = "Seção 4.2 (Confronto DCN)"
                        f_item["localizacao"] = "Seção 4.2 (Confronto DCN)"
                        f_item["adjudication_rationale"] = "Reancorado no documento-alvo principal."

                r2_data["findings"].append(
                    _make_finding(
                        "F-004",
                        "Sessão BGP sem definição explícita de hold-timer",
                        "HLD_Principal.txt",
                        crit="Alta",
                        prio="P1",
                        tipo="Lacuna",
                        loc="Seção 5.1",
                        evid="Sessao BGP sem hold-timer.",
                        origin_note="Confronto cross-check GPTC-EXT-01 na baseline",
                    )
                )
                r2_data["external_inputs"] = [
                    {
                        "name": "Relatorio_Externo_GPTC_v1.1.html",
                        "path": "insumos_externos/Relatorio_Externo_GPTC_v1.1.html",
                        "hash_sha256": "ccc",
                        "role": "insumo_externo",
                        "normative_source": False,
                    }
                ]
                r2_data["kpis"].update({
                    "total_achados": 4,
                    "achados_confirmados": 3,
                    "achados_excluidos": 1,
                    "criticos": 1,
                    "altos": 2,
                    "medios": 0,
                    "lacunas": 1,
                    "perguntas": 1,
                    "iqd": "76.5%",
                })
                r2_data["adjudication_summary"] = {"confirmado": 3, "pendente": 0, "excluido": 1}

                with open(r2_json_path, "w", encoding="utf-8") as f:
                    json.dump(r2_data, f, indent=2, ensure_ascii=False)

                disposition = [
                    {
                        "item_externo": "EXT-01",
                        "tema": "Hold-timer BGP ausente na topologia",
                        "status": "Incorporado",
                        "achado_id": "F-004",
                        "justificativa": "Confirmado literalmente na baseline HLD_Principal.txt <img onerror=x>.",
                    },
                    {
                        "item_externo": "EXT-02",
                        "tema": "Hipótese de porta UDP proprietária",
                        "status": "Descartado",
                        "achado_id": "—",
                        "justificativa": "Não comprovado na baseline congelada.",
                    },
                ]
                rec_raw = server.tool_reconcile_versions(
                    r1_rel,
                    r2_rel,
                    summary_notes="Revisão r2 com segregação de documentos de apoio e validação cruzada <script>alert(1)</script>.",
                    external_audit_disposition=disposition,
                )
                rec_res = json.loads(rec_raw)
                self.assertEqual(rec_res["status"], "success")
                self.assertTrue(rec_res["evolution_html"].endswith("evolucao.html"))

                vr = rec_res["reconciliation"]
                self.assertEqual(vr["novos_achados_count"], 1)
                self.assertEqual(vr["achados_refinados_count"], 1)
                self.assertEqual(vr["achados_expurgados_escopo_count"], 1)
                self.assertEqual(vr["achados_reincidentes_count"], 2)
                self.assertEqual(len(vr["rastreabilidade_insumos_externos"]), 2)

                r1_index = os.path.join(r1_dir, "relatorios", "index.html")
                r2_index = os.path.join(tmp_root, "analise", r2_rel, "relatorios", "index.html")
                ver_evo = os.path.join(tmp_root, "analise", "LOTE_EVOL", "v1.2", "evolucao.html")
                r2_evo = os.path.join(tmp_root, "analise", r2_rel, "relatorios", "evolucao.html")
                r1_evo = os.path.join(r1_dir, "relatorios", "evolucao.html")
                master_html_path = os.path.join(tmp_root, "analise", "index.html")
                manifest_path = os.path.join(tmp_root, "analise", "manifest.json")

                for p in (r1_index, r2_index, ver_evo, r2_evo, r1_evo, master_html_path, manifest_path):
                    self.assertTrue(os.path.isfile(p), f"Arquivo esperado ausente: {p}")

                # 1 & 2. Relatórios de análise não embutem o quadro e possuem botão ./evolucao.html offline-safe
                for rpt_path in (r1_index, r2_index):
                    with open(rpt_path, "r", encoding="utf-8") as f:
                        rpt_html = f.read()
                    self.assertNotIn("Quadro de Reconciliação Técnica e Evolução (Diff de Achados)", rpt_html)
                    self.assertIn("./evolucao.html", rpt_html)
                    self.assertIn("Evolução de Versões", rpt_html)
                    self.assertNotIn("fonts.googleapis.com", rpt_html)
                    self.assertNotIn("cdnjs.cloudflare.com", rpt_html)

                with open(r2_index, "r", encoding="utf-8") as f:
                    r2_index_html = f.read()

                # 3. Ambos os evolucao.html (versão e rodada) completos, offline-safe e com links válidos
                for evo_path in (ver_evo, r2_evo):
                    with open(evo_path, "r", encoding="utf-8") as f:
                        evo_html = f.read()
                    self.assertNotIn("fonts.googleapis.com", evo_html)
                    self.assertNotIn("cdnjs.cloudflare.com", evo_html)
                    self.assertNotIn("<script>alert(1)</script>", evo_html)
                    self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", evo_html)
                    self.assertNotIn("<img onerror=x>", evo_html)
                    self.assertIn("&lt;img onerror=x&gt;", evo_html)

                    self.assertIn("Tabela Master de Versionamento das Análises", evo_html)
                    self.assertIn("20261117_100000_LOTE_EVOL", evo_html)
                    self.assertIn(os.path.basename(r2_rel), evo_html)
                    self.assertIn("Sumário Executivo de Alterações", evo_html)
                    self.assertIn("Novos Achados Incorporados", evo_html)
                    self.assertIn("F-004", evo_html)
                    self.assertIn("Achados Refinados ou Reancorados", evo_html)
                    self.assertIn("F-002", evo_html)
                    self.assertIn("Achados Saneados ou Expurgados por Foco de Escopo", evo_html)
                    self.assertIn("F-001", evo_html)
                    self.assertIn("Auditoria Cruzada de Insumos Externos", evo_html)
                    self.assertIn("EXT-01", evo_html)
                    self.assertIn("EXT-02", evo_html)

                    evo_dir = os.path.dirname(evo_path)
                    hrefs = _extract_local_hrefs(evo_html)
                    self.assertTrue(any(h.endswith("index.html") for h in hrefs))
                    for href in hrefs:
                        target_rel, _, frag = href.partition("#")
                        target_abs = os.path.normpath(os.path.join(evo_dir, target_rel))
                        self.assertTrue(os.path.isfile(target_abs), f"Link quebrado em {evo_path}: {href} -> {target_abs}")
                        if frag and target_abs == os.path.normpath(r2_index):
                            self.assertIn(f'id="{frag}"', r2_index_html, f"Âncora #{frag} ausente em r2/index.html")

                # 4. Central Master (manifest.json e analise/index.html) expõe evolution_html
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                self.assertEqual(manifest["total_analyses"], 2)
                for entry in manifest["analyses"]:
                    self.assertTrue(entry["evolution_html"].endswith("evolucao.html"))
                    self.assertTrue(
                        os.path.isfile(os.path.join(tmp_root, "analise", entry["evolution_html"]))
                    )

                with open(master_html_path, "r", encoding="utf-8") as f:
                    master_html = f.read()
                self.assertIn("Evolução de Versões", master_html)
                self.assertIn("Evolução", master_html)
                self.assertIn("evolucao.html", master_html)

    def test_dispatch_reconcile_and_master_index_auto_compile_evolution(self):
        with tempfile.TemporaryDirectory() as tmp_root:
            with patch.object(server, "get_workspace_root", return_value=tmp_root):
                r1_rel, _ = _seed_workspace(tmp_root)
                rev = json.loads(server.tool_create_review_revision(r1_rel, reason="Rodada MCP", reviewer="mcp"))
                r2_rel = rev["new_analysis_path"]

                raw = server.dispatch_tool(
                    "reconcile_versions",
                    {
                        "previous_timestamp": r1_rel,
                        "current_timestamp": r2_rel,
                        "summary_notes": "Sumário via MCP dispatch",
                        "external_audit_disposition": [
                            {
                                "item_externo": "MCP-01",
                                "tema": "Item via dispatch",
                                "status": "Já Coberto",
                                "achado_id": "F-003",
                                "justificativa": "Já endereçado em F-003.",
                            }
                        ],
                    },
                )
                payload = json.loads(raw)
                self.assertEqual(payload["status"], "success")
                self.assertIn("Sumário via MCP dispatch", payload["reconciliation"]["sumario_alteracoes"])

                # Remove todos os evolucao.html para verificar auto-recompilação via build_master_index
                ver_evo = os.path.join(tmp_root, "analise", "LOTE_EVOL", "v1.2", "evolucao.html")
                r2_evo = os.path.join(tmp_root, "analise", r2_rel, "relatorios", "evolucao.html")
                for p in (ver_evo, r2_evo):
                    if os.path.exists(p):
                        os.remove(p)

                server.tool_build_master_index()
                self.assertTrue(os.path.isfile(ver_evo))
                self.assertTrue(os.path.isfile(r2_evo))
                with open(r2_evo, "r", encoding="utf-8") as f:
                    text = f.read()
                self.assertIn("Sumário via MCP dispatch", text)
                self.assertIn("MCP-01", text)


if __name__ == "__main__":
    unittest.main()
