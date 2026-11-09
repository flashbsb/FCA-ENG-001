from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "mcp-server"))

import server


class FindingAdjudicationTests(unittest.TestCase):
    def test_adjudication_tool_is_registered_and_dispatched(self):
        tool = next(item for item in server.TOOLS_MANIFEST if item["name"] == "adjudicate_findings")
        self.assertIn("decisions", tool["inputSchema"]["properties"])
        with patch.object(server, "tool_adjudicate_findings", return_value="ok") as handler:
            self.assertEqual(server.dispatch_tool("adjudicate_findings", {"timestamp": "t", "decisions": []}), "ok")
            handler.assert_called_once_with("t", [])

    def _fixture(self, root: pathlib.Path, timestamp: str = "20261010_120000_LOTE_TESTE") -> tuple[pathlib.Path, pathlib.Path]:
        source_rel = pathlib.Path("entrada/LOTE_TESTE/requisitos.txt")
        source_path = root / source_rel
        source_path.parent.mkdir(parents=True)
        source_text = "A API deverá usar TLS 1.3.\nA API pode utilizar mTLS."
        source_path.write_text(source_text, encoding="utf-8")
        digest = hashlib.sha256(source_path.read_bytes()).hexdigest()

        report_dir = root / "analise" / timestamp / "relatorios"
        report_dir.mkdir(parents=True)
        data = {
            "title": "LOTE TESTE", "timestamp": timestamp,
            "baseline_files": [{
                "name": "requisitos.txt", "path": "requisitos.txt", "sha256": digest,
                "size_bytes": source_path.stat().st_size,
            }],
            "skills_ativas": ["analisar-documento"],
            "findings": [
                {
                    "id": "FIND-1", "title": "Requisito de mTLS não definido", "tipo": "Lacuna",
                    "criticidade": "Média", "prioridade": "P2", "evidencia": "E1",
                    "doc_origem": "requisitos.txt", "doc_path": "requisitos.txt", "loc": "Linha 2",
                    "fato": "O texto admite mTLS sem exigir esse método.", "impacto": "A autenticação pode variar.",
                    "evidence_sources": [{
                        "document_path": "requisitos.txt", "location": "Linha 2",
                        "quote": "A API pode utilizar mTLS.", "sha256": digest,
                    }],
                },
                {
                    "id": "FIND-2", "title": "Controle crítico fora da baseline", "tipo": "Lacuna",
                    "criticidade": "Crítica", "prioridade": "P0", "evidencia": "E1",
                    "doc_origem": "requisitos.txt", "loc": "Escopo genérico",
                    "fato": "Candidato sem localização específica.", "impacto": "Pode inflar o parecer.",
                },
            ],
            "lacunas": [], "riscos": [], "redacoes": [], "esclarecimentos": [],
            "visual_inventory": {"assets": []}, "visual_analysis": {"assets_reviewed": []},
            "kpis": {"iqd_denominador": 30},
        }
        (report_dir / "dados_analise.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        template_dir = root / "framework" / "templates"
        template_dir.mkdir(parents=True)
        shutil.copyfile(REPO_ROOT / "framework" / "templates" / "master_index_template.html", template_dir / "master_index_template.html")
        return report_dir, source_path

    def test_confirmed_and_pending_findings_are_separated_in_reports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            report_dir, _ = self._fixture(root)
            timestamp = "20261010_120000_LOTE_TESTE"
            with patch.object(server, "get_workspace_root", return_value=str(root)):
                result = json.loads(server.tool_adjudicate_findings(timestamp, [
                    {
                        "finding_id": "FIND-1", "status": "confirmado",
                        "rationale": "Citação literal localizada na linha indicada e pertinente ao requisito.",
                    },
                    {
                        "finding_id": "FIND-2", "status": "pendente",
                        "rationale": "",
                    },
                ]))

                self.assertEqual(result["parecer"], "PENDENTE DE ADJUDICAÇÃO")
                self.assertEqual(result["pending_adjudication"], 1)
                updated = json.loads((report_dir / "dados_analise.json").read_text(encoding="utf-8"))
                self.assertEqual(updated["kpis"]["achados_confirmados"], 1)
                self.assertEqual(updated["kpis"]["achados_pendentes_adjudicacao"], 1)
                self.assertEqual(updated["kpis"]["criticos"], 0)
                self.assertEqual(updated["kpis"]["iqd"], "—")
                self.assertEqual(updated["parecer"], "PENDENTE DE ADJUDICAÇÃO")
                self.assertEqual(updated["findings"][0]["adjudication"]["status"], "confirmado")
                self.assertTrue(updated["findings"][0]["adjudication"]["adjudicated_at"])

                html = (report_dir / "index.html").read_text(encoding="utf-8")
                master = (root / "analise" / "index.html").read_text(encoding="utf-8")
                self.assertIn("Pendente de adjudicação", html)
                self.assertIn("Confirmado", html)
                self.assertIn("PENDENTE DE ADJUDICAÇÃO", master)
                self.assertIn("Pendentes", master)

                result = json.loads(server.tool_adjudicate_findings(timestamp, [{
                    "finding_id": "FIND-2", "status": "fora_de_escopo",
                    "rationale": "A exigência não pertence ao escopo declarado desta baseline documental.",
                }]))
                self.assertEqual(result["pending_adjudication"], 0)
                self.assertEqual(result["parecer"], "APTO COM RESSALVAS")
                updated = json.loads((report_dir / "dados_analise.json").read_text(encoding="utf-8"))
                self.assertEqual(updated["kpis"]["criticos"], 0)
                self.assertEqual(updated["kpis"]["achados_excluidos"], 1)
                self.assertEqual(updated["findings"][1]["adjudication"]["status"], "fora_de_escopo")

    def test_master_build_migrates_legacy_findings_as_pending(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            report_dir, _ = self._fixture(root)
            with patch.object(server, "get_workspace_root", return_value=str(root)):
                result = json.loads(server.tool_build_master_index())
            updated = json.loads((report_dir / "dados_analise.json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "success")
            self.assertEqual(updated["parecer"], "PENDENTE DE ADJUDICAÇÃO")
            self.assertEqual(updated["decision_status"], "pendente_adjudicacao")
            self.assertEqual(updated["kpis"]["achados_pendentes_adjudicacao"], 2)
            self.assertEqual(updated["kpis"]["criticos"], 0)
            self.assertEqual(updated["kpis"]["iqd"], "—")
            individual = (report_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn("Pendente de adjudicação", individual)

    def test_confirmation_rejects_non_literal_evidence_without_persisting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            report_dir, _ = self._fixture(root)
            timestamp = "20261010_120000_LOTE_TESTE"
            invalid_source = [{
                "document_path": "requisitos.txt", "location": "Linha 2",
                "quote": "A API exige mTLS.",
            }]
            with patch.object(server, "get_workspace_root", return_value=str(root)):
                with self.assertRaisesRegex(ValueError, "não localizada literalmente"):
                    server.tool_adjudicate_findings(timestamp, [{
                        "finding_id": "FIND-1", "status": "confirmado",
                        "rationale": "A citação foi analisada, mas o texto proposto não é literal.",
                        "evidence_sources": invalid_source,
                    }])
            unchanged = json.loads((report_dir / "dados_analise.json").read_text(encoding="utf-8"))
            self.assertNotIn("adjudication", unchanged["findings"][0])
            with patch.object(server, "get_workspace_root", return_value=str(root)):
                with self.assertRaisesRegex(ValueError, "críticos/altos exigem evidência E2 ou E3"):
                    server.tool_adjudicate_findings(timestamp, [{
                        "finding_id": "FIND-2", "status": "confirmado",
                        "rationale": "O trecho foi encontrado, mas o grau de evidência declarado é insuficiente.",
                        "evidence_sources": [{
                            "document_path": "requisitos.txt", "location": "Linha 1",
                            "quote": "A API deverá usar TLS 1.3.",
                        }],
                    }])
            unchanged = json.loads((report_dir / "dados_analise.json").read_text(encoding="utf-8"))
            self.assertNotIn("adjudication", unchanged["findings"][1])

    def test_reconcile_versions_distinguishes_sanados_reincidentes_and_novos(self):
        import audit_engine
        json_antigo = {
            "timestamp": "20261010_100000_LOTE_V1",
            "parecer_badge": "NÃO APTO",
            "kpis": {"iqd": "70.0%"},
            "findings": [
                {
                    "id": "CAR-001",
                    "title": "Ausência de margem OSNR na camada DWDM",
                    "categoria": "Carrier Telecom & DCN",
                    "criticidade": "Alta",
                    "prioridade": "P1",
                    "loc": "Seção 3.1",
                },
                {
                    "id": "CAR-002",
                    "title": "Falta de proteção LFA/TI-LFA no backbone MPLS",
                    "categoria": "Carrier Telecom & DCN",
                    "criticidade": "Crítica",
                    "prioridade": "P0",
                    "loc": "Seção 4.2",
                },
            ],
        }
        json_novo = {
            "timestamp": "20261011_100000_LOTE_V2",
            "parecer_badge": "APTO COM RESSALVAS",
            "kpis": {"iqd": "88.0%"},
            "findings": [
                {
                    "id": "CAR-010",
                    "title": "Ausência de margem OSNR na camada DWDM",
                    "categoria": "Carrier Telecom & DCN",
                    "criticidade": "Alta",
                    "prioridade": "P1",
                    "loc": "Seção 3.2",
                },
                {
                    "id": "CAR-020",
                    "title": "Timer BFD acima de 50ms em enlaces críticos",
                    "categoria": "Carrier Telecom & DCN",
                    "criticidade": "Média",
                    "prioridade": "P2",
                    "loc": "Seção 5.1",
                },
            ],
        }
        diff = audit_engine.reconcile_versions(json_antigo, json_novo)
        self.assertEqual(diff["achados_sanados_count"], 1)
        self.assertEqual(diff["achados_reincidentes_count"], 1)
        self.assertEqual(diff["novos_achados_count"], 1)
        self.assertEqual(diff["sanados"][0]["id_anterior"], "CAR-002")
        self.assertEqual(diff["reincidentes"][0]["id_anterior"], "CAR-001")
        self.assertEqual(diff["novos"][0]["id_atual"], "CAR-020")
        self.assertEqual(diff["delta_iqd"], "+18.0%")

    def test_triple_hierarchy_path_and_create_review_revision(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            report_dir, _ = self._fixture(root)
            timestamp = "20261010_120000_LOTE_TESTE"
            with patch.object(server, "get_workspace_root", return_value=str(root)):
                rev_res = json.loads(server.tool_create_review_revision(
                    timestamp, reason="Adjudicação de revisão técnica", reviewer="auditor_senior"
                ))
                self.assertEqual(rev_res["status"], "success")
                rev_path = rev_res["new_analysis_path"]
                self.assertEqual(len(rev_path.split("/")), 3)

                manifest = json.loads(server.tool_get_semantic_review_manifest(rev_path))
                self.assertEqual(manifest["status"], "success")

                adj_res = json.loads(server.tool_adjudicate_findings(rev_path, [
                    {
                        "finding_id": "FIND-1",
                        "status": "confirmado",
                        "rationale": "Trecho confirmado literalmente na linha 2 do arquivo da baseline.",
                    },
                    {
                        "finding_id": "FIND-2",
                        "status": "falso_positivo",
                        "rationale": "Exigência não aplicável ao escopo do lote analisado.",
                    },
                ]))
                self.assertEqual(adj_res["pending_adjudication"], 0)
                rev_html = (root / "analise" / rev_path / "relatorios" / "index.html").read_text(encoding="utf-8")
                self.assertIn('href="../../../../index.html"', rev_html)

    def test_all_26_checklists_and_structural_7_pillars(self):
        self.assertEqual(len(server.ALL_CHECKLISTS), 26)
        with tempfile.TemporaryDirectory() as temp_dir:
            doc_path = pathlib.Path(temp_dir) / "especificacao.md"
            doc_path.write_text(
                "1.1 Introdução\nTexto inicial.\n1.3 Arquitetura\n"
                "Conforme Tabela 9, a taxa é de 10 Gbps ou 10 GB/s.\n",
                encoding="utf-8",
            )
            findings = server.analyze_document_structure(str(doc_path))
            ids = {f["id"] for f in findings}
            self.assertIn("EDIT-007", ids)
            self.assertIn("EDIT-008", ids)
            self.assertIn("EDIT-009", ids)


if __name__ == "__main__":
    unittest.main()
