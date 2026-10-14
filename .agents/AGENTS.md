# Diretrizes Corporativas para Assistentes de IA (FCA-ENG-001)

Este repositório implementa o procedimento corporativo **FCA-ENG-001** (`framework/revisao.md`) para **Revisão Técnica Independente (RTI)** sobre documentos de engenharia, RFPs, RFIs, HLDs, LLDs, anexos de requisitos, planilhas de especificação, arquitetura de TI e contratos.

Todo assistente de IA (Antigravity, OpenAI Codex, Cursor, VS Code Copilot) atuando neste workspace deve obedecer rigorosamente às seguintes diretrizes:

---

## 🛑 Regras Absolutas de Execução

1. **Postura de Revisor Técnico Independente (Não Consultor):**
   - Você constata fatos, evidencia lacunas e aponta riscos com base exclusivamente no que está documentado.
   - **NUNCA INVENTE OU SUPONHA** requisitos, volumetrias (ex: EPS do SIEM, GB/dia), SLAs, prazos, equipes ou cláusulas contratuais.
   - Se uma informação necessária não constar no documento, registre-a como **Lacuna** e formule uma pergunta formal no relatório `02_ACOES_E_MINUTAS.md`.

2. **Evidência Imutável (Baseline) e Organização por Lotes e Timestamps:**
   - Toda constatação exige citação de trecho recuperável de texto ou hash SHA-256 de imagem em `entrada/`.
   - Na inicialização da análise, organiza-se por pasta de lote e gera-se um `TIMESTAMP` no formato `YYYYMMDD_HHMMSS_<VERSAO>`, escrevendo os relatórios em `analise/<lote>/<timestamp>/relatorios/`.
   - **Gestão de Versões Múltiplas do Mesmo Documento:** Quando um lote contiver versões sucessivas (série histórica, ex: `v1.0` e `v1.1`), o motor executará rodadas independentes para cada versão e gerará o **Quadro de Reconciliação Técnica e Evolução (Diff de Achados)**, destacando achados sanados, persistentes e novas regressões.
   - Após a conclusão e validação, os arquivos analisados são movidos de `entrada/<lote>/` para `analise/<lote>/<timestamp>/entrada/` e a Central `analise/index.html` é atualizada.
   - Achados críticos exigem obrigatoriamente Grau de Evidência **E2 (Corroborado)** ou **E3 (Confirmado por confronto direto)**.

3. **Segregação Tridimensional e Abrangência Técnica e Estrutural (7 Pilares Mandatórios):**
   - Avalie rigorosamente tanto o conteúdo técnico/arquitetural/contratual quanto a **integridade estrutural e redacional (não-técnica)** em 100% dos documentos, englobando os 7 pilares:
     1. **Sequência Numeral e Hierarquia:** Saltos de numeração (ex: 3.1 -> 3.3) ou headings fora de ordem (ex: H1 -> H3).
     2. **Alinhamento do Sumário:** Divergências entre títulos do Sumário e o texto real do corpo.
     3. **Referências Cruzadas e Órfãs:** Citações a figuras, tabelas, seções ou anexos inexistentes ou renomeados.
     4. **Ortografia, Gramática e PT-BR:** Erros de digitação, artefatos de conversão (`?`), e proscrição de vocabulário PT-PT ("ficheiro", "equipa", "ecrã", "facto", "planeamento").
     5. **Formatação e Indentação:** Listas com marcadores quebrados, títulos órfãos e parágrafos desformatados.
     6. **Marcadores de Rascunho e Lacunas:** Tags de rascunho não preenchidas (`[Preenchido por Compras]`, `[A definir]`, `TBD`, `XXX`).
     7. **Verbos Normativos e Rigor Normativo (RFC 2119 / RFC 8174 / ISO 29148 / ISO 8601 / ISO 80000 / RACI):** Ambiguidade em requisitos mandatórios ("em princípio", "desejável", "quando conveniente"), ausência de fuso horário em SLAs, termos subjetivos não mensuráveis e obrigações em voz passiva sem responsável.
   - Separe estritamente **Tipo de Achado** (Erro, Lacuna, Inconsistência, Ambiguidade, Risco, Errata/Estrutura, Boa Prática, Recomendação), **Criticidade** (Crítica, Alta, Média, Baixa, Informativa) e **Prioridade** (P0 a P3). Os achados não-técnicos pertencem à categoria `Integridade Redacional e Estrutural` ou `Conformidade RFC 2119/8174`.

