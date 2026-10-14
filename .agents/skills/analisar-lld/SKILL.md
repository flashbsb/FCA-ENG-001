---
name: analisar-lld
description: Skill especializada para Revisão Técnica de Low Level Designs (LLD) e documentos de detalhamento técnico de implementação. Verifica parametrização, configurações, consistência com o HLD de referência, completude de procedimentos e implementabilidade técnica.
---

# Skill: Análise de LLD (Low Level Design)

Esta skill especializa a RTI para documentos de detalhamento técnico de baixo nível, verificando se o design é suficientemente detalhado para implementação, consistente com o HLD e tecnicamente correto.

---

## Contexto de Ativação

Ative quando o lote contiver:
- Low Level Design (LLD)
- Documento de Configuração Detalhada
- Runbook de Implementação
- Guia de Parametrização

---

## Workflow de Análise LLD

### 1. Rastreabilidade LLD ↔ HLD

- Verifique se o LLD referencia o HLD correspondente (versão e data).
- Para cada elemento do HLD, verifique se há detalhamento correspondente no LLD.
- Elementos do HLD sem cobertura no LLD = **Lacuna de Detalhamento**.

### 2. Completude de Parametrização

Verifique se os seguintes itens estão presentes para cada componente:
- [ ] Endereçamento IP, VLANs, sub-redes
- [ ] Credenciais de acesso e protocolo de gerência (referência, não credenciais reais)
- [ ] Parâmetros de protocolo (versão, timers, thresholds)
- [ ] Sizing de hardware (CPU, memória, storage, interfaces)
- [ ] Configuração de HA/Failover com procedimento de teste
- [ ] Procedimento de rollback em caso de falha na implementação

### 3. Verificação de Consistência Técnica

- Verifique se os parâmetros são tecnicamente coerentes (ex: timer de hello vs timer de dead em protocolos de roteamento).
- Identifique configurações que criariam loops ou conflitos.
- Verifique se capacidades de hardware suportam os parâmetros configurados.

### 4. Implementabilidade

- O LLD é suficientemente detalhado para uma equipe técnica implementar sem perguntas adicionais?
- Existem dependências externas não documentadas?
- Existe plano de teste e aceite pós-implementação?

---

## Achados Típicos de LLD

| Tipo | Exemplo |
|------|---------|
| Lacuna | Componente presente no HLD sem qualquer parametrização no LLD |
| Inconsistência | LLD define VLAN 100 para gerência; HLD define VLAN 200 para a mesma função |
| Risco | Ausência de procedimento de rollback para componente crítico |
| Lacuna | Sizing de storage do servidor de logs não especificado |

---

## Saída Esperada

Registre os achados em `dados_analise.json` com categoria `LLD / Detalhamento` para exibição no `index.html`:
- Tabela de rastreabilidade: Componente HLD → Seção LLD → Status de Cobertura
- Achados de completude e consistência técnica (parâmetros, IPs, procedimentos)
