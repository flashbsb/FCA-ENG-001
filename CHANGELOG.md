# Changelog — Framework MCP FCA-ENG-001

Todas as alterações graduais, correções e melhorias arquiteturais implementadas no framework corporativo **FCA-ENG-001** de Revisão Técnica Independente (RTI) estão documentadas neste arquivo, adotando versionamento semântico.

---

## [1.4.0] - 2026-11-09
### Adicionado
- **Ferramenta MCP de Reconciliação de Versões (`reconcile_versions` / `tool_reconcile_versions`):**
  - Exposição da função `reconcile_versions` no manifesto MCP (`TOOLS_MANIFEST`) e no despachante `dispatch_tool` em `mcp-server/server.py`.
  - Persistência automática do bloco `version_reconciliation` no `dados_analise.json` da versão atual e recompilação imediata do `index.html`.
  - Renderização visual do **Quadro de Reconciliação Técnica e Evolução (Diff de Versões)** na Seção 1 (`_build_resumo_html`) de `mcp-server/html_compiler.py`, exibindo KPIs evolutivos (IQD Anterior vs. Atual, Δ IQD, Taxa de Resolução e contagens de achados Sanados, Reincidentes e Novos/Regressões).
- **Controles Determinísticos dos 7 Pilares Estruturais e Editoriais (`analyze_document_structure`):**
  - `EDIT-007`: Detecção de saltos na sequência numérica de seções (ex.: `3.1` → `3.3`) — Pilar 1.
  - `EDIT-008`: Detecção de referências cruzadas órfãs a Tabelas e Figuras citadas no corpo do texto sem legenda/definição correspondente — Pilar 3.
  - `EDIT-009`: Detecção de coexistência ambígua de unidades de taxa de transferência/capacidade (`Gbps` vs `GB/s`, `Mbps` vs `MB/s`) — Pilar 7 (ISO 80000).
- **Cobertura Integral dos 26 Checklists Técnicos:**
  - Mapeamento completo de `rfp.md`, `hld.md`, `lld.md`, `lgpd.md` e `planilha.md` em `CHECKLIST_DOMAIN_MAP`, `ALL_CHECKLISTS` e `get_active_checklists` (`mcp-server/server.py`) e em `RULE_PREFIX_CHECKLIST_MAP`, `SKILL_CHECKLIST_MAP` e `AUTOMATED_CHECKLISTS` (`mcp-server/audit_pipeline.py`).
- **Expansão da Suíte de Testes Unitários (`mcp-server/tests/test_adjudication.py`):**
  - Novos testes automatizados cobrindo reconciliação entre versões (`reconcile_versions`), resolução de caminhos na hierarquia tripla (`<lote>/<version>/<timestamp>`), criação de revisão com subpastas (`create_review_revision`) e ativação dos 26 checklists + 7 pilares estruturais.

### Corrigido
- **Preservação de Adjudicações e Metadados na Recompilação (`mcp-server/audit_engine.py`):**
  - `generate_6_reports` agora preserva integralmente os atributos `adjudication`, `adjudication_status`, `texto_afirmado`, `diagrama_demonstrado` nos achados, bem como `adjudication_summary`, `decision_status`, `audit_trail`, `parent_analysis`, `version_reconciliation` e `metadata` no nível raiz do `dados_analise.json`.
  - `calculate_iqd` e `calculate_parecer` corrigidos para ler tanto `'crit'`/`'criticidade'` quanto `'prio'`/`'prioridade'`, garantindo recálculo fiel após adjudicações ou inserções de achados semânticos/visuais.
  - `reconcile_versions` corrigido para ler tanto `'title'`/`'titulo'` quanto `'loc'`/`'localizacao'`, evitando colisões com chaves vazias.
- **Suporte Universal à Hierarquia Tripla (`<lote>/<version>/<timestamp>`) em Todas as Tools MCP:**
  - Unificação da validação `_is_valid_analysis_identifier` (com bloqueio estrito de segmentos `.` e `..`) e da resolução `_resolve_analysis_dirs` em `tool_get_visual_assets`, `tool_record_visual_analysis`, `tool_get_semantic_review_manifest`, `tool_get_semantic_document_chunk`, `_resolve_baseline_document`, `_refresh_analysis_outputs`, `tool_adjudicate_findings` e `tool_record_semantic_analysis`.
  - Cópia e movimentação recursiva de subpastas da baseline (incluindo `visuais/` e anexos aninhados) em `tool_finalize_execution` e `tool_create_review_revision`.
  - Cálculo dinâmico do link relativo `../../index.html` / `../../../index.html` para o Portal Master em `compile_timestamp_html`.
