---
name: analisar-datacenter
description: Skill especializada para Revisão Técnica de Datacenters (Infraestrutura Tier III/IV, UPS, Climatização, Redundância 2N/N+1, Cabling Passivo).
---

# Skill: Análise Técnica de Infraestrutura de Datacenter (Facilities & Cabling)

Esta skill orienta o revisor técnico independente a auditar documentos de engenharia, RFPs, HLDs, LLDs e memoriais descritivos de **Infraestrutura Física de Datacenter (Tier III/IV, Energia, UPS, Grupos Geradores, Climatização HVAC/CRAC, Racks, Cabeamento Estruturado e DCIM)**.

---

## 🔍 Contexto de Ativação e Checklists Associados

- **Gatilhos:** Menções a Datacenter, Sala-Cofre, Tier III / Tier IV (Uptime Institute), ANSI/TIA-942, UPS/Nobreak, Gerador, PDU/STS, Climatização (CRAC/CRAH/In-Row), Cabeamento Estruturado, Rack/Colocation, DCIM.
- **Checklists Associados:**
  - `framework/checklists/datacenter.md`
  - `framework/checklists/arquitetura.md`
  - `framework/checklists/seguranca.md`

---

## 🛠️ Workflow de Análise de Datacenter

### 1. Classificação de Disponibilidade e Redundância (Tier / ANSI/TIA-942)
- Verificar se a classificação exigida ou declarada (ex: Tier III — *Concurrently Maintainable* ou Tier IV — *Fault Tolerant*) é acompanhada de evidência verificável (certificação de projeto/construção ou especificação explícita de subsistemas).
- Verificar se todos os caminhos críticos (alimentação elétrica, refrigeração e telecomunicações) respeitam o modelo de redundância declarado (`N+1`, `2N` ou `2(N+1)`), sem pontos únicos de falha (SPOF) ocultos.

### 2. Subsistema Elétrico (Subestação, Geradores, UPS, Baterias e PDUs)
- Verificar especificação de grupos motogeradores (GMG): regime de operação contínuo, partida automática, autonomia mínima de combustível em plena carga e contrato de reabastecimento.
- Verificar topologia de UPS (dupla conversão online, bancos independentes A/B), tempo mínimo de autonomia dos bancos de baterias (ex: ≥ 15 min a 100% de carga) e tecnologia das baterias (VRLA / Lítio).
- Verificar distribuição nos racks: PDUs duplas (vias A e B independentes), medição/gerenciamento remoto por tomada e chaves de transferência estática (ATS/STS) para equipamentos monofonte.

### 3. Subsistema de Climatização e Controle Ambiental (HVAC / CRAC)
- Verificar capacidade térmica (kW / TR por rack), redundância dos equipamentos de precisão (`N+1` ou `2N`), confinamento de corredor quente/frio e faixas de temperatura e umidade relativa conforme ASHRAE.
- Verificar continuidade de refrigeração durante a transição rede → gerador.

### 4. Espaço Físico, Racks, Cabeamento Estruturado e Segurança Física
- Verificar dimensões de racks (U disponíveis, profundidade, capacidade de carga estática/dinâmica), calhas separadas para fibra óptica e cabos metálicos, e conformidade com ANSI/TIA-942.
- Verificar sistemas de detecção precoce (laser/aspiração tipo VESDA) e combate a incêndio por agente limpo (ex: Novec 1230 / FM-200).
- Verificar controle de acesso físico (biometria, eclusa, CFTV com retenção mínima) e monitoramento ambiental centralizado via **DCIM** / BMS.

---

## 📌 Achados Típicos de Datacenter

| Tipo de Achado | Categoria | Exemplo Típico |
|---|---|---|
| **Lacuna** | Datacenter / Infraestrutura | Especificação exige ambiente de Datacenter de alta disponibilidade sem definir topologia de UPS (2N vs N+1), autonomia de baterias ou grupos geradores. |
| **Inconsistência** | Datacenter / Energia | Documento exige disponibilidade Tier III (manutenção concorrente), mas especifica caminho único de distribuição elétrica até os racks. |
| **Lacuna** | Datacenter / Climatização | Memorial técnico especifica densidade de 15 kW por rack sem detalhar a capacidade de refrigeração In-Row/CRAC nem o confinamento térmico. |
| **Risco** | Datacenter / Segurança Física | Ausência de exigência de sistema de detecção precoce de fumaça e extinção por gás agente limpo na sala de equipamentos. |
| **Lacuna** | Datacenter / Monitoramento | Não há previsão de sensores de temperatura/umidade por rack nem integração com plataforma DCIM/SNMP para alertas ambientais. |

---

## 📊 Saída Esperada (SSOT)

Registre os achados via `record_semantic_analysis` em `dados_analise.json` com a categoria `Datacenter / Infraestrutura`, populando o checklist `datacenter.md` para exibição no dashboard `index.html`.
