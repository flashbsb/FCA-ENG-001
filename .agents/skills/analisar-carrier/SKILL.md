---
name: analisar-carrier
description: Skill especializada para Revisão Técnica Independente (RTI) de operadoras de transporte (Carrier Telecom) com backbone nacional próprio (fibra apagada, DWDM, REDIP Core/Edge/Metro, SD-WAN, L2VPN, L3VPN, P2P, serviços Internet, Peering IXP/PNI e Route Reflectors BGP) e infraestrutura DCN (Data Communication Network).
---

# Skill: Análise Técnica Carrier Telecom & DCN (Operadora de Transporte Nacional)

Esta skill capacita o revisor técnico a auditar documentos de arquitetura, RFPs, HLDs, LLDs e especificações técnicas de **Operadoras de Transporte Telecom com Backbone Nacional Próprio**, englobando desde a camada de fibra apagada e óptica DWDM até a camada de roteamento IP, SD-WAN, serviços de transporte (P2P, L2VPN, L3VPN, Internet), Peering (IXP/PNI), BGP Route Reflectors e a rede DCN de suporte operacional.

---

## 🔍 Perfil do Escopo de Carrier Auditado

- **Perfil da Operadora:** Carrier de transporte multisserviço nacional (sem telefonia celular/mobile core).
- **Serviços Oferecidos:** 
  - Transporte IP/Banda Larga / Trânsito IP / Internet Dedicada (IP Transit).
  - P2P (Point-to-Point / Wavelengths dedicados / L2 P2P).
  - L2VPN (EVPN-VPWS, VPLS, EoMPLS, Carrier Ethernet MEF E-Line / E-LAN).
  - L3VPN (MPLS L3VPN, VRF Lite, SRv6 L3VPN).
  - SD-WAN (Overlay para integração de borda e clientes corporativos).
- **Infraestrutura Física & Óptica:**
  - **Fibra Apagada (Dark Fiber):** Contratos de direito de passagem (IRU), atenuação dB/km, dispersão cromática, PMD, relatórios OTDR, tipo de fibra (ITU-T G.652.D, G.655, G.657).
  - **Camada DWDM / OTN:** Transponders/Muxponders 100G/400G, ROADMs (Flex-grid, CDC - Colorless Directionless Contentionless), amplificadores EDFA/Raman, margem de OSNR, span budget, potências de canal.
- **Rede IP (REDIP - Core, Edge & Metro):**
  - **Core IP:** Roteadores de alto desempenho (chassi/terabit), arquitetura de roteamento dual-homed, IS-IS/OSPFv3, Segment Routing (SR-MPLS / SRv6), FRR (Fast Reroute < 50ms), BFD.
  - **Edge / PE (Provider Edge):** Roteadores de borda para terminação de L2VPN, L3VPN, QinQ, H-QoS, subinterfaces.
  - **Metro IP:** Anéis de acesso metro, proteção G.8032 ERPS, L2/L3 demarcation.
  - **SD-WAN:** Controllers centralizados, vEdge/cEdge, encriptação IPsec/DTLS, steering dinâmico por aplicação, integração com REDIP.
- **BGP & Peering (BGP Route Reflectors, IXP / PTT & PNI):**
  - Cluster de BGP Route Reflectors (RR) dedicados fora do caminho de dados (Out-Of-Band/In-Band control plane).
  - Ponto de Troca de Tráfego (IXP / PTT.br) e Conexões Privadas (PNI - Private Network Interconnection).
  - Políticas de Roteamento BGP: RPKI (ROA Validation), BGP Communities (Local-Pref, Blackhole, Prepend), anti-DDoS (BGP Flowspec, RTBH - Remote Triggered Blackhole).
- **DCN (Data Communication Network) & Gerência Carrier:**
  - **DCN Fabric:** Redes de gerência de datacenter/POP Spine-Leaf, EVPN-VXLAN, rede física/lógica Out-Of-Band (OOB) dedicada.
  - **VRFs de Gerência:** Segregação rígida por VRFs (OOB, Control Plane, Management, Internal POP Services).
  - **Interfaces Físicas & Optos:** 100GbE / 400GbE (QSFP28 / QSFP-DD / OSFP), optics SR4/LR4/FR4/ER4, cordões passivos.
  - **Telemetria Contínua & Observabilidade:** Streaming Telemetry (gNMI / gRPC / OpenConfig), BFD para detecção instantânea, polling SNMPv3.
  - **Acesso OOB & Custódia (Break-Glass):** Autenticação TACACS+/RADIUS, integração PAM (Privileged Access Management), cofre de senhas seladas, política de rotação compulsória de credenciais em até 24h.

---

## 🛠️ Workflow de Análise Carrier & DCN

