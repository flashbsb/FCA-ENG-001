---
name: analisar-integracoes
description: Skill especializada para Revisão Técnica de Integrações, Barramentos ESB, REST/SOAP APIs e TM Forum Open APIs.
---

# Skill: Análise Técnica de Integrações, APIs, Mensageria e TM Forum

Esta skill orienta o revisor técnico independente a auditar especificações de **Integrações de Sistemas, APIs REST/SOAP/gRPC, Gateways de API, Barramentos de Serviço (ESB), Mensageria Assíncrona (Kafka/RabbitMQ/AMQP) e aderência às TM Forum Open APIs (OSS/BSS)**.

---

## 🔍 Contexto de Ativação e Checklists Associados

- **Gatilhos:** Menções a API, REST, SOAP, GraphQL, gRPC, Webhook, ESB, API Gateway, Kafka, Mensageria, OpenAPI/Swagger, WSDL, TM Forum (TMF6xx, eTOM, SID, Open Digital Architecture).
- **Checklists Associados:**
  - `framework/checklists/integracoes.md`
  - `framework/checklists/tm_forum.md`
  - `framework/checklists/arquitetura.md`

---

## 🛠️ Workflow de Análise de Integrações

### 1. Catálogo e Contratos de Interface
- Verificar se cada integração possui **sistema produtor (origem)**, **sistema consumidor (destino)**, protocolo de transporte, direção do fluxo e responsável técnico definidos.
- Verificar se os contratos de interface estão especificados (OpenAPI/Swagger 3.x para REST, WSDL/XSD para SOAP, Protobuf para gRPC, schemas Avro/JSON para eventos Kafka).
- Verificar política de versionamento de APIs (ex: `/v1/`, `/v2/`) e retrocompatibilidade.

### 2. Segurança de Integração e Controle de Acesso
- Verificar mecanismos de autenticação e autorização entre sistemas: OAuth 2.0 / OIDC (Client Credentials), mTLS (autenticação mútua por certificado), chaves de API rotacionáveis e validação de escopos/claims JWT.
- Verificar proteção de borda no API Gateway: *rate limiting*, *throttling*, validação de payload e proteção contra abuso (OWASP API Security).

### 3. Resiliência, Tratamento de Erros e Idempotência
- Verificar especificação de timeouts de conexão/leitura, políticas de *retry* com *exponential backoff + jitter*, *Circuit Breaker* e *Dead Letter Queues (DLQ)* para filas/tópicos assíncronos.
- Verificar exigência de **idempotência** (`Idempotency-Key`) em operações de escrita/transacionais para evitar duplicidade de ordens, bilhetes ou cobranças em caso de retentativa.

### 4. Modelo de Dados, Volumetria e Desempenho
- Verificar se há mapeamento de campos/payloads (De → Para de atributos, codificação UTF-8, formato de datas ISO 8601).
- Verificar se a volumetria (TPS / requisições por segundo, tamanho máximo de payload, janela de sincronismo batch vs. tempo real) está declarada.

### 5. Conformidade TM Forum (Quando Aplicável a OSS/BSS)
- Quando o documento mencionar **TM Forum / Open APIs**, verificar se os códigos específicos das APIs (ex: `TMF620 Product Catalog`, `TMF622 Product Ordering`, `TMF638 Service Inventory`, `TMF642 Alarm Management`) e suas respectivas versões estão identificados.
- Distinguir entre exigência de **certificação oficial TM Forum** e simples **aderência/compatibilidade ao modelo de dados**.

---

## 📌 Achados Típicos de Integrações

| Tipo de Achado | Categoria | Exemplo Típico |
|---|---|---|
| **Lacuna** | Integrações / APIs | Documento exige integração com sistemas legados de CRM e ERP, mas não especifica os protocolos (REST/SOAP), contratos de payload nem volumetria (TPS). |
| **Lacuna** | Integrações / Segurança | Especificação de APIs externas omite o mecanismo de autenticação (mTLS / OAuth 2.0) e políticas de *rate limiting* no API Gateway. |
| **Risco** | Integrações / Resiliência | Integração crítica de provisionamento síncrono sem definição de timeout, política de *retry*, fila de contingência (DLQ) ou chave de idempotência. |
| **Ambiguidade** | TM Forum / OSS-BSS | RFP exige que a solução seja "100% compatível com TM Forum" sem listar quais Open APIs (TMF6xx) e versões fazem parte do escopo obrigatório. |
| **Inconsistência** | Integrações / Dados | Diagrama de integração indica fila assíncrona Kafka, enquanto a especificação textual descreve chamada síncrona SOAP/XML. |

---

## 📊 Saída Esperada (SSOT)

Registre os achados via `record_semantic_analysis` em `dados_analise.json` com a categoria `Integrações / APIs`, populando os checklists `integracoes.md` e `tm_forum.md` para exibição no dashboard `index.html`.