- **Alinhamento de Chaves do Caderno de Perguntas Formais (Seção 5 do HTML):**
  - Compatibilização entre `tool_run_full_audit` e `_build_acoes_html` para suportar simultaneamente `id`/`id_pergunta`, `doc`/`doc_ref`, `secao_ref` e `impacto`/`justificativa`.
- **Extração de Texto `.docx` e `.pdf` com Preservação de Parágrafos:**
  - Unificação de `extract_text_from_file` em `mcp-server/server.py` para utilizar `extract_docx_text` e `extract_pdf_text`, preservando quebras de linha essenciais para os controles estruturais e normativos.
- **Remoção de Falso Positivo `DIA-NOME` e de Hardcodes Legados:**
  - Desativação da regra `DIA-NOME` em `mcp-server/specialized_controls.py`, alinhando o motor à diretriz de `analisar-diagramas/SKILL.md`.
  - Remoção de substituições de texto específicas de projetos legados em `clean_unicode_text` e centralização de `sanitize_batch_isolation` e `clean_unicode_text` em `mcp-server/audit_pipeline.py`.

### Segurança
- **Sanitização HTML em Atributos e Filtros (`mcp-server/html_compiler.py`):**
  - Aplicação de `html.escape(..., quote=True)` nos atributos `data-*` das linhas da Matriz Master SSOT e nas opções `<option>` de documentos no filtro interativo.

### Documentação
- **Padronização de Documentação, Normas, Checklists e Skills:**
  - Atualização de `framework/revisao.md`, `.agents/AGENTS.md`, `README.md`, `framework/checklists/editorial.md`, `framework/templates/modelo_skill.md`, `framework/normas/README.md` e das skills em `.agents/skills/` para refletir as 22 ferramentas MCP, os 26 checklists, a hierarquia tripla e a arquitetura SSOT (`dados_analise.json` + `index.html`).

---

## [1.3.0] - 2026-10-14
### Adicionado
- **Hierarquia Tripla Canônica (`analise/<lote>/<version>/<timestamp>/`):**
  - Estruturação do armazenamento em três níveis semânticos claros:
    - `<lote>`: Pacote de contratação ou escopo técnico (ex.: `03_HLD_NUTANIX`).
    - `<version>`: Versão do artefato entregue pelo fornecedor (ex.: `v1.0`, `v1.8`, `v1.8.2`).
    - `<timestamp>`: Rodada de auditoria da IA ou ciclo de revisão/adjudicação humana (ex.: `20261014_210000`).
- **Ciclo de Revisão e Adjudicação Humana (`create_review_revision`):**
  - Nova ferramenta MCP que permite ao auditor criar uma rodada pontual de revisão sob a mesma versão do documento sem sobrescrever a análise original da IA.
  - Clona o `dados_analise.json` e a pasta `entrada/` preservando a baseline e registrando trilha de auditoria (`audit_trail`), permitindo adjudicações de falsos positivos, ajustes de severidade e inclusão de observações manuais em um novo timestamp histórico.
- **Resolução Universal Flexível de Diretórios (`_resolve_analysis_dirs`):**
  - Todas as funções MCP (`tool_adjudicate_findings`, `tool_record_semantic_analysis`, `tool_build_run_index_html`, `tool_validate_analise_contract`, `tool_finalize_execution`) resolvem de forma dinâmica tanto o caminho relativo completo quanto o timestamp isolado da folha via busca recursiva de até 4 níveis.
- **Isolamento Estrito de Séries Históricas na Finalização:**
  - `tool_finalize_execution` identifica os arquivos da baseline pertencentes exclusivamente àquela versão específica, movendo apenas os artefatos analisados e preservando as demais versões em `entrada/` para suas respectivas rodadas.
- **Portal Master com Visão Hierárquica e Badges:**
  - `tool_build_master_index` enriquecido com detecção de versão (`v1.0`, `v1.8`) e badges distintivos para versões de documento e rodadas de revisão adjudicadas.

---

## [1.2.0] - 2026-10-14
### Adicionado
- **Hierarquia por Lotes no Armazenamento (`analise/<lote>/<timestamp>/`):** 
  - Reestruturação do sistema de arquivos para armazenar os relatórios e evidências de forma isolada por lote (`analise/<lote>/<timestamp_versao>/relatorios/` e `analise/<lote>/<timestamp_versao>/entrada/`), eliminando o desordenamento cronológico na raiz da pasta `analise/`.
