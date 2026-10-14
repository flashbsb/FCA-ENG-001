---
name: analisar-contrato
description: Skill especializada para Revisão Técnica de cláusulas contratuais, minutas, SLAs, penalidades, obrigações de partes, rescisão e critérios de aceite em documentos de licitação pública e contratos de TI/Telecom. Não emite interpretação jurídica — identifica lacunas, inconsistências e riscos para encaminhamento ao jurídico competente.
---

# Skill: Análise de Cláusulas Contratuais e SLAs

Esta skill especializa a RTI para aspectos contratuais e de nível de serviço, identificando lacunas, assimetrias e inconsistências que podem gerar litígio ou prejuízo operacional.

> **Atenção:** Esta skill identifica achados técnico-documentais. **Não emite interpretação jurídica.** Encaminha ao Jurídico competente via pergunta formal Q-XXX.

---

## Contexto de Ativação

Ative quando o lote contiver:
- Minuta de contrato ou contrato vigente
- SLA específico (Acordo de Nível de Serviço)
- Edital com cláusulas de penalidade
- Termos de referência com obrigações

---

## Workflow de Análise Contratual

### 1. Análise de SLAs

Para cada SLA declarado, verifique:
- **Valor numérico:** Percentual, prazo ou quantidade definidos?
- **Janela de medição:** Mensal, trimestral, anual? Horário de medição?
- **Método de cálculo:** Fórmula explícita ou referência a norma?
- **Exclusões:** Manutenções programadas, força maior estão definidas?
- **Penalidade:** Há consequência definida para descumprimento?
- **Escalonamento:** Se a penalidade escala com reincidência?
- **Relatório:** Quem mede, como reporta e para quem?

SLA sem qualquer um desses itens = **Lacuna** com Criticidade conforme impacto.

### 2. Análise de Obrigações das Partes

- Liste as obrigações da Contratante e da Contratada separadamente.
- Verifique assimetrias (uma parte com obrigações excessivas sem contrapartida).
- Verifique obrigações sem prazo definido = Lacuna.
- Verifique obrigações sem critério de aceite = Ambiguidade.

### 3. Análise de Rescisão

- Prazo de aviso prévio especificado?
- Condições de rescisão por justa causa claramente definidas?
- Há ressarcimento em caso de rescisão imotivada?
- Ativos (hardware, licenças) adquiridos especificamente têm tratamento em rescisão?

### 4. Análise de Penalidades e Multas

- Valores de multa são proporcionais e legalmente defensáveis? (encaminhar ao Jurídico)
- Há teto de penalidade total?
- Processo de glosa é descrito (notificação, prazo de defesa, recurso)?

### 5. Inconsistências Contratuais

- Compare cláusulas entre si: a mesma obrigação com prazo diferente em duas cláusulas.
- Compare o contrato com os anexos técnicos: SLA diferente no Anexo A vs no corpo do contrato.

---

## Achados Típicos de Contratos

| Tipo | Exemplo |
|------|---------|
| Lacuna | SLA de disponibilidade 99,5% sem definição de janela de medição |
| Inconsistência | Corpo do contrato diz prazo de entrega 90 dias; Cronograma no Anexo diz 120 dias |
| Risco | Rescisão imotivada com aviso de 30 dias sem qualquer ressarcimento de CAPEX investido |
| Ambiguidade | "Manutenção preventiva" sem frequência, duração ou procedimento definido |
| Lacuna | Processo de glosa sem prazo de resposta para defesa do fornecedor |

---

## Saída Esperada

Registre os achados em `dados_analise.json` com categoria `Contrato / SLA` para exibição no `index.html`:
- Achados de cláusulas ambíguas e conflitos entre contrato e anexos técnicos
- Riscos contratuais com impacto financeiro ou operacional potencial descrito
- Minutas sugeridas De → Para para adequação redacional
- Perguntas formais (`Q-XXX`) encaminhando ao Jurídico os pontos de interpretação legal
