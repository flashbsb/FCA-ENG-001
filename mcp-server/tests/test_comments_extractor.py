"""
Testes unitários para o extrator e triangulador de comentários (DOCX e PDF).
"""

import os
import json
import zipfile
import tempfile
import unittest
from pathlib import Path

from comments_extractor import (
    extract_docx_comments,
    extract_all_comments_from_lote,
    export_comments_artifacts
)


class TestCommentsExtractor(unittest.TestCase):

    def test_extract_docx_comments_with_anchor_text(self):
        """Valida que comentários em .docx são extraídos com seus respectivos textos âncoras."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_file = os.path.join(tmpdir, "documento_teste.docx")

            doc_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r><w:t>O sistema utilizará arquitetura </w:t></w:r>
      <w:commentRangeStart w:id="1"/>
      <w:r><w:t>monolítica em servidor único</w:t></w:r>
      <w:commentRangeEnd w:id="1"/>
      <w:r><w:commentReference w:id="1"/></w:r>
      <w:r><w:t> para atender 1 milhão de usuários.</w:t></w:r>
    </w:p>
  </w:body>
</w:document>"""

            comments_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:comment w:id="1" w:author="Eng. Roberto" w:date="2026-10-15T10:00:00Z">
    <w:p>
      <w:r><w:t>Atenção: viola requisito de alta disponibilidade N+1 do Edital.</w:t></w:r>
    </w:p>
  </w:comment>
</w:comments>"""

            with zipfile.ZipFile(docx_file, "w") as z:
                z.writestr("word/document.xml", doc_xml)
                z.writestr("word/comments.xml", comments_xml)

            comments = extract_docx_comments(docx_file)
            self.assertEqual(len(comments), 1)
            c = comments[0]
            self.assertEqual(c["autor"], "Eng. Roberto")
            self.assertEqual(c["item_referenciado"], "monolítica em servidor único")
            self.assertIn("viola requisito de alta disponibilidade", c["comentario"])
            self.assertEqual(c["status_triangulacao"], "PENDENTE")

    def test_export_comments_artifacts_isolation(self):
        """Valida que artefatos de comentários são salvos apenas na pasta de relatórios designada."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sample_comments = [
                {
                    "id_anotacao": "COM-001",
                    "documento": "HLD.docx",
                    "pagina_ou_secao": "Corpo",
                    "autor": "Auditor",
                    "data_hora": "2026-10-19",
                    "tipo_anotacao": "Comentário Word",
                    "item_referenciado": "trecho x",
                    "comentario": "dúvida sobre SLA",
                    "status_triangulacao": "PENDENTE",
                    "parecer_triangulacao": "",
                    "achado_id_associado": None
                }
            ]
            rel_dir = os.path.join(tmpdir, "relatorios")
            paths = export_comments_artifacts(sample_comments, rel_dir)

            self.assertTrue(os.path.isfile(paths["json"]))
            self.assertTrue(os.path.isfile(paths["csv"]))

            with open(paths["json"], "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["id_anotacao"], "COM-001")


if __name__ == "__main__":
    unittest.main()
