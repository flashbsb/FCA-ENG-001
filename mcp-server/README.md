# Servidor MCP | doc-audit-framework (FCA-ENG-001)

Este módulo fornece um servidor **MCP (Model Context Protocol)** nativo em Python (STDIO / JSON-RPC 2.0) com **Zero Dependências Obrigatórias**, compatível com Python 3.9+ e pronto para uso no Antigravity, Cursor, Claude Desktop ou VS Code.

---

## 🛠️ Ferramentas (Tools) Expostas pelo Servidor MCP

| Ferramenta MCP | Descrição |
|---|---|
| `profile_baseline` | Realiza a triagem adaptativa de `entrada/`: detecta domínios, mapeia checklists ativos/inaplicáveis, audita o ambiente (SO/Python) e recomenda skills. |
| `check_environment` | Audita proativamente dependências Python e utilitários do SO (poppler-utils, tesseract-ocr) e sugere comandos para destravar 100% de capacidade. |
| `run_full_audit` | Executa os controles determinísticos, prepara o SSOT/HTML, baseline com hashes e matriz de escopos semânticos pendentes. |
| `get_semantic_review_manifest` | Expõe a matriz skill/documento, progresso e achados existentes para orientar as passagens semânticas do modelo revisor. |
| `get_semantic_document_chunk` | Entrega blocos paginados com localização e SHA-256 conferido contra a baseline imutável. |
| `record_semantic_analysis` | Valida citações e skills ativas; persiste os escopos/achados semânticos e recompila relatório e índice central. |
| `adjudicate_findings` | Registra confirmação, falso positivo, fora de escopo, duplicidade ou pendência; exige justificativa e valida evidência/hash antes de confirmar. |
| `get_visual_assets` / `record_visual_analysis` | Entrega imagens/diagramas ao modelo e registra inspeção visual rastreável em separado. |
| `analyze_structural_integrity` | Executa a verificação determinística e exaustiva dos 7 pilares estruturais e redacionais sobre os documentos. |
| `scaffold_skill` | Gera o rascunho de uma nova skill em `.agents/skills/<skill_name>/SKILL.md` para validação e aprovação do usuário. |
| `freeze_baseline` | Varre a pasta `entrada/`, calcula hashes SHA-256 de todas as extensões e retorna o inventário imutável em JSON. |
| `extract_docx_summary` | Extrai a quantidade de parágrafos, tabelas e mídias de um arquivo `.docx` em `entrada/`. |
| `extract_xlsx_summary` | Extrai abas, cabeçalhos e amostra de dados de um arquivo `.xlsx` em `entrada/`. |
| `validate_analise_contract` | Valida se os entregáveis da RTI (`index.html` e `dados_analise.json`) existem em `analise/<timestamp>/relatorios/` e verifica a cobertura de skills. |
| `build_run_index_html` | Recompila o dashboard HTML de uma análise individual a partir do `dados_analise.json` SSOT. |
| `finalize_execution` | Finaliza a análise: move os arquivos de `entrada/` para `analise/<timestamp>/entrada/` e atualiza a Central `analise/index.html`. |
| `build_master_index` | Varre a pasta `analise/`, atualiza o arquivo `analise/manifest.json` e recompila a Central de Análises Master `analise/index.html`. |

> O MCP não chama um modelo externo: a leitura semântica e o julgamento técnico são executados pelo modelo chamador, seguindo as skills ativas. Achados sem decisão são tratados como pendentes; somente confirmados entram no parecer, IQD, riscos e ações. O servidor valida citações/hash e mantém a adjudicação auditável no SSOT.

---

## 🚀 Como Ativar no Seu Ambiente (Antigravity / Cursor / Claude Desktop / VS Code)

### 1. Pré-requisitos
- Python 3.9+ (utiliza bibliotecas nativas da linguagem, sem necessidade de `pip install` obrigatório).

### 2. Configuração do MCP
Basta adicionar o bloco abaixo no arquivo de configuração de MCPs da sua IDE (ex: `antigravity.json`, `claude_desktop_config.json` ou `cursor.json`):

```json
{
  "mcpServers": {
    "doc-audit-framework": {
      "command": "python3",
      "args": [
        "/caminho/absoluto/para/doc-audit-framework/mcp-server/server.py"
      ]
    }
  }
}
```

### 3. Teste Local via Linha de Comando (CLI)
Você pode testar a execução direta das ferramentas no terminal executando:
```bash
python3 mcp-server/server.py
```
