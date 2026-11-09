---
name: analisar-cloud
description: Skill especializada para Revisão Técnica de Arquiteturas em Nuvem (Multi-Cloud AWS/Azure/GCP, OpenStack, Kubernetes, Serverless).
---

# Skill: Análise Técnica de Arquiteturas em Nuvem (Cloud & Containers)

Esta skill orienta o revisor técnico independente a auditar documentos de arquitetura, RFPs, HLDs, LLDs e especificações técnicas que envolvam **ambientes em Nuvem Pública, Privada ou Híbrida (AWS, Azure, GCP, OCI, OpenStack), Orquestração de Containers (Kubernetes/OpenShift) e computação Serverless**.

---

## 🔍 Contexto de Ativação e Checklists Associados

- **Gatilhos:** Menções a IaaS, PaaS, SaaS, AWS, Azure, GCP, OpenStack, Kubernetes, EKS/AKS/GKE, OpenShift, VPC/VNet, Multi-AZ, Serverless, FinOps.
- **Checklists Associados:**
  - `framework/checklists/cloud.md`
  - `framework/checklists/arquitetura.md`
  - `framework/checklists/seguranca.md`

---

## 🛠️ Workflow de Análise Cloud

### 1. Modelo de Responsabilidade Compartilhada e Governança
- Verificar se a matriz de responsabilidades entre Provedor de Nuvem (CSP), Integrador/Contratada e Contratante está claramente delimitada (patch management, backup, configuração de segurança, gestão de chaves).
- Verificar especificações de localização geográfica / residência de dados (região primária e secundária) em conformidade com requisitos legais e de latência.

### 2. Identidade, Acesso e Segurança (IAM / KMS / Zero Trust)
- Verificar controles de Gestão de Identidades e Acessos (IAM, RBAC, federação SSO/SAML/OIDC, MFA obrigatório e princípio do menor privilégio).
- Verificar gestão de segredos e chaves criptográficas (KMS/HSM, BYOK, criptografia em trânsito TLS 1.2+/1.3 e em repouso AES-256).

### 3. Topologia de Rede, Conectividade e Segmentação
- Verificar o desenho de rede em nuvem: VPC/VNet, sub-redes públicas/privadas, Security Groups, NACLs, WAF, DDoS Protection e Ingress/Egress Controllers.
- Verificar conectividade híbrida quando aplicável (Direct Connect / ExpressRoute / Cloud Interconnect / VPN IPsec redundante) com SLA e largura de banda definidos.

### 4. Resiliência, Alta Disponibilidade e Recuperação de Desastres (DR)
- Verificar distribuição Multi-AZ / Multi-Region para workloads críticos.
- Verificar definição explícita e quantificada de **RTO** (Recovery Time Objective) e **RPO** (Recovery Point Objective), políticas de snapshot/backup imutável e testes de restore.
- Para Kubernetes/Containers: verificar alta disponibilidade do Control Plane, políticas de autoscaling (HPA/VPA/Cluster Autoscaler), limites de recursos (`requests`/`limits`), Pod Disruption Budgets (PDB) e persistência de storage (CSI).

### 5. Observabilidade, Operação e Portabilidade
- Verificar centralização de logs, métricas, traces (OpenTelemetry / Prometheus / SIEM) e alertas operacionais.
- Verificar estratégia de provisionamento como código (IaC — Terraform, Helm, GitOps) e mitigação de aprisionamento tecnológico (*vendor lock-in*).

---

## 📌 Achados Típicos de Cloud

| Tipo de Achado | Categoria | Exemplo Típico |
|---|---|---|
| **Lacuna** | Cloud / Arquitetura | Arquitetura em nuvem não especifica a distribuição Multi-AZ nem define metas numéricas de RTO e RPO para recuperação de desastres. |
| **Lacuna** | Cloud / Segurança | Especificação omite o modelo de responsabilidade compartilhada e a política de IAM/RBAC com MFA para contas privilegiadas. |
| **Inconsistência** | Cloud / Containers | HLD declara cluster Kubernetes de alta disponibilidade, mas especifica apenas 2 nós no Control Plane (impossibilitando quorum etcd em falha). |
| **Risco** | Cloud / Conectividade | Integração entre datacenter on-premises e nuvem depende de túnel VPN único pela internet pública sem link dedicado redundante. |
| **Lacuna** | Cloud / Observabilidade | Ausência de especificação para retenção de logs de auditoria da conta Cloud (CloudTrail / Activity Log) e integração ao SIEM. |

---

## 📊 Saída Esperada (SSOT)

Registre os achados via `record_semantic_analysis` em `dados_analise.json` com a categoria `Cloud / Arquitetura`, populando o checklist `cloud.md` para exibição no dashboard `index.html`.
