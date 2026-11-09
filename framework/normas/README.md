# Catálogo de Referências Normativas (FCA-ENG-001)

Este diretório consolida o catálogo de normas técnicas, padrões de engenharia e marcos regulatórios de referência aplicáveis durante a **Revisão Técnica Independente (RTI)** conforme a **Seção 17** de [`framework/revisao.md`](../revisao.md).

> **Regra de Aplicabilidade (Seção 17 do FCA-ENG-001):** Uma norma só é considerada de cumprimento obrigatório quando contrato, edital, regulação ou escopo documental a vincular expressamente. Quando utilizada como referência técnica voluntária de engenharia, deve ser rotulada como **Boa Prática** ou **Referência Corroborativa (E2)**.

---

## 1. Rigor Redacional, Engenharia de Requisitos e Metrologia (Pilar 7)

| Entidade / Código | Título / Escopo | Aplicação na RTI | Checklist Associado |
|---|---|---|---|
| **IETF RFC 2119** | *Key words for use in RFCs to Indicate Requirement Levels* | Verificação de verbos normativos estritos (`DEVE` / `MUST`, `RECOMENDA-SE` / `SHOULD`, `PODE` / `MAY`) e detecção de termos ambíguos ("em princípio", "desejável"). | `rfc.md`, `editorial.md` |
| **IETF RFC 8174** | *Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words* | Distinção inequívoca de obrigatoriedade normativa por caixa alta e precisão redacional. | `rfc.md`, `editorial.md` |
| **ISO/IEC/IEEE 29148** | *Systems and software engineering — Life cycle processes — Requirements engineering* | Critérios de completude, não-ambiguidade, verificabilidade e testabilidade quantitativa de requisitos funcionais e não funcionais. | `iso.md`, `rfp.md`, `editorial.md` |
| **ISO 8601** | *Date and time — Representations for information interchange* | Padronização de datas, janelas operacionais e obrigatoriedade de fuso horário explícito (`BRT` / `UTC-3`) em SLAs e cronogramas. | `iso.md`, `contratos.md`, `editorial.md` |
| **ISO 80000 / SI** | *Quantities and units (International System of Units)* | Padronização de grandezas e unidades de medida (distinção estrita entre `Gbps` / bits por segundo e `GB/s` / bytes por segundo, potências decimais vs. binárias). | `iso.md`, `editorial.md`, `tabelas.md` |

---

## 2. Telecomunicações, Carrier Backbone, Redes IP e Transporte Óptico

| Entidade / Código | Título / Escopo | Aplicação na RTI | Checklist Associado |
|---|---|---|---|
| **ITU-T G.652 / G.655 / G.657** | *Characteristics of single-mode optical fibre and cable* | Auditoria de parâmetros físicos de fibra apagada (atenuação dB/km, dispersão cromática, PMD). | `carrier.md` |
| **ITU-T G.694.1 / G.709 / G.872** | *Spectral grids for WDM applications / OTN interfaces* | Especificação de canais DWDM, ROADMs, FEC, OSNR mínima e span budget óptico. | `carrier.md` |
| **ITU-T Y.1564** | *Ethernet service activation test methodology (EtherSAM)* | Metodologia de teste de ativação e aceite de serviços Carrier Ethernet (CIR, EIR, Frame Loss, Jitter, Latência). | `carrier.md`, `mef.md` |
| **IETF RFC 2544** | *Benchmarking Methodology for Network Interconnect Devices* | Testes de throughput, latência, frame loss e back-to-back em enlaces de transporte. | `carrier.md`, `rfc.md` |
| **IETF RFC 5880 / RFC 8955 / RFC 6811** | *BFD / BGP Flow Specification / BGP Prefix Origin Validation (RPKI)* | Convergência sub-50ms (BFD), mitigação anti-DDoS (Flowspec) e segurança de roteamento BGP (RPKI ROA). | `carrier.md`, `rfc.md` |
| **MEF 3.0 (MEF 6.3 / 10.4 / 26.2)** | *Carrier Ethernet Services & Attributes (E-Line, E-LAN, E-Tree, E-Access)* | Demarcação UNI/ENNI, parâmetros de largura de banda, CoS e SLAs de transporte L2VPN. | `mef.md`, `carrier.md` |

---

## 3. Datacenter, Cloud, Arquitetura, OSS/BSS e Integrações

| Entidade / Código | Título / Escopo | Aplicação na RTI | Checklist Associado |
|---|---|---|---|
| **ANSI/TIA-942 / Uptime Tier** | *Telecommunications Infrastructure Standard for Data Centers* | Topologia de redundância elétrica/mecânica (N+1, 2N), autonomia de UPS/geradores e cabeamento estruturado. | `datacenter.md` |
| **TM Forum Open APIs / Frameworx** | *eTOM (Business Process), SID (Information), TAM & Open APIs (TMF6xx)* | Padronização de integrações OSS/BSS, catálogos de produtos, ordens de serviço, inventário e bilhetagem. | `tm_forum.md`, `oss.md`, `bss.md`, `integracoes.md` |
| **IEEE 802.1Q / 802.1AX / 802.3** | *VLAN Bridging, Link Aggregation (LACP) & Ethernet Standards* | Segmentação L2, QinQ, agregação de links e interfaces ópticas 10G/40G/100G/400GbE. | `ieee.md`, `arquitetura.md`, `lld.md` |
| **ITIL v4** | *Information Technology Infrastructure Library* | Governança operacional, gestão de incidentes, problemas, mudanças (GMUD), configuração (CMDB) e níveis de serviço (SLA/OLA). | `itil.md`, `contratos.md` |

---

## 4. Cibersegurança, Privacidade e Proteção de Dados

| Entidade / Código | Título / Escopo | Aplicação na RTI | Checklist Associado |
|---|---|---|---|
| **Lei nº 13.709/2018 (LGPD)** | *Lei Geral de Proteção de Dados Pessoais* | Verificação documental de finalidade, base legal (Arts. 7º/11), direitos do titular, retenção, DPO e notificação à ANPD. | `lgpd.md`, `seguranca.md`, `contratos.md` |
| **ABNT NBR ISO/IEC 27001 / 27002** | *Segurança da informação, segurança cibernética e proteção à privacidade* | Controles de acesso (IAM/RBAC/PAM), criptografia em trânsito e repouso, segregação de ambientes e trilha de auditoria. | `iso.md`, `seguranca.md` |
| **NIST SP 800-53 / CSF** | *Security and Privacy Controls for Information Systems and Organizations* | Arquitetura de defesa em profundidade, gestão de vulnerabilidades, monitoramento contínuo (SIEM/SOC) e resposta a incidentes. | `seguranca.md`, `cloud.md` |
