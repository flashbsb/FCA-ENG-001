from __future__ import annotations

import json
import pathlib
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "mcp-server"))

import semantic_pipeline
import server


class DocumentRoleSegregationTests(unittest.TestCase):
    def test_classify_batch_document_roles_auto_explicit_and_external(self):
        lote_name = "01 - High Level Design Enterprise SDWAN"
        files = [
            "High Level Design Enterprise SDWAN v1.2.pdf",
            "HLD Enterprise Gerencia v1.4.pdf",
            "HLD_DCN-v1.0.pdf",
            "High_Level_Design_Enterprise_SDWAN_v1_2_pdf_Relatorio_Analise_Externo_v1.1_20261109_152500.html",
            "insumos_externos/nota_revisao.md",
        ]
        roles = server._classify_batch_document_roles(lote_name, files)
        self.assertEqual(roles["High Level Design Enterprise SDWAN v1.2.pdf"], "alvo_principal")
        self.assertEqual(roles["HLD Enterprise Gerencia v1.4.pdf"], "apoio_cruzamento")
        self.assertEqual(roles["HLD_DCN-v1.0.pdf"], "apoio_cruzamento")
        self.assertEqual(
            roles["High_Level_Design_Enterprise_SDWAN_v1_2_pdf_Relatorio_Analise_Externo_v1.1_20261109_152500.html"],
            "insumo_externo",
        )
        self.assertEqual(roles["insumos_externos/nota_revisao.md"], "insumo_externo")

        # Empate (todos sem interseção com nome genérico de lote) -> todos são alvo_principal
        peer_roles = server._classify_batch_document_roles(
            "lote-exemplo-rfp",
            ["RFP_Principal.pdf", "Anexo_SLA.docx", "BoM.xlsx"],
        )
        self.assertEqual(
            peer_roles,
            {
                "RFP_Principal.pdf": "alvo_principal",
                "Anexo_SLA.docx": "alvo_principal",
                "BoM.xlsx": "alvo_principal",
            },
        )

        # Sobrescrita explícita via primary_files
        override_roles = server._classify_batch_document_roles(
            lote_name, files, primary_files=["HLD_DCN-v1.0.pdf"]
        )
        self.assertEqual(override_roles["HLD_DCN-v1.0.pdf"], "alvo_principal")
        self.assertEqual(override_roles["High Level Design Enterprise SDWAN v1.2.pdf"], "apoio_cruzamento")

    def test_build_required_scopes_focuses_on_alvo_principal_and_keeps_planilha(self):
        docs = [
            {"relative_path": "alvo.pdf", "ext": ".pdf", "role": "alvo_principal", "text": "HLD principal."},
            {"relative_path": "apoio.pdf", "ext": ".pdf", "role": "apoio_cruzamento", "text": "HLD de apoio."},
            {"relative_path": "bom.xlsx", "ext": ".xlsx", "role": "apoio_cruzamento", "text": "Item|Qtd\nA|1"},
            {"relative_path": "ext.html", "ext": ".html", "role": "insumo_externo", "text": "Relatório externo."},
        ]
        scopes, unreadable = semantic_pipeline.build_required_scopes(
            docs, ["analisar-documento", "analisar-hld", "analisar-planilha"]
        )
        self.assertEqual(
            scopes,
            [
                {"skill": "analisar-documento", "document_path": "alvo.pdf"},
                {"skill": "analisar-hld", "document_path": "alvo.pdf"},
                {"skill": "analisar-planilha", "document_path": "bom.xlsx"},
            ],
        )
        self.assertEqual(unreadable, [])

    def test_normalize_semantic_finding_anchors_on_alvo_principal(self):
        docs_by_path = {
            "apoio.txt": {
                "name": "apoio.txt",
                "relative_path": "apoio.txt",
                "role": "apoio_cruzamento",
                "text": "O padrão oficial da rede exige DSCP CS6.",
                "sha256": "a" * 64,
            },
            "alvo.txt": {
                "name": "alvo.txt",
                "relative_path": "alvo.txt",
                "role": "alvo_principal",
                "text": "O firewall marca pacotes com DSCP CS2.",
                "sha256": "b" * 64,
            },
        }
        raw = {
            "skill": "analisar-carrier",
            "title": "Divergência de DSCP no tráfego de gerência",
            "tipo": "Inconsistência",
            "evidencia": "E3 (confronto direto)",
            "criticidade": "Alta",
            "prioridade": "P1",
            "fato": "O alvo usa CS2 enquanto a especificação de apoio exige CS6.",
            "impacto": "Perda de priorização QoS.",
            "evidence_sources": [
                {"document_path": "apoio.txt", "location": "Linha 1", "quote": "O padrão oficial da rede exige DSCP CS6."},
                {"document_path": "alvo.txt", "location": "Linha 1", "quote": "O firewall marca pacotes com DSCP CS2."},
            ],
        }
        normalized = semantic_pipeline.normalize_semantic_finding(
            raw, docs_by_path, {"analisar-carrier"}, "lote_teste"
        )
        self.assertEqual(normalized["doc_origem"], "alvo.txt")
        self.assertEqual(normalized["documento"], "alvo.txt")
        self.assertEqual(normalized["doc_path"], "alvo.txt")
        self.assertEqual(len(normalized["evidence_sources"]), 2)

    def test_end_to_end_run_full_audit_and_semantic_cross_ref_roles(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            lote_dir = root / "entrada" / "01 - HLD SDWAN Teste"
            lote_dir.mkdir(parents=True)
            (root / "analise").mkdir(parents=True)

            # Copiar templates e checklists necessários
            shutil.copytree(REPO_ROOT / "framework" / "templates", root / "framework" / "templates")
            shutil.copytree(REPO_ROOT / "framework" / "checklists", root / "framework" / "checklists")

            target_file = lote_dir / "HLD SDWAN Teste v1.2.txt"
            target_file.write_text(
                "High Level Design (HLD) SD-WAN Teste.\n"
                "Objetivo e escopo da arquitetura de transporte MPLS e SD-WAN.\n"
                "A disponibilidade contratada e SLA global é de 99.9%.\n"
                "O cluster de HA utiliza switches centrais. Detalhes TBD.\n",
                encoding="utf-8",
            )
            support_file = lote_dir / "HLD Gerencia v1.4.txt"
            support_file.write_text(
                "HLD Gerencia Central.\n"
                "Topologia com cluster em HA sem definição adicional.\n"
                "A disponibilidade e SLA da gerência exige 99.5%.\n"
                "Parâmetro interno marcado como TBD no documento de apoio.\n",
                encoding="utf-8",
            )
            external_file = lote_dir / "HLD_SDWAN_Relatorio_Analise_Externo_v1.0.html"
            external_file.write_text(
                "<html><body><p>SLA sugerido 95.0% TBD</p></body></html>",
                encoding="utf-8",
            )

            with patch.object(server, "get_workspace_root", return_value=str(root)):
                audit_res = json.loads(server.tool_run_full_audit(lote_path="entrada/01 - HLD SDWAN Teste"))
                self.assertEqual(audit_res["status"], "success")
                ts = audit_res["lotes_processed"][0]["timestamp"]
                rel_dir = root / "analise" / ts / "relatorios"
                data = json.loads((rel_dir / "dados_analise.json").read_text(encoding="utf-8"))

                # Insumo externo foi segregado da baseline normativa
                baseline_names = [bf["name"] for bf in data["baseline_files"]]
                self.assertIn("HLD SDWAN Teste v1.2.txt", baseline_names)
                self.assertIn("HLD Gerencia v1.4.txt", baseline_names)
                self.assertNotIn("HLD_SDWAN_Relatorio_Analise_Externo_v1.0.html", baseline_names)
                self.assertEqual(len(data["external_inputs"]), 1)
                self.assertEqual(
                    data["external_inputs"][0]["name"],
                    "HLD_SDWAN_Relatorio_Analise_Externo_v1.0.html",
                )

                # Nenhum achado isolado originado em HLD Gerencia v1.4.txt
                finding_docs = {f["doc_origem"] for f in data["findings"]}
                self.assertEqual(finding_docs, {"HLD SDWAN Teste v1.2.txt"})

                # O conflito cruzado de SLA foi capturado e ancorado no alvo principal
                xref_sla = [f for f in data["findings"] if f.get("rule_id") == "XREF-SLA"]
                self.assertEqual(len(xref_sla), 1)
                self.assertEqual(xref_sla[0]["doc_origem"], "HLD SDWAN Teste v1.2.txt")
                self.assertEqual(len(xref_sla[0]["evidence_sources"]), 2)

                # Manifest semântico cobra apenas escopos do documento-alvo principal
                manifest = json.loads(server.tool_get_semantic_review_manifest(ts))
                doc_skill_targets = [row["document_path"] for row in manifest["skills"]["analisar-documento"]]
                self.assertEqual(doc_skill_targets, ["HLD SDWAN Teste v1.2.txt"])

                # Registro semântico com confronto E3 entre apoio (1º) e alvo (2º)
                scopes_to_mark = [
                    {"skill": sk, "document_path": row["document_path"], "status": "revisado"}
                    for sk, rows in manifest["skills"].items()
                    for row in rows
                ]
                sem_res = json.loads(
                    server.tool_record_semantic_analysis(
                        ts,
                        scopes_to_mark,
                        [
                            {
                                "skill": "analisar-hld",
                                "rule_id": "SEM-XREF-TEST",
                                "title": "Divergência de SLA de disponibilidade entre SD-WAN e Gerência",
                                "tipo": "Inconsistência",
                                "evidencia": "E3 (confronto direto)",
                                "criticidade": "Alta",
                                "prioridade": "P1",
                                "fato": "Metas distintas de SLA (99.9% vs 99.5%) entre os dois HLDs.",
                                "impacto": "Ambiguidade nos critérios de aceite.",
                                "evidence_sources": [
                                    {
                                        "document_path": "HLD Gerencia v1.4.txt",
                                        "location": "Linha 3",
                                        "quote": "A disponibilidade e SLA da gerência exige 99.5%.",
                                    },
                                    {
                                        "document_path": "HLD SDWAN Teste v1.2.txt",
                                        "location": "Linha 3",
                                        "quote": "A disponibilidade contratada e SLA global é de 99.9%.",
                                    },
                                ],
                            }
                        ],
                    )
                )
                self.assertEqual(sem_res["status"], "success")
                updated = json.loads((rel_dir / "dados_analise.json").read_text(encoding="utf-8"))
                sem_finding = next(f for f in updated["findings"] if f.get("rule_id") == "SEM-XREF-TEST")
                self.assertEqual(sem_finding["doc_origem"], "HLD SDWAN Teste v1.2.txt")

                contract = json.loads(server.tool_validate_analise_contract(ts))
                self.assertEqual(contract["missing"], [])

                compiled_html = (rel_dir / "index.html").read_text(encoding="utf-8")
                self.assertIn("Papel no Lote", compiled_html)
                self.assertIn("Documento-Alvo Principal", compiled_html)
                self.assertIn("Apoio / Confronto Cruzado", compiled_html)
                self.assertIn("Insumos Externos de Auditoria Cruzada", compiled_html)


if __name__ == "__main__":
    unittest.main()
