---
name: analisar-hld
description: Skill especializada para Revisão Técnica de High Level Designs (HLD) e documentos de arquitetura de alto nível. Verifica topologia, redundância, escalabilidade, interoperabilidade, requisitos não funcionais, alinhamento com padrões de mercado e coerência entre a visão arquitetural descrita e os componentes listados.
---

# Skill: Análise de HLD (High Level Design)

Esta skill especializa a RTI para documentos de arquitetura de alto nível, verificando se o design proposto atende aos requisitos declarados e é tecnicamente consistente, viável e rastreável.

---

## Contexto de Ativação

Ative quando o lote contiver:
- High Level Design (HLD)
- Documento de Arquitetura de Solução
- Arquitetura de Referência
- Solução Técnica de Alto Nível

---

## Workflow de Análise HLD

### 1. Verificação de Completude Estrutural do HLD

Verifique se o documento contém:
- [ ] Objetivo e escopo da arquitetura
- [ ] Diagrama de topologia de alto nível
- [ ] Lista de componentes/módulos com responsabilidade de cada um
- [ ] Fluxos de dados entre componentes
- [ ] Requisitos não funcionais (disponibilidade, desempenho, escalabilidade, segurança)
- [ ] Premissas e dependências externas
- [ ] Restrições conhecidas
- [ ] Padrões e referências normativas aplicadas
- [ ] Maturidade decisória: separação clara entre conteúdo conceitual/didático de fabricante e definições fechadas do projeto (sem alternativas com `"ou"`, validações adiadas para laboratório sem critério objetivo de aceite ou encerramento sem conclusão/RACI/aprovação)

Ausência de qualquer item acima = **Lacuna** com Criticidade conforme impacto no objetivo.

### 2. Análise de Redundância e Alta Disponibilidade

- Identifique o esquema de HA declarado (2N, N+1, Active/Passive, Active/Active).
- Verifique se o diagrama suporta o esquema declarado (sem SPOFs não documentados).
- Para Datacenter: verificar Tier declarado vs recursos de energia, refrigeração e conectividade descritos.
- Para redes: verificar dual-homing, anel de proteção, diversidade de percurso.

### 3. Análise de Escalabilidade e Viabilidade Hardware × Firmware × BoM

- O design suporta crescimento horizontal ou vertical? Há declaração explícita dos limites?
- Existem gargalos arquiteturais não endereçados?
- Verifique compatibilidade funcional **Hardware (RAM/CPU/portas físicas) × Versão de Firmware recomendada × Subscrições contratadas na BoM** (ex.: modelos com <= 2 GB RAM não suportam recursos baseados em Proxy em versões recentes do FortiOS, impossibilitando a entrega de *Video Filtering* ou proxy-UTM mesmo se adquiridos na BoM; limites reais de túneis em malha dupla e capacidade de portas WAN/ópticas).
- Verifique o modelo de licenciamento por instância lógica (**VDOMs**, tenants, nós de cluster escalável) frente aos totais da BoM.

### 4. Análise de Interoperabilidade e Integrações

- Identifique todas as interfaces de integração declaradas.
- Verifique se os protocolos e padrões de interface estão especificados (ex: REST, NETCONF, SNMP, TM Forum APIs).
- Interfaces sem protocolo definido = Lacuna.

### 5. Alinhamento Requisitos × Design

- Para cada requisito funcional/não funcional declarado no documento referenciado (RFP, Contrato, etc.), verifique se há correspondência explícita no HLD.
- Requisito sem cobertura no design = achado de Lacuna de Cobertura.

### 6. Análise de Segurança Arquitetural, PKI e Criptografia

- Identifique zonas de segurança, DMZs, segmentação de rede.
- Verifique se há declaração de controle de acesso, autenticação e criptografia para cada fluxo de dados sensível.
- Verifique prontidão da infraestrutura de **PKI / CA / HSM** (túneis, *Deep SSL Inspection* sem chave privada CA única compartilhada em CPEs de campo, certificados de portais administrativos e previsão em BoM) e fechamento arquitetural de elementos dedicados de **criptografia de Estado** (*WAN-to-WAN* vs. *HSM/CA*), sem postergação indefinida para laboratório.

---

## Achados Típicos de HLD

| Tipo | Exemplo |
|------|---------|
| Lacuna | HLD descreve cluster de 3 nós mas não especifica o mecanismo de quorum |
| Inconsistência | Diagrama mostra 2 links de uplink; texto descreve 4 links de uplink |
| Risco | Único ponto de falha (SPOF) na camada de controle não documentado como risco aceito |
| Lacuna | Requisito de RTO=4h da RFP sem correspondência na arquitetura de DR proposta |
| Ambiguidade | "Alta disponibilidade" declarada sem SLA ou esquema de redundância especificado |

---

## Saída Esperada

Registre os achados em `dados_analise.json` com categoria `HLD / Arquitetura` para exibição no `index.html` com:
- Checklist de completude estrutural (conforme/não conforme/não verificável)
- Achados de redundância, escalabilidade e integração
- Tabela de rastreabilidade: Requisito → Elemento de Design → Status de Cobertura