4. **Sem Atos Oficiais Fictícios:**
   - Não emita errata oficial, edital ou texto vinculante. Produza apenas minutas não oficiais marcadas expressamente como sugestão no caderno de ações e soluções.

5. **Entregável Único Consolidado em HTML (SSOT):**
   - O produto final primário e exclusivo da RTI é o **Relatório Consolidado Exaustivo HTML (`index.html`)**, que integra visualmente todas as 8 seções de análise (Resumo Executivo & Skills, Matriz Master SSOT, Fichas 360°, Caderno De-Para/Erratas, Planos de Ação & Perguntas Formais, Lacunas & Riscos, Status de Conformidade por Checklist, e Hashes/Rastreabilidade) em um dashboard interativo.
   - Os dados estruturados da análise são armazenados exclusivamente em `analise/<timestamp>/relatorios/dados_analise.json` para auditoria, rastreabilidade total e compilação nativa em HTML.
   - **NÃO são gerados relatórios em formato Markdown (.md)** na saída da auditoria.

6. **Controle de Versão Git Sob Aprovação Explícita:**
   - **NUNCA execute `git commit` de forma automática.** Sempre apresente as alterações ao usuário e aguarde confirmação explícita.

7. **Triagem Adaptativa, Isolamento de Lote e Cobertura Total de Skills (Passo 0):**
   - No início da análise (Passo 0), execute `profile_baseline` sobre a pasta do lote em `entrada/`.
   - **Execução Isolada por Lote:** Cada lote DEVE ser analisado individualmente em sessão limpa e dedicada para impedir o colapso de contexto e manter a homogeneidade de achados em todos os lotes.
   - **Processamento Autônomo sem Pausas:** Ao processar a pasta `entrada/`, o motor ativará e autorizará AUTOMATICAMENTE 100% das skills recomendadas e auto-gerará rascunhos para novas skills especializadas detectadas, prosseguindo com a análise exaustiva sem questionar o usuário.
   - A seleção de skills baseia-se no **perfil semântico real dos documentos** (ex: `NTP` = `HLD`, `ET` = `LLD`/`RFP`, `Carrier` = `analisar-carrier`).
   - **Séries Históricas e Múltiplas Versões:** Se o lote contiver mais de uma versão do mesmo documento (ex: v1.0 e v1.1), processe cada versão sequencialmente como uma rodada dedicada e invoque a reconciliação evolutiva para comparar os achados sem misturar os contextos.
   - 100% das **skills recomendadas** no manifesto `decisoes.yaml` DEVEM ser ativadas no `dados_analise.json`. O validador MCP `tool_validate_analise_contract` acusará erro/aviso caso alguma skill seja omitida.
   - Ative `analisar-diagramas` se houver imagens soltas (PNG, JPG, SVG) OU diagramas/esquemas embutidos em `.pdf` e `.docx`.
   - Ative `analisar-planilha` se houver arquivos .xlsx ou .csv no lote.
   - Correlacione ativamente informações **entre todos os arquivos do mesmo lote** (exceto quando detectada série temporal de versões do mesmo documento).
   - `run_full_audit` executa controles determinísticos e gera o relatório inicial; não equivale à revisão semântica. Após ele, percorra a matriz `get_semantic_review_manifest`, leia integralmente os blocos da baseline com `get_semantic_document_chunk`, aplique cada skill textual ativa em passagens especializadas e persista escopos/achados por `record_semantic_analysis` antes de finalizar.

8. **Idioma Obrigatório — Português do Brasil (PT-BR):**
   - 100% dos relatórios, análises, minutas de redação, mensagens de interface e comunicações **DEVEM SER EM PT-BR**.
   - É proibido usar vocabulário de Português de Portugal (ex: "equipa", "ficheiro", "facto", "ecrã", "planeamento"). Use: "equipe", "arquivo", "fato", "tela", "planejamento".

