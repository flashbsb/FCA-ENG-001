# Checklist Carrier Telecom & DCN (Operadora de Transporte Nacional)

| Verificação | Evidência esperada |
|---|---|
| Parâmetros de fibra apagada (atenuação dB/km, dispersão, OTDR) e especificação ópticas DWDM (OSNR, span budget, ROADMs) documentados | Especificação técnica / Anexo óptico |
| Topologia da REDIP (Core, Edge, Metro) com redundância e dual-homing definidos | Diagramas de topologia e redundância |
| Mecanismos de alta velocidade de convergência (SR-FRR, BFD < 50ms) especificados no Core IP | HLD/LLD — Roteamento IP |
| Especificação de serviços de transporte (P2P, L2VPN EVPN/VPLS, L3VPN) com MTU (Jumbo Frames ≥ 9100) e H-QoS | Matriz de serviços / SLA |
| Arquitetura SD-WAN de borda integrada ao Backbone Core com redundância de controllers e encriptação IPsec/DTLS | HLD SD-WAN / Topologia |
| Arquitetura de BGP Route Reflectors (RR) dedicados com redundância multi-site | Seção Roteamento BGP |
| Políticas de Peering (IXP/PTT e PNI) com validação RPKI (ROA), max-prefix e BGP Flowspec / RTBH anti-DDoS | Seção BGP Peering / Segurança |
| Infraestrutura DCN (Spine-Leaf Fabric, EVPN-VXLAN) e segregação por VRFs (OOB, Control Plane, Management) | HLD DCN / Matriz de VRFs |
| Especificação física e ópticas da DCN (100GbE/400GbE, part-numbers de transceivers SR4/LR4, cordões de fibra passivos) | Matriz de interfaces DCN |
| Instrumentação por Streaming Telemetry (gNMI/gRPC/OpenConfig) suplementada por SNMPv3 traps na DCN e REDIP | Seção Observabilidade / Telemetria |
| Custódia e rotatividade compulsória de senhas locais seladas (Break-Glass / PAM) nos elementos DCN e Roteadores | Seção Segurança de Acesso / PAM |
| SLAs/KPIs Carrier 5-Nines (99,999%), RTT/Latência, Jitter, Perda de Pacotes e testes ITU-T Y.1564 / MEF 3.0 | Cláusula de SLA / Metrologia |
