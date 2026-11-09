---
name: {{SKILL_NAME}}
description: {{SKILL_DESCRIPTION}}
---

# Skill: {{SKILL_TITLE}}

Esta skill orienta o assistente de IA a executar a análise especializada no domínio **{{SKILL_DOMAIN}}** sobre a documentação de baseline presente na pasta `entrada/`.
Esta skill orienta o assistente de IA a executar a Revisão Técnica Independente (RTI) especializada no domínio **{{SKILL_DOMAIN}}** sobre a documentação de baseline presente na pasta `entrada/<lote>/`.

## Propósito e Escopo de Análise
- **Domínio Principal:** {{SKILL_DOMAIN}}
- **Objetivo:** Auditar requisitos, especificações, SLAs, arquitetura e conformidades pertinentes ao escopo de {{SKILL_DOMAIN}}.
- **Checklists Associados:** `framework/checklists/{{CHECKLIST_FILE}}.md`
- **Objetivo:** Auditar requisitos, especificações, SLAs, arquitetura e conformidades pertinentes ao escopo de {{SKILL_DOMAIN}}, sem inventar requisitos ou suposições.
- **Checklists Associados:** `framework/checklists/{{CHECKLIST_FILE}}`

## Workflow de Execução Especializada

### 1. Triagem e Inspeção de Requisitos Específicos
1. Identificar todas as seções e anexos da baseline em `entrada/` que abordam {{SKILL_DOMAIN}}.
2. Extrair tabelas de volumetria, parâmetros numéricos e requisitos funcionais/não-funcionais.
1. Identificar todas as seções, tabelas e anexos da baseline em `entrada/<lote>/` que abordam {{SKILL_DOMAIN}}.
2. Extrair tabelas de volumetria, parâmetros numéricos e requisitos funcionais/não-funcionais via leitura paginada (`get_semantic_document_chunk`).

### 2. Verificação de Conformidade e Evidências
1. Confrontar o texto da baseline com as diretrizes do checklist `framework/checklists/{{CHECKLIST_FILE}}.md`.
2. Registrar evidências de Grau **E1** (indicação), **E2** (corroborado) ou **E3** (confirmado/confronto direto).
1. Confrontar o texto da baseline com as diretrizes do checklist `framework/checklists/{{CHECKLIST_FILE}}`.
2. Registrar evidências de Grau **E1** (indicação), **E2** (corroborado) ou **E3** (confirmado/confronto direto com ao menos duas citações literais).

### 3. Registro dos Achados Atômicos
1. Registrar todas as não conformidades, lacunas e riscos encontrados no arquivo `analise/<timestamp>/relatorios/01_PONTOS_DE_ATENCAO.md` e sincronizar com a `00_RESUMO_EXECUTIVO.md`.
2. Segregar rigorosamente **Tipo**, **Criticidade** (Crítica, Alta, Média, Baixa) e **Prioridade** (P0, P1, P2, P3).
### 3. Registro dos Achados Atômicos (SSOT)
1. Persistir todas as não conformidades, lacunas e riscos encontrados via `record_semantic_analysis` na base estruturada `analise/<lote>/<version>/<timestamp>/relatorios/dados_analise.json` para compilação no dashboard `index.html`.
2. Segregar rigorosamente **Tipo**, **Criticidade** (Crítica, Alta, Média, Baixa, Informativa) e **Prioridade** (P0, P1, P2, P3).