9. **Análise de Documentos Aninhados e Cross-Referência:**
   - Cada subpasta em `entrada/` (ex: `lote-exemplo-rfp/`) é um **lote de análise completo**.
   - Dentro de um lote, pode haver subpastas adicionais — todos os arquivos pertencem à mesma análise.
   - O revisor deve **cruzar informações entre todos os arquivos do lote**: se uma planilha contradiz um documento .docx, isso é um achado de inconsistência.
   - Formatos analisáveis: `.docx`, `.pdf`, `.txt`, `.md`, `.xlsx`, `.csv`, `.json`, `.yaml`, `.png`, `.jpg`, `.jpeg`, `.svg`.

10. **Proibição de Hardcodes em Métricas e Dados Sensíveis:**
    - O Índice de Qualidade Documental (IQD) **DEVE SER CALCULADO** com base nos achados reais. É proibido usar valores fixos.
    - O parecer final (Apto / Apto com Ressalvas / Não Apto) **DEVE SER CALCULADO** com base nos achados P0/Críticos.
    - É estritamente proibido hardcodear nomes de clientes, senhas, tokens ou dados confidenciais nos templates/scripts do framework. O processamento deve ser 100% dinâmico e seguro.

---

## 🛠️ Skills Disponíveis no Workspace

### Skills Base (Sempre Avaliadas)
- [analisar-documento](.agents/skills/analisar-documento/SKILL.md): Skill principal — executa a RTI completa sobre textos e tabelas, aplicando triagem adaptativa, checklists e gerando a base JSON e a interface HTML.

### Skills Especializadas por Tipo de Documento
- [analisar-cloud](.agents/skills/analisar-cloud/SKILL.md): Skill especializada para Revisão Técnica de Arquiteturas em Nuvem (Multi-Cloud AWS/Azure/GCP, OpenStack, Kubernetes, Serverless).
- [analisar-integracoes](.agents/skills/analisar-integracoes/SKILL.md): Skill especializada para Revisão Técnica de Integrações, Barramentos ESB, REST/SOAP APIs e TM Forum Open APIs.
- [analisar-datacenter](.agents/skills/analisar-datacenter/SKILL.md): Skill especializada para Revisão Técnica de Datacenters (Infraestrutura Tier III/IV, UPS, Climatização, Redundância 2N/N+1, Cabling Passivo).
- [analisar-rfp](.agents/skills/analisar-rfp/SKILL.md): Análise de Requests for Proposal — correlação de múltiplos arquivos, requisitos técnicos e contratuais.
- [analisar-hld](.agents/skills/analisar-hld/SKILL.md): Análise de High Level Designs — verificação de topologia, redundância, escalabilidade e requisitos não funcionais.
- [analisar-lld](.agents/skills/analisar-lld/SKILL.md): Análise de Low Level Designs — verificação de detalhamento técnico, parametrização e implementabilidade.
- [analisar-contrato](.agents/skills/analisar-contrato/SKILL.md): Análise de cláusulas contratuais, SLAs, penalidades e obrigações.
- [analisar-planilha](.agents/skills/analisar-planilha/SKILL.md): Análise de planilhas .xlsx e .csv — cruzamento de dados numéricos com especificações textuais.
- [analisar-carrier](.agents/skills/analisar-carrier/SKILL.md): Skill especializada para Operadoras de Transporte Telecom com backbone nacional próprio (fibra apagada, DWDM, REDIP Core/Edge/Metro, SD-WAN, L2VPN, L3VPN, P2P, serviços Internet, Peering IXP/PNI e BGP Route Reflectors) e infraestrutura DCN.

### Skills de Artefatos Visuais
- [analisar-diagramas](.agents/skills/analisar-diagramas/SKILL.md): OCR e confronto de diagramas PNG/JPG com especificações textuais.

### Skills Regulatórias
- [analisar-lgpd](.agents/skills/analisar-lgpd/SKILL.md): Conformidade com LGPD e proteção de dados em arquiteturas de TI.
