---
name: analisar-planilha
description: Skill especializada para Revisão Técnica de planilhas (.xlsx, .csv) e documentos tabulares. Extrai dados de células, abas e fórmulas para verificar consistência com especificações textuais do mesmo lote, identificar inconsistências numéricas, quantitativos conflitantes e dados ausentes que deveriam estar presentes conforme o escopo declarado.
---

# Skill: Análise de Planilhas e Dados Tabulares

Esta skill especializa a RTI para arquivos estruturados como planilhas Excel e CSV, extraindo e correlacionando dados com os demais documentos do lote.

---

## Contexto de Ativação

Ative quando o lote contiver:
- Arquivos `.xlsx`, `.xls`, `.csv`
- Planilhas de quantitativos, BOMs, preços de referência
- Cronogramas em formato tabular
- Matrizes de requisitos ou conformidade

---

## Workflow de Análise de Planilha

### 1. Inventário de Conteúdo

1. Liste todas as abas (sheets) presentes com nome e descrição inferida do conteúdo.
2. Para cada aba, identifique:
   - Cabeçalhos de coluna
   - Tipos de dados (texto, numérico, data, fórmula)
   - Faixas de dados preenchidos vs células vazias
   - Totalizadores e subtotais

### 2. Correlação com Documentos Textuais do Lote

Para cada item na planilha, verifique nos documentos .docx/.pdf do mesmo lote:
- O item existe na especificação técnica? (ausente = Lacuna)
- Os quantitativos batem? (diferença = Inconsistência)
- As unidades são compatíveis? (ex: planilha em GB vs documento em TB = Ambiguidade)
- O item descrito na planilha tem especificação técnica no documento? (ausente = Lacuna)

### 3. Consistência Interna da Planilha

- Totais conferem com a soma dos itens?
- Há linhas com dados incompletos (células obrigatórias vazias)?
- Há itens duplicados com valores diferentes?
- Fórmulas referenciam células corretas?

### 4. Completude dos Dados

- A planilha cobre todos os itens listados nos documentos textuais?
- Há colunas obrigatórias ausentes conforme o escopo declarado?

---

## Achados Típicos de Planilha

| Tipo | Exemplo |
|------|---------|
| Inconsistência | Planilha lista 50 licenças SIEM; documento técnico menciona 100 licenças |
| Lacuna | Aba "SOC" sem preenchimento de colunas de prazo de entrega |
| Inconsistência | Planilha soma total de R$ 1.200.000 mas itens somam R$ 1.350.000 |
| Inconsistência | Documento cita roteador modelo X; planilha lista modelo Y |
| Ambiguidade | Coluna "Capacidade" sem unidade de medida definida |

---

## Saída Esperada

Registre os achados em `dados_analise.json` com categoria `Planilha / Quantitativo` para exibição no `index.html` com:
- Inventário de abas e conteúdo
- Achados de inconsistência entre planilha e documentos textuais
- Achados de consistência interna (células, somatórias, unidades)
