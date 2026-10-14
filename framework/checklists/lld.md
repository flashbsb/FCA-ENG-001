# Checklist de Análise de LLD (Low Level Design)

| Verificação | Evidência Esperada | Destino do Registro |
|-------------|-------------------|---------------------|
| LLD referencia o HLD correspondente com versão e data | Referência explícita | `index.html #fichas` |
| Todos os componentes do HLD têm detalhamento no LLD | Cobertura 1:1 | `index.html #lacunas-riscos` |
| Endereçamento IP e VLANs especificados por componente | Tabela de endereçamento | `index.html #fichas` |
| Parâmetros de protocolo especificados (versão, timers, thresholds) | Valores por protocolo | `index.html #fichas` |
| Sizing de hardware especificado (CPU, RAM, storage, interfaces) | Tabela de sizing | `index.html #lacunas-riscos` |
| Configuração de HA/Failover com procedimento de teste | Procedimento documentado | `index.html #fichas` |
| Procedimento de rollback definido para cada componente crítico | Passos de rollback | `index.html #lacunas-riscos` |
| Plano de teste e aceite pós-implementação definido | Critérios de aceite | `index.html #fichas` |
| Consistência entre parâmetros LLD e valores do HLD | Comparação direta | `index.html #fichas` |
| Dependências externas documentadas | Lista de dependências | `index.html #lacunas-riscos` |
| Credenciais referenciadas por vault/secret (nunca em texto claro) | Política de credenciais | `index.html #fichas` |
| Versão e data do LLD registradas no cabeçalho | Metadados do documento | `index.html #fichas` |
