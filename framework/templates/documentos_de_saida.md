# Contrato Corporativo dos Documentos de Saída (FCA-ENG-001 v2.1.0)

Cada execução do procedimento de **Revisão Técnica Independente (RTI)** gera a base de dados estruturada SSOT em JSON (`analise/<timestamp>/relatorios/dados_analise.json`) e o parecer executivo consolidado em HTML (`analise/<timestamp>/relatorios/index.html`).

> [!NOTE]
> A partir da versão v2.1.0 (Fase 1), os relatórios legados em formato Markdown (`.md`) foram descontinuados para evitar redundâncias e dessincronizações de dados. Toda a entrega ocorre exclusivamente via `index.html` alimentado nativamente pelo `dados_analise.json`.

---

## 1. Base Estruturada SSOT (`dados_analise.json`)

Armazena 100% dos dados estruturados da RTI para auditoria e rastreabilidade total:
- **Metadata & Parecer:** Título, timestamp, parecer técnico e resumo de KPIs.
- **Baseline Files:** Lista imutável de arquivos com tamanho e hashes SHA-256.
- **Skills Ativas:** Agentes e skills ativadas na triagem adaptativa.
- **Fichas 360° (Findings):** Objetos atômicos com ID, documento de origem, localização exata, fatos, impactos, criticidade, prioridade, substituições De->Para e soluções recomendadas.
- **Erratas, Planos de Ação (`ACT-00X`), Perguntas Formais (`Q-00X`), Lacunas e Riscos.**
- **Status dos Checklists de Domínio.**

---

## 2. Central Executiva HTML Consolidada (`index.html`)

O arquivo `index.html` oferece um dashboard interativo moderno organizado nas 8 seções executivas:

1. **1. Resumo Executivo & Matriz de Skills (`#resumo`):** Card Hero com parecer, KPIs, inventário da baseline e badges de skills.
2. **2. Matriz Master SSOT (`#matriz-master`):** Tabela panorâmica consolidada de todos os achados com links diretos para as Fichas 360°.
3. **3. Caderno de Fichas 360° Detalhadas (`#fichas`):** Cards responsivos com busca em tempo real e filtros interativos.
4. **4. Caderno de Erratas De → Para (`#erratas`):** Tabela de propostas de substituição redacional direta com botão de cópia.
5. **5. Planos de Ação & Perguntas Formais (`#acoes-perguntas`):** Tabelas estruturadas para planos de ação (`ACT-00X`) e ofícios de esclarecimento (`Q-00X`).
6. **6. Mapeamento de Lacunas Estratégicas & Matriz de Riscos (`#lacunas-riscos`):** Mapeamento de lacunas e riscos.
7. **7. Status de Conformidade por Checklist (`#checklists`):** Status dos checklists aplicados por domínio técnico.
8. **8. Hashes SHA-256 & Rastreabilidade (`#rastreabilidade`):** Rastreabilidade de baseline e log auditável de execução.

5. **Capítulo 3: Central de Ações & Cópia com 1 Clique:**
   - Caderno de Erratas e Redações (De->Para) com botão "Copiar Texto Corrigido".
   - Ofício de Perguntas Formais para a comissão/fornecedor.
   - Matriz de Governança e Planos de Ação por responsável.
6. **Estilo `@media print` para Exportação PDF Impede Cortes:** O navegador converte automaticamente para um relatório limpo em fundo branco, expande 100% dos cards e aplica quebras de página perfeitas sem cortar tabelas.



