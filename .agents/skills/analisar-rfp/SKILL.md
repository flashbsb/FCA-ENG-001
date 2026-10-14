---
name: analisar-rfp
description: Skill especializada para Revisão Técnica de Requests for Proposal (RFPs) e Requests for Information (RFIs). Analisa a correlação entre múltiplos arquivos do lote (documento principal, anexos técnicos, planilhas), verifica completude de requisitos funcionais/não funcionais, consistência de SLAs, penalidades, critérios de aceite e obrigações contratuais. Ativa automaticamente quando o lote contém RFP, RFI ou documentação correlata.
---

# Skill: Análise de RFP / RFI (Request for Proposal / Information)

Esta skill especializa a RTI para documentos de licitação, concorrência pública ou consulta ao mercado, onde múltiplos arquivos formam um conjunto coeso e devem ser analisados com correlação cruzada obrigatória.

---

## Contexto de Ativação

Ative esta skill quando o lote contiver qualquer combinação de:
- Documento principal de RFP, RFI, Edital, Pregão ou Concorrência
- Anexos técnicos de especificação (Anexo A, Anexo B, etc.)
- Planilhas de quantitativos, BOMs (Bill of Materials) ou preços de referência
- Minutas de contrato ou cláusulas especiais

---

## Workflow de Análise RFP

### 1. Mapeamento do Conjunto Documental

1. Identifique o **documento raiz** (RFP/Edital principal) e todos os **documentos dependentes** (anexos, adendos, planilhas).
2. Construa o mapa de relações: qual documento é referenciado por qual outro, quais anexos complementam quais seções.
3. Verifique se todos os documentos referenciados no texto estão presentes no lote.
   - Se ausentes → registrar como **Lacuna (LAC-XXX)** com Criticidade Alta.

### 2. Análise de Requisitos Técnicos

Verifique para cada requisito:
- **Completude:** O requisito tem critério de aceite verificável? (ex: "alta disponibilidade" sem SLA definido = Lacuna)
- **Mensurabilidade:** Valores quantitativos presentes? (ex: "99,9% de disponibilidade" em vez de "alta disponibilidade")
- **Rastreabilidade:** O requisito do documento principal é detalhado nos anexos?
- **Consistência:** O mesmo requisito citado em dois arquivos usa os mesmos valores?
- **Ambiguidade:** Termos vagos como "rápido", "moderno", "adequado", "eficiente" sem definição técnica = achado de Ambiguidade.
- **Verbos normativos:** Diferenciar DEVE (obrigatório), DEVERIA (recomendado), PODE (opcional). Mistura ou ausência = achado.

### 3. Análise de SLAs e Níveis de Serviço

- Verifique se cada SLA tem: valor numérico, período de medição, método de cálculo, penalidade por descumprimento.
- Identifique SLAs contraditórios entre documentos (ex: RFP diz 4h de RMA, Anexo A diz 24h).
- Verifique se os SLAs são tecnicamente viáveis (ex: SLA de 99,999% para um serviço sem redundância documentada).

### 4. Análise Contratual e de Riscos

- Verifique cláusulas de rescisão, multas e penalidades.
- Identifique assimetrias contratuais (ex: rescisão imotivada sem ressarcimento de CAPEX).
- Verifique se prazos de entrega, aceite e pagamento são coerentes entre si.

### 5. Correlação Cruzada RFP × Anexos × Planilha

Para cada item encontrado em planilhas (ex: lista de equipamentos, quantitativos):
- Verifique se o item corresponde exatamente ao que é descrito na especificação técnica.
- Identifique quantitativos na planilha que não têm correspondência no documento técnico (e vice-versa).
- Inconsistência de valores = achado de Inconsistência (INS-XXX) com Grau de Evidência E3.

### 6. Verificação Normativa

- Identifique normas referenciadas (ABNT, IEEE, ITU, ETSI, TM Forum, etc.).
- Verifique se a edição da norma está especificada (norma sem edição = Lacuna).
- Verifique se a norma é de aplicação obrigatória (por contrato/regulação) ou recomendada (boa prática).

---

## Achados Típicos de RFP (Exemplos de Referência)

| Tipo | Exemplo de Achado |
|------|------------------|
| Lacuna | SLA de disponibilidade exigido sem definição de janela de medição ou método de cálculo |
| Inconsistência | Prazo de RMA de 8h no documento principal vs 45 dias no Anexo A |
| Ambiguidade | Requisito de "sistema moderno e escalável" sem métricas de escala ou critério de modernidade |
| Risco | Rescisão imotivada em 30 dias sem ressarcimento de ativos CAPEX |
| Lacuna | Referência a "Anexo C" no texto mas Anexo C ausente do lote |
| Inconsistência | Planilha lista 50 licenças SIEM; documento técnico menciona 100 licenças |

---

## Saída Esperada

Registre os achados em `dados_analise.json` com categoria `RFP / Edital` para exibição no `index.html`:
- Mapa documental (arquivos, relações, ausências)
- Achados específicos de RFP com referência cruzada entre arquivos
- Tabela de requisitos: ID requisito, documento origem, critério de aceite, status de completude
- Todas as lacunas de requisito (`LAC-XXX`) e riscos contratuais (`RSC-XXX`) com impacto estimado
- Perguntas formais (`Q-XXX`) para cada lacuna estratégica que exige esclarecimento do comprador
- Minutas sugeridas De → Para para cláusulas ambíguas ou contraditórias
