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


if __name__ == "__main__":
    unittest.main()