- **Detecção Inteligente de Séries Históricas de Versões:**
  - Implementação da função `detect_document_versions` no módulo `mcp-server/audit_engine.py` e integração ao `tool_profile_baseline` no `mcp-server/server.py`.
  - Identifica automaticamente se múltiplos arquivos dentro de um mesmo lote representam versões sucessivas de um mesmo documento (ex.: `v1.0`, `v1.1`, `_v1`, `_v2`, `_revA`, `_revB`), permitindo a execução sequencial independente de cada versão para prevenir falsos positivos de inconsistência interna.
- **Motor de Reconciliação e Evolução Técnica (`reconcile_versions`):**
  - Nova funcionalidade de confrontação matemática entre bases de auditoria (`dados_analise.json`) de versões distintas do mesmo documento.
  - Classificação automatizada dos apontamentos em três categorias de gestão:
    - 🟢 **Achados Sanados / Superados:** Problemas da versão anterior resolvidos na versão nova.
    - 🔴 **Achados Reincidentes / Não Sanados:** Apontamentos da versão anterior que persistem na versão nova.
    - 🟡 **Novos Achados:** Vícios inéditos ou regressões introduzidas na nova revisão.
  - Cálculo automático de indicadores evolutivos: Taxa de Resolução de Apontamentos (`%`), IQD Anterior vs. IQD Atual e Delta de Conformidade (`Δ IQD`).
- **Descoberta Recursiva no Master Index:**
  - Atualização das funções `tool_build_master_index`, `_get_relatorios_dir`, `tool_validate_analise_contract` e `tool_finalize_execution` no `server.py` para descobrir e processar relatórios tanto na raiz quanto aninhados em subpastas de lotes.
- **Atualização de Normas Corporativas:**
  - Ajuste nas Diretrizes 2 e 7 em `.agents/AGENTS.md` formalizando a nova organização por lotes e o fluxo de análise sequencial de séries históricas.

---

## [1.1.0] - 2026-10-14
### Segurança
- **Blindagem em Profundidade contra Vazamentos no Git:**
  - Atualização abrangente do arquivo `.gitignore` com bloqueio recursivo de `/entrada/**` e `/analise/**`, preservando apenas arquivos de infraestrutura (`.gitkeep`, `README.md`, `decisoes.yaml`).
  - Bloqueio global de extensões sensíveis de documentos (`*.pdf`, `*.docx`, `*.xlsx`, `*.csv`, `*.vsdx`, imagens soltas `*.png`, `*.jpg`, `*.svg`) e arquivos temporários de lock de editores (`~$*`, `.~lock.*`).
### Adicionado
- **Ferramenta de Diagnóstico de Ambiente (`tool_check_environment`):**
  - Módulo integrado para inspeção de pacotes do sistema operacional Linux (Tesseract OCR, Poppler, LibreOffice, Graphviz) e bibliotecas Python necessárias para potencializar extração de texto e visão multimodal.
- **Confronto Visual Texto × Diagrama na Ficha 360°:**
  - Inclusão dos campos normativos `texto_afirmado` e `diagrama_demonstrado` nas fichas de achado da skill `analisar-diagramas`.
  - Suporte a imagens Base64 inline no relatório HTML (`mcp-server/html_compiler.py`) para geração de relatórios "single-file" autossuficientes sem dependências externas de links locais.
### Corrigido
- Correção de importação no `mcp-server/server.py` adicionando `sys.path.insert(0, _current_dir)`.
- Redirecionamento de logs de diagnóstico de `stdout` para `stderr` em `mcp-server/html_compiler.py`, garantindo integridade estrita do protocolo MCP JSON-RPC.

---

## [1.0.0] - Versão Inicial do GitHub
### Adicionado
- **Framework FCA-ENG-001:**
  - Procedimento corporativo para Revisão Técnica Independente (RTI) sobre documentos de engenharia, RFPs, HLDs, LLDs e contratos de telecomunicações/TI.
- **Servidor MCP (`mcp-server`):**
  - Ferramentas de inspeção de baseline, triagem adaptativa (`profile_baseline`), validação de contratos (`validate_analise_contract`), auditoria semântica e consolidação em `dados_analise.json`.
- **Catálogo Inicial de Skills Especializadas:**
  - `analisar-documento`, `analisar-cloud`, `analisar-integracoes`, `analisar-datacenter`, `analisar-rfp`, `analisar-hld`, `analisar-lld`, `analisar-contrato`, `analisar-planilha`, `analisar-carrier`, `analisar-diagramas`, `analisar-lgpd`.
- **Entregável Consolidado HTML:**
  - Dashboard executivo responsivo com 8 seções sequenciais, cálculo dinâmico de IQD e parecer corporativo.
