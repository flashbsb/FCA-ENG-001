---
name: {{SKILL_NAME}}
description: {{SKILL_DESCRIPTION}}
---

# Skill: {{SKILL_TITLE}}

Esta skill orienta o assistente de IA a executar a análise especializada no domínio **{{SKILL_DOMAIN}}** sobre a documentação de baseline presente na pasta `entrada/`.

## Propósito e Escopo de Análise
- **Domínio Principal:** {{SKILL_DOMAIN}}
- **Objetivo:** Auditar requisitos, especificações, SLAs, arquitetura e conformidades pertinentes ao escopo de {{SKILL_DOMAIN}}.
- **Checklists Associados:** `framework/checklists/{{CHECKLIST_FILE}}.md`

## Workflow de Execução Especializada

### 1. Triagem e Inspeção de Requisitos Específicos
1. Identificar todas as seções e anexos da baseline em `entrada/` que abordam {{SKILL_DOMAIN}}.
2. Extrair tabelas de volumetria, parâmetros numéricos e requisitos funcionais/não-funcionais.

### 2. Verificação de Conformidade e Evidências
1. Confrontar o texto da baseline com as diretrizes do checklist `framework/checklists/{{CHECKLIST_FILE}}.md`.
2. Registrar evidências de Grau **E1** (indicação), **E2** (corroborado) ou **E3** (confirmado/confronto direto).

### 3. Registro dos Achados Atômicos
1. Registrar todas as não conformidades, lacunas e riscos encontrados no arquivo `analise/<timestamp>/relatorios/01_PONTOS_DE_ATENCAO.md` e sincronizar com a `00_RESUMO_EXECUTIVO.md`.
2. Segregar rigorosamente **Tipo**, **Criticidade** (Crítica, Alta, Média, Baixa) e **Prioridade** (P0, P1, P2, P3).
