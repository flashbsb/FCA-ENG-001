---
name: analisar-lgpd
description: Skill especializada para Revisão Técnica de conformidade com a Lei Geral de Proteção de Dados (LGPD - Lei 13.709/2018) e proteção de dados pessoais em arquiteturas de TI, RFPs e contratos. Identifica lacunas de conformidade, ausência de controles exigidos e riscos de privacidade.
---

# Skill: Análise de Conformidade LGPD e Proteção de Dados

Esta skill especializa a RTI para aspectos de privacidade e proteção de dados pessoais, aplicável quando os documentos do lote envolvem processamento de dados de pessoas físicas.

> **Atenção:** Esta skill identifica lacunas e riscos documentais. **Não emite parecer jurídico.** Encaminha ao DPO/Jurídico competente via pergunta formal Q-XXX.

---

## Contexto de Ativação

Ative quando o lote mencionar: dados pessoais, CPF, RG, dados biométricos, dados de saúde, LGPD, ANPD, DPO, privacidade, relatório de impacto, base legal, consentimento, titular de dados.

---

## Checklist de Conformidade LGPD

### Bases Legais e Finalidade
- [ ] A finalidade do tratamento de dados pessoais está declarada?
- [ ] A base legal do tratamento está identificada (Art. 7º ou Art. 11 da LGPD)?
- [ ] Os dados coletados são limitados ao mínimo necessário (princípio da minimização)?

### Direitos dos Titulares
- [ ] Há mecanismo previsto para o titular acessar, corrigir ou excluir seus dados?
- [ ] Há canal de atendimento ao titular identificado?
- [ ] O prazo de resposta a solicitações de titulares está definido?

### Medidas Técnicas e Organizacionais
- [ ] Controles de acesso aos dados pessoais estão especificados?
- [ ] Há criptografia em trânsito e em repouso para dados sensíveis?
- [ ] Há procedimento de notificação de incidente de segurança à ANPD?
- [ ] O prazo de notificação de incidente está definido (LGPD: prazo razoável)?

### Operadores e Suboperadores
- [ ] Há cláusula de proteção de dados no contrato com o operador?
- [ ] O operador está obrigado a seguir as instruções do controlador?
- [ ] Há vedação de uso dos dados para finalidades próprias do operador?

### Transferência Internacional
- [ ] Há transferência de dados para outro país? Se sim, a base legal está identificada?

### RIPD (Relatório de Impacto)
- [ ] Para tratamentos de alto risco, há previsão de elaboração do RIPD?

---

## Achados Típicos LGPD

| Tipo | Exemplo |
|------|---------|
| Lacuna | Sistema de CRM processa CPF sem declaração de base legal |
| Lacuna | Contrato com operador sem cláusula de proteção de dados |
| Risco | Dados de saúde processados sem medidas adicionais de segurança |
| Lacuna | Ausência de mecanismo para atendimento a direitos dos titulares |
| Lacuna | Prazo de retenção de dados pessoais não especificado |

---

## Saída Esperada

Registre os achados em `dados_analise.json` com categoria `LGPD / Privacidade` para exibição no `index.html` com:
- Status do checklist LGPD (conforme/não conforme/não aplicável/não verificável)
- Achados com referência ao artigo LGPD correspondente
- Encaminhamento ao DPO via perguntas `Q-XXX` para pontos que requerem decisão do controlador