### 1. Auditoria da Camada Física (Dark Fiber & DWDM)
- Verificar se o documento especifica os parâmetros de fibra apagada: trechos de cabo, distâncias (km), atenuação máxima por km, dispersão cromática e ensaios OTDR requeridos.
- Verificar se a camada DWDM especifica a margem de OSNR mínima, o span budget por enlace, o tipo de amplificação (EDFA/Raman), número de canais suportados e compatibilidade com ROADMs.
- Ausência de especificação de óptica/fibra em projetos de transporte nacional = **Lacuna Crítica (P0/P1)**.

### 2. Auditoria da Rede IP (REDIP Core, Edge, Metro & SD-WAN)
- Verificar a segregação e clareza de atribuições das camadas Core, Edge (PE) e Metro.
- Verificar os protocolos de roteamento interno (IGP: IS-IS / OSPFv3) e o tempo de convergência/recuperação (< 50ms com BFD + SR-FRR).
- Para serviços de transporte (P2P, L2VPN, L3VPN): verificar se os parâmetros de MTU (suporte a Jumbo Frames ≥ 9100 bytes), H-QoS (priorização de voz/vídeo/dados) e identificadores de VLAN/VRF estão explicitados.
- Para a camada SD-WAN: verificar a arquitetura de controle (redundância de controllers), encriptação de overlays, integração com o Backbone Core e failover automático entre links primários e secundários.

### 3. Auditoria de Roteamento BGP, Peering e RPKI
- Verificar a arquitetura de BGP Route Reflectors (redundância de RRs em POPs distintos, cluster ID, prevenções de loop BGP).
- Verificar políticas de Peering (IXP/PTT e PNI): RPKI ROA Validation ativo, filtragem de bogons, limites de prefixos recebidos (max-prefix).
- Verificar proteção contra ataques volumétricos: suporte a BGP Flowspec (RFC 8955/5575) e BGP Remote Triggered Blackhole (RTBH).

### 4. Auditoria de DCN (Data Communication Network) & Infraestrutura de Gerência
- Verificar se a rede DCN possui segregação física e lógica Out-Of-Band (OOB) dedicada.
- Verificar a conectividade física entre Switches DCN (Core/Spine/Leaf) e Firewalls (interfaces 100G/400G, part-numbers de optics, comprimentos de cordões de fibra).
- Verificar o protocolo de instrumentação: se adota Streaming Telemetry (gNMI/gRPC) suplementado por SNMPv3 trap para eventos assíncronos.
- Verificar a política de Break-Glass: se as contas de administrador local dos elementos DCN possuem procedimento de selagem no PAM corporativo e rotação automática compulsória após acionamento de contingência.

### 5. Auditoria de Metrologia e SLAs Carrier (5-Nines)
- Verificar se a disponibilidade mínima contratual/arquitetural é ≥ 99,999% (ou justificada em contrato).
- Verificar se os KPIs de rede incluem: RTT/Latência máxima por trecho (ms), Jitter (ms), Perda de Pacotes (%), e tempo médio de reparo (MTTR ≤ 4h).
- Verificar se há referência aos procedimentos normalizados de teste de aceite (ITU-T Y.1564 / RFC 2544 / MEF 3.0).

---

## 📌 Achados Típicos de Carrier & DCN

| Tipo de Achado | Categoria | Exemplo Típico |
|---|---|---|
| **Lacuna** | Física / DWDM | Contrato de fibra apagada não especifica o limite máximo de atenuação por km (dB/km) nem exige laudos de OTDR. |
| **Inconsistência** | REDIP IP/MPLS | HLD exige convergência sub-50ms mas não especifica a ativação do BFD e SR-FRR no backbone Core. |
| **Lacuna** | BGP & Peering | Arquitetura BGP de Peering (IXP/PNI) não especifica a validação de RPKI nem limite máximo de prefixos (max-prefix). |
| **Lacuna** | DCN & Conectividade | HLD da DCN omite os part-numbers dos transceivers 100GbE (QSFP28 SR4 vs LR4) na interconexão entre Core e Firewalls. |
| **Inconsistência** | Observabilidade DCN | Tabela de monitoramento indica coleta por SNMP polling a cada 5min em vez de Streaming Telemetry (gNMI/gRPC). |
| **Risco** | Segurança DCN / Break-Glass | Credenciais locais de contingência dos roteadores DCN mantidas em planilha estática sem rotação automática via PAM. |
| **Inconsistência** | SD-WAN / Overlay | SD-WAN exige MTU de 1500 bytes no overlay sem considerar o overhead do cabeçalho IPsec, causando fragmentação no backbone. |

---

## 📊 Registros em `dados_analise.json`

Ao identificar achados na auditoria Carrier, registre-os com a categoria `Carrier Telecom & DCN` em `dados_analise.json` e popule o checklist `carrier.md` para renderização nativa na interface HTML (`index.html`).
