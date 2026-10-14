# Checklist de Análise de HLD (High Level Design)

| Verificação | Evidência Esperada | Destino do Registro |
|-------------|-------------------|---------------------|
| Objetivo e escopo da arquitetura declarados | Seção de escopo | `index.html #fichas` |
| Diagrama de topologia de alto nível presente | Figura/diagrama | `index.html #fichas` |
| Lista de componentes com responsabilidade de cada um | Tabela de componentes | `index.html #lacunas-riscos` |
| Fluxos de dados entre componentes descritos | Diagrama de fluxo | `index.html #fichas` |
| Requisitos de disponibilidade com SLA especificado | SLA numérico | `index.html #lacunas-riscos` |
| Esquema de redundância declarado (2N, N+1, Active/Active) | Texto + diagrama | `index.html #fichas` |
| Ausência de SPOFs não documentados como risco aceito | Verificação topológica | `index.html #lacunas-riscos` |
| Requisitos de desempenho quantificados (throughput, latência, IOPS) | Valores mensuráveis | `index.html #lacunas-riscos` |
| Requisitos de escalabilidade definidos com limites explícitos | Capacidade máxima | `index.html #fichas` |
| Interfaces de integração com protocolo especificado | Protocolo + versão | `index.html #lacunas-riscos` |
| Segurança arquitetural: zonas, DMZ, segmentação | Diagrama de segurança | `index.html #fichas` |
| Premissas e restrições declaradas explicitamente | Seção de premissas | `index.html #fichas` |
| Rastreabilidade HLD → Requisitos da RFP/Contrato | Tabela de rastreabilidade | `index.html #rastreabilidade` |
| RTO e RPO definidos para componentes críticos | Valores de RTO/RPO | `index.html #lacunas-riscos` |
| Versão e data do HLD registradas no cabeçalho | Metadados do documento | `index.html #fichas` |
