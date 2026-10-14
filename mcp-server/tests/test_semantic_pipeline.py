from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import semantic_pipeline
import server


class SemanticPipelineTests(unittest.TestCase):
    def test_chunk_pagination_is_contiguous(self):
        source = "abcdefghijklmnop"
        first = semantic_pipeline.split_text(source, 0, 5)
        second = semantic_pipeline.split_text(source, first["next_start_char"], 5)
        third = semantic_pipeline.split_text(source, second["next_start_char"], 5)
        fourth = semantic_pipeline.split_text(source, third["next_start_char"], 5)
        self.assertEqual(first["text"] + second["text"] + third["text"] + fourth["text"], source)
        self.assertFalse(fourth["has_more"])

    def test_required_scopes_are_skill_and_document_specific(self):
        docs = [
            {"relative_path": "spec.txt", "ext": ".txt", "text": "Escopo."},
            {"relative_path": "boq.csv", "ext": ".csv", "text": "Item;Quantidade"},
            {"relative_path": "figura.png", "ext": ".png", "text": ""},
        ]
        scopes, unreadable = semantic_pipeline.build_required_scopes(
            docs, ["analisar-documento", "analisar-planilha", "analisar-diagramas"])
        self.assertEqual(scopes, [
            {"skill": "analisar-documento", "document_path": "spec.txt"},
            {"skill": "analisar-documento", "document_path": "boq.csv"},
            {"skill": "analisar-planilha", "document_path": "boq.csv"},
        ])
        self.assertEqual(unreadable, [])

    def test_quote_matching_normalizes_whitespace_but_requires_literal_words(self):
        self.assertTrue(semantic_pipeline.quote_is_literal("A API\n deve usar mTLS.", "A API deve usar mTLS."))
        self.assertFalse(semantic_pipeline.quote_is_literal("A API deve usar TLS.", "A API deve usar mTLS."))

    def test_high_finding_cannot_claim_only_e1(self):
        doc = {"name": "spec.txt", "text": "A API utiliza autenticação OAuth.", "sha256": "abc"}
        raw = {
            "skill": "analisar-integracoes", "title": "Controle ausente", "document_path": "spec.txt",
            "quote": "A API utiliza autenticação OAuth.", "tipo": "Lacuna", "evidencia": "E1",
            "criticidade": "Alta", "prioridade": "P1", "fato": "Fato", "impacto": "Impacto",
        }
        with self.assertRaisesRegex(ValueError, "E2 ou E3"):
            semantic_pipeline.normalize_semantic_finding(raw, {"spec.txt": doc}, {"analisar-integracoes"}, "lote")

    def test_e3_requires_two_baseline_quotes(self):
        doc = {"name": "spec.txt", "text": "O SLA é 99%.", "sha256": "abc"}
        raw = {
            "skill": "analisar-documento", "title": "Conflito", "document_path": "spec.txt",
            "quote": "O SLA é 99%.", "tipo": "Inconsistência", "evidencia": "E3",
            "criticidade": "Alta", "prioridade": "P1", "fato": "Fato", "impacto": "Impacto",
        }
        with self.assertRaisesRegex(ValueError, "duas citações"):
            semantic_pipeline.normalize_semantic_finding(raw, {"spec.txt": doc}, {"analisar-documento"}, "lote")

    def test_e2_rejects_empty_corroborative_reference(self):
        doc = {"name": "spec.txt", "text": "A API utiliza OAuth.", "sha256": "abc"}
        raw = {
            "skill": "analisar-documento", "title": "Controle", "document_path": "spec.txt",
            "quote": "A API utiliza OAuth.", "tipo": "Risco", "evidencia": "E2",
            "criticidade": "Média", "prioridade": "P2", "fato": "Fato", "impacto": "Impacto",
            "referencias": [{}],
        }
        with self.assertRaisesRegex(ValueError, "referência técnica corroborativa válida"):
            semantic_pipeline.normalize_semantic_finding(raw, {"spec.txt": doc}, {"analisar-documento"}, "lote")

    def test_e3_rejects_duplicate_quotes(self):
        doc = {"name": "spec.txt", "text": "O SLA é 99%.", "sha256": "abc"}
        raw = {
            "skill": "analisar-documento", "title": "Conflito", "tipo": "Inconsistência",
            "evidencia": "E3", "criticidade": "Alta", "prioridade": "P1",
            "fato": "Fato", "impacto": "Impacto",
            "evidence_sources": [
                {"document_path": "spec.txt", "quote": "O SLA é 99%.", "location": "p. 1"},
                {"document_path": "spec.txt", "quote": "O SLA é 99%.", "location": "p. 1"},
            ],
        }
        with self.assertRaisesRegex(ValueError, "duplica citação"):
            semantic_pipeline.normalize_semantic_finding(raw, {"spec.txt": doc}, {"analisar-documento"}, "lote")

    def test_semantic_review_reads_hash_verified_chunk_and_persists_finding(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            timestamp = "20261010_120000_LOTE_TESTE"
            source_rel = pathlib.Path("entrada/LOTE_TESTE/requisitos.txt")
            source_path = root / source_rel
            source_path.parent.mkdir(parents=True)
            source_text = "A interface deverá aceitar conexões TLS 1.3.\nO timeout máximo será de 2 segundos."
            source_path.write_text(source_text, encoding="utf-8")
            digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
            report_dir = root / "analise" / timestamp / "relatorios"
            report_dir.mkdir(parents=True)
            data = {
                "title": "LOTE TESTE", "timestamp": timestamp,
                "baseline_files": [{"name": "requisitos.txt", "path": "requisitos.txt", "sha256": digest, "size_bytes": source_path.stat().st_size}],
                "skills_ativas": ["analisar-documento", "analisar-cloud"], "findings": [], "lacunas": [], "riscos": [],
                "cobertura_extracao": {"arquivos": [{"arquivo": "requisitos.txt", "status": "extraido"}]},
                "kpis": {"iqd_denominador": 30}, "execucao_skills": [{"skill": "analisar-documento", "status": "executada_com_controles"}],
            }
            (report_dir / "dados_analise.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            with patch.object(server, "get_workspace_root", return_value=str(root)):
                manifest = json.loads(server.tool_get_semantic_review_manifest(timestamp))
                self.assertEqual(manifest["pending_scope_count"], 2)
                chunk = json.loads(server.tool_get_semantic_document_chunk(timestamp, "requisitos.txt", 0, 16))
                self.assertEqual(chunk["text"], source_text[:16])
                self.assertTrue(chunk["has_more"])

                finding = {
                    "skill": "analisar-documento", "rule_id": "SEM-REQ-001",
                    "title": "Parâmetro de timeout sem critério de aceite", "document_path": "requisitos.txt",
                    "localizacao_exata": "Linha 2", "categoria": "Requisitos não funcionais",
                    "tipo": "Ambiguidade", "evidencia": "E1 (trecho literal da baseline)",
                    "criticidade": "Média", "prioridade": "P2",
                    "fato": "O requisito declara um limite de timeout, sem método de medição ou critério de aceite.",
                    "impacto": "A verificação de conformidade pode variar entre implementação e aceite.",
                    "quote": "O timeout máximo será de 2 segundos.",
                }
                with patch.object(server, "tool_build_master_index", return_value=json.dumps({"status": "success", "master_html": "analise/index.html"})):
                    result = json.loads(server.tool_record_semantic_analysis(
                        timestamp,
                        [
                            {"skill": "analisar-documento", "document_path": "requisitos.txt", "status": "revisado"},
                            {"skill": "analisar-cloud", "document_path": "requisitos.txt", "status": "não_aplicável",
                             "justificativa": "O documento não descreve componentes nem serviços de nuvem."},
                        ],
                        [finding],
                    ))
                self.assertEqual(result["semantic_status"], "concluída")
                self.assertEqual(result["findings_added"], 1)
                updated = json.loads((report_dir / "dados_analise.json").read_text(encoding="utf-8"))
                self.assertEqual(updated["findings"][0]["semantic_skill"], "analisar-documento")
                self.assertEqual(updated["findings"][0]["adjudication_status"], "pendente")
                self.assertEqual(updated["findings"][0]["evidence_sources"][0]["sha256"], digest)
                compiled_html = (report_dir / "index.html").read_text(encoding="utf-8")
                self.assertIn("Rastreabilidade semântica", compiled_html)
                self.assertIn("Parâmetro de timeout sem critério de aceite", compiled_html)
                self.assertIn("Revisão semântica especializada", compiled_html)
                final_manifest = json.loads(server.tool_get_semantic_review_manifest(timestamp))
                cloud_scope = final_manifest["skills"]["analisar-cloud"][0]
                self.assertEqual(cloud_scope["status"], "não_aplicável")
                self.assertIn("não descreve", cloud_scope["justificativa"])

    def test_semantic_chunk_rejects_changed_baseline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            timestamp = "20261010_120000_LOTE_TESTE"
            source_path = root / "entrada" / "LOTE_TESTE" / "requisitos.txt"
            source_path.parent.mkdir(parents=True)
            source_path.write_text("Conteúdo alterado", encoding="utf-8")
            report_dir = root / "analise" / timestamp / "relatorios"
            report_dir.mkdir(parents=True)
            data = {"timestamp": timestamp, "baseline_files": [{
                "name": "requisitos.txt", "path": "requisitos.txt", "sha256": "0" * 64,
            }]}
            (report_dir / "dados_analise.json").write_text(json.dumps(data), encoding="utf-8")
            with patch.object(server, "get_workspace_root", return_value=str(root)):
                with self.assertRaisesRegex(ValueError, "Integridade da baseline divergente"):
                    server.tool_get_semantic_document_chunk(timestamp, "requisitos.txt")


if __name__ == "__main__":
    unittest.main()
