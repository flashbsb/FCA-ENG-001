# Procedimento Corporativo de Revisão Técnica Independente (RTI)

**Identificador:** FCA-ENG-001  
**Versão:** 1.3.0  
**Estado:** Baseline interna de governança documental e engenharia  
**Aplicação:** Telecom, datacenter, OSS/BSS, segurança, cloud, arquitetura, RFP/RFQ, contratos e estudos técnicos.

## 1. Objetivo

Definir um processo repetível, independente e baseado em evidências para realizar a **Revisão Técnica Independente (RTI)** da qualidade, coerência e verificabilidade de documentos de engenharia. O procedimento registra observações, pontos de atenção e seus impactos; não cria requisitos, dimensionamentos, SLAs, arquitetura, cronogramas, cláusulas ou decisões em nome do autor.

## 2. Escopo

Aplica-se a documentos de entrada e às relações entre eles, inclusive anexos, tabelas, figuras, diagramas, referências, versões e artefatos visuais avulsos ou extraídos (`.png`, `.jpg`). A revisão pode concluir que não há evidência suficiente; essa conclusão é válida e não deve ser preenchida com suposições.

## 3. Definições

**Revisão Técnica Independente (RTI)** identifica e evidencia pontos de atenção, lacunas e riscos documentais. **Consultoria** desenha solução; é atividade separada, autorizada e rotulada. **Ponto de Atenção / Ajuste** é registro verificável. **Evidência** é trecho, artefato, versão ou fonte recuperável. **Lacuna** é informação necessária ao objetivo declarado, mas ausente. **Hipótese** é premissa não comprovada, sempre rotulada. **Recomendação** orienta decisão sem criar obrigação. **Proposta de Redação** é alternativa não oficial, condicionada à validação do proprietário.

## 4. Papéis

| Papel | Segregação mínima |
|---|---|
| Patrocinador | Define objetivo, escopo e destinatário; não altera evidência. |
| Gestor da Revisão | Aprova plano, independência, qualidade e emissão. |
| Revisor Técnico Independente | Coleta evidência, formula e revisa observações técnicas. |
| Especialista de Domínio | Faz revisão por pares, sem substituir o revisor. |
| Controlador Documental | Mantém baseline, hash, versões e acesso. |
| Proprietário do Documento | Responde, aceita ou rejeita ações; não modifica o parecer emitido. |
| Jurídico/Compras | Avalia consequência contratual; não transforma parecer técnico em decisão jurídica. |

## 5. Responsabilidades

O revisor técnico mantém rastreabilidade e independência. O proprietário fornece fontes e esclarecimentos. O gestor decide se a cobertura é suficiente. A aprovação de uma ação pertence ao proprietário competente; a revisão técnica não publica errata, edital, SLA ou texto vinculante.

## 6. Fluxo de Revisão Técnica (RTI)

1. Registrar demanda, propósito, escopo, exclusões e classificação da informação.
2. Inicializar o `TIMESTAMP` no formato `YYYYMMDD_HHMMSS` e criar a estrutura em `analise/<timestamp>/`.
3. **Triagem Adaptativa e Pausa Interativa de Escopo (Passo 0):** Executar a ferramenta `profile_baseline` sobre `entrada/`, mapeando os domínios técnicos presentes, definindo a matriz de checklists ativos e inaplicáveis (com justificativa auditável), recomendando/omitindo skills e sugerindo novas skills especializadas (ex: `analisar-lgpd`, `analisar-finops`). **A IA DEVE APRESENTAR O PLANO DE TRIAGEM AO USUÁRIO E PAUSAR A EXECUÇÃO AGUARDANDO A CONFIRMAÇÃO DO USUÁRIO ANTES DE CONTINUAR.**
4. Congelar baseline: inventário, versão, data, origem, hash (SHA-256 de textos e imagens em `entrada/`) e relação entre documentos. Imagens avulsas ou extraídas devem seguir a nomenclatura padronizada `fig{NN}_{doc}_{secao/pag}_{descricao_curta}.png` e ser inventariadas.
5. Criar mapa documental e matriz de rastreabilidade de objetivos, requisitos e evidências.
6. Executar triagem editorial, estrutural, técnica e normativa conforme os checklists mantidos ativos.
7. Registrar evidências e fichas 360° unificadas organizadas pela sequência natural de leitura das seções dos documentos de origem.
8. Emitir o **Relatório Consolidado Exaustivo HTML (`index.html`)** e a base estruturada `dados_analise.json` em `analise/<timestamp>/relatorios/`.
9. Finalizar o processamento: mover os arquivos de baseline analisados da pasta `entrada/` para `analise/<timestamp>/entrada/` e atualizar a Central Master (`analise/index.html` e `analise/manifest.json`).
10. Receber resposta do proprietário sem alterar o registro original; reauditar somente a nova baseline.

## 7. Princípios

Independência, evidência antes de conclusão, proporcionalidade, atomicidade, reprodutibilidade, neutralidade de fornecedor, separação entre fato e inferência, minimização de dados, linguagem precisa em **Português do Brasil (PT-BR)** e rastreabilidade bidirecional são obrigatórios. É estritamente proibido o uso de ortografia ou vocabulário de Português de Portugal (ex: "equipa", "ficheiro", "facto").


## 8. Critérios

Avaliar somente os critérios pertinentes: clareza; consistência interna e entre documentos; integridade estrutural e de sequenciamento numérico; consistência de referências cruzadas e índices; completude frente ao objetivo declarado; testabilidade; rastreabilidade; viabilidade técnica e operacional; segurança; resiliência; interoperabilidade; observabilidade; manutenibilidade; escalabilidade; governança; conformidade normativa; qualidade editorial e acessibilidade. A ausência de um critério aplicável é uma lacuna de avaliação, não prova de falha do sistema.

## 9. Categorias

Editorial & Estrutura Documental (inclui sequência numérica e referências cruzadas), requisito, arquitetura, integração, operação, segurança, dados, datacenter, carrier, OSS, BSS, cloud, contrato, norma/referência, diagrama/imagem, tabela e governança. Um achado pode ter uma categoria primária e etiquetas secundárias; não deve duplicar o mesmo problema em categorias diferentes.

## 10. Grau de evidência

**E0 — não verificado:** alegação sem fonte, não pode gerar conclusão. **E1 — indicação:** evidência parcial ou contexto incompleto. **E2 — corroborado:** trecho recuperável ou imagem legível conferida em fonte baseline. **E3 — confirmed:** corroborado por fontes independentes, teste/reprodução ou confronto direto entre diagrama e texto baseline. Achados críticos exigem E2; alegações de conformidade ou descumprimento normativo exigem E3 ou devem ser expressas como necessidade de validação.

## 11. Criticidade

Criticidade mede consequência potencial caso o achado seja real e não tratado: **Crítica** (impede objetivo, segurança, legalidade ou aceite); **Alta** (ameaça relevante a serviço, contratação ou operação); **Média** (causa ambiguidade, retrabalho ou risco controlável); **Baixa** (impacto localizado editorial/documental/estrutural); **Informativa** (registro sem não conformidade). Não usar “melhoria” como criticidade.

## 12. Prioridade

Prioridade é decisão de tratamento: P0 antes de emissão/publicação; P1 antes de contratação/implantação; P2 no próximo ciclo; P3 oportunidade. É definida por impacto, urgência, dependência e janela de mudança, não pela opinião do revisor. “Não definida” é aceitável enquanto faltarem dados.

## 13. Tipos de achados

Erro (informação demonstravelmente incorreta); lacuna (ausência verificável); inconsistência/conflito; ambiguidade; não verificabilidade; risco; erro estrutural / quebra de sequência numérica; errata / grafia; hipótese não declarada; boa prática observada; melhoria; recomendação. Erro, lacuna, hipótese, boa prática, melhoria e recomendação nunca são sinônimos e devem aparecer em campos distintos.

## 14. Regras de análise

- Nunca inventar requisito, volumetria, SLA, cronograma, arquitetura ou cláusula.
- Não afirmar oficialidade, obrigatoriedade ou conformidade sem autoridade e evidência.
- Citar a fonte exata: documento, versão, página/seção, tabela/figura, imagem padronizada e trecho ou descrição verificável.
- Separar fato observado, interpretação, impacto potencial e ação sugerida.
- Não converter recomendação em requisito; usar condicionais em redações alternativas.
- Não usar quantitativos de cobertura, páginas, requisitos ou qualidade sem método e denominador registrados.
- Não inferir obrigações legais/contratuais: encaminhar para validação competente.

## 15. Regras para IA

IA pode extrair, comparar, classificar preliminarmente, inspecionar multimodalmente diagramas e imagens legíveis (OCR, rótulos e topologias) e redigir rascunhos. Toda saída é assistida, não conclusiva, até validação humana. Ao analisar imagens, a IA deve cruzar obrigatoriamente os rótulos e fluxos visuais com a seção textual correspondente, apontando divergências e omissões sem supor conexões não desenhadas nem descritas. Toda ferramenta deve preservar fonte, versão, prompt/configuração, data, limitações e revisão humana. É proibido atribuir a IA autoridade normativa, inventar citações, completar lacunas com padrões de mercado ou enviar conteúdo confidencial a serviço não autorizado.

## 16. Regras para revisores humanos

Validar cada localização e citação, verificar escopo, desafiar inferências, avaliar conflito de interesse e aprovar a classificação. O revisor deve rejeitar achados agregados, linguagem absoluta sem evidência, recomendações travestidas de obrigação e qualquer texto que aparente ser documento oficial.

## 17. Regras para utilização de normas

Manter catálogo com entidade, título, edição, status, escopo, licença e localização. Uma norma só é “aplicável” quando contrato, regulação, política ou escopo a vincular. Caso seja referência voluntária, rotular como boa prática. Não declarar atendimento/não atendimento por memória; registrar cláusula aplicável e versão.

## 18. Regras para utilização de referências

Priorizar fontes primárias, vigentes e rastreáveis. Referência técnica explica um raciocínio; não substitui evidência do documento auditado. Links instáveis devem ser acompanhados de título, edição e data de consulta. Referências de fabricante não provam neutralidade ou obrigatoriedade.

## 19. Estrutura obrigatória dos achados (Ficha 360° Unificada)

Cada achado é registrado como uma unidade auditável atômica e autossuficiente (Ficha 360°), contendo a contextualização completa da não conformidade e a sua proposta de resolução. É vedada a fragmentação desnecessária do mesmo achado entre diferentes documentos.

Campos obrigatórios de cada Ficha 360°:
- `ID`: Identificador único e estável (ex: `ACH-001`, `EDIT-001`, `ESTR-001`).
- `Título`: Síntese clara do fato observado (técnico ou estrutural).
- `Documento de Origem`: Nome exato do arquivo analisado em `entrada/` (ex: `RFP_OSS_BSS.docx`).
- `Localização Exata`: Seção, Item, Subitem, Página, Tabela ou Figura recuperável na baseline.
- `Categoria`: Conforme taxonomia do FCA-ENG-001 (Contratos, Arquitetura, Cibersegurança, Editorial & Estrutura Documental, etc.).
- `Tipo de Achado`: Erro, Lacuna, Inconsistência, Ambiguidade, Risco, Errata/Grafia, Quebra de Sequência Numérica.
- `Grau de Evidência`: E0 (Não verificado), E1 (Indicação), E2 (Corroborado), E3 (Confronto Direto) + citação do trecho legível.
- `Fato Observado`: Descrição neutra do fato sem invenção de dados ou quantitativos supostos.
- `Impacto Potencial`: Consequência técnica, operacional, financeira, legal ou de clareza documental caso o achado não seja tratado.
- `Criticidade`: Crítica, Alta, Média, Baixa ou Informativa.
- `Prioridade`: P0 (Antes da emissão), P1 (Antes da contratação), P2 (Próximo ciclo), P3 (Oportunidade).
- `Tipo de Solução`:
  - **Ação Direta / Simples (Substituição De -> Para):** Aplicável a erratas, ortografia, pulos de numeração ou ajustes redacionais/estruturais pontuais. Exibe o *Texto Atual (Baseline)* vs *Texto Sugerido (Minuta Não Oficial)*.
  - **Plano de Ação Estruturado:** Aplicável a lacunas, contradições e riscos de arquitetura/contrato. Exibe os passos ordenados da ação recomendada, integrando pergunta formal de esclarecimento (`Q-00X`), minuta condicional (`PR-00X`) e mitigações técnicas.
- `Proprietário Sugerido`: Papel competente para deliberar (ex: Comissão de Licitação, Arquitetura de TI, Jurídico, Controle Editorial).

Campos ausentes devem ser preenchidos com "não disponível", nunca com informações supostas.

## 20. Estrutura dos relatórios e Apresentação Dinâmica em HTML

A análise consolida todos os dados em `analise/<timestamp>/relatorios/dados_analise.json` e compila o **Relatório Consolidado Exaustivo HTML (`index.html`)**. O compilador HTML renderiza uma Central Executiva de alto impacto visual (com cabeçalho Hero, KPI Cards, barra fixa superior, sidebar retrátil **colapsada por padrão**, busca em tempo real, filtros por categoria, criticidade, tipo e documento, e atalhos de impressão/PDF), organizada na seguinte hierarquia executiva de 8 seções:
1. **Seção 1: Resumo Executivo & Matriz de Skills** (Parecer técnico justificado, KPIs globais e matriz de skills ativas);
2. **Seção 2: Matriz Master SSOT de Achados** (Tabela consolidada de 100% dos achados com IDs clicáveis `<a href="#card-ID">`);
3. **Seção 3: Caderno de Fichas 360° Detalhadas** (Detalhamento granular em cards com Fato Observado, Impacto, Evidência E2+ e Caixas De-Para copiáveis, com filtros avançados por Categoria, Criticidade, Tipo, Documento e Busca);
4. **Seção 4: Caderno de Erratas (De → Para)** (Tabela dedicada a substituições diretas redacionais e estruturais com IDs de achados linkados e botão de cópia);
5. **Seção 5: Planos de Ação & Perguntas Formais (Q-00X / ACT-00X)** (Matriz de governança operacional e ofícios formais com IDs de achados linkados);
6. **Seção 6: Mapeamento de Lacunas Estratégicas & Matriz de Riscos** (Probabilidade, impacto, mitigações técnicas e IDs de achados de origem linkados);
7. **Seção 7: Status de Conformidade por Checklist de Domínio** (Percentual por checklist e justificativas de inaplicabilidade);
8. **Seção 8: Rastreabilidade de Baseline & Hashes SHA-256** (Capítulo final isolado de metadados técnicos, inventário de arquivos auditados, tamanhos, hashes SHA-256 e memória de cálculo do IQD).

## 21. Estrutura dos documentos

Todo artefato possui identificador, versão, status, proprietário, data, classificação, objetivo, fontes, regras de preenchimento e histórico. O status permitido é Rascunho, Em revisão, Emitido, Substituído ou Arquivado.

## 22. Templates

Os modelos oficiais ficam em `framework/templates/`. Alterações exigem versão, justificativa, revisão por pares e compatibilidade com rastreabilidade. Modelo não preenchido não é evidência de que um controle foi executado.

## 23. Checklists

Os checklists separados em `framework/checklists/` definem perguntas de verificação e evidência esperada. Marcação “não aplicável” requer justificativa; “não verificado” não pode ser contabilizado como conforme.

## 24. Critérios de aprovação

Resultados possíveis: **Apto para decisão**, **Apto com ressalvas**, **Não apto para decisão** ou **Sem conclusão**. Não existem limiares numéricos universais: o plano de análise define critérios de aceite e autoridade antes da execução. Qualquer achado crítico corroborado requer decisão explícita do proprietário antes da emissão/publicação do documento auditado.

## 25. Métricas

Medir: itens inventariados, itens avaliados, cobertura verificável, achados por tipo/categoria/criticidade, taxa de localização verificável, retrabalho, tempo de ciclo e itens reabertos. Fórmulas, população, exclusões e data de corte são obrigatórias.

## 26. Indicadores

Indicadores mostram tendência, não veredito isolado: cobertura verificável; densidade de achados por unidade analisável; % de achados com E2+; tempo de resposta; % de ações aceitas/rejeitadas; reincidência; e aderência ao template. Comparar somente populações e métodos equivalentes.

## 27. Índice de qualidade documental

O IQD é opcional e local: `IQD = 100 × (itens conformes verificáveis / itens aplicáveis verificados)`. Publicar cobertura, pesos aprovados, itens não verificados e limitações. O IQD não pode compensar achado crítico nem ser calculado sobre requisito inventariado de modo incompleto.

## 28. Índice de maturidade documental

Avaliar cinco dimensões (governança, estrutura, rastreabilidade, verificabilidade e controle de mudança) em níveis 0–4 com rubrica aprovada. O índice expressa capacidade do processo documental, não qualidade da solução técnica.

## 29. Fluxo de aprovação

Revisor emite rascunho → revisor por pares valida → gestor libera emissão → proprietário responde → gestor registra encerramento/reabertura. Aprovação de conteúdo fonte, recomendação, plano e publicação são decisões separadas e registradas.

## 30. Controle de versões

Preservar baseline imutável, hash quando possível, relações de substituição e changelog. Nova versão gera nova rodada de análise ou escopo de regressão. Nunca sobrescrever relatório emitido.

## 31. Governança

Comitê de qualidade mantém este procedimento, catálogo de normas, taxonomia, templates e métricas. Deve revisar conflitos de interesse, qualidade amostral, acesso à informação, retenção e exceções. Exceções têm prazo, aprovador e risco residual.

## 32. Boas práticas

Planejar antes de revisar; realizar leitura cruzada; usar identificadores estáveis; manter um registro por problema; distinguir ausência de requisito de requisito mal formulado; conservar figuras de origem; e comunicar incerteza explicitamente.

## 33. Lições aprendidas

Registrar apenas após encerramento, sem reescrever o histórico. Cada lição referencia evidência, contexto, decisão, benefício esperado, responsável e revisão futura.

## 35. Aviso de Responsabilidade e Colaboração

Este conteúdo foi elaborado para apoiar a análise e a tomada de decisão, mas não representa uma verdade absoluta. Diferentes contextos, interpretações, restrições e necessidades podem levar a conclusões distintas, todas potencialmente válidas.

A leitura deste material pressupõe análise crítica, entendimento e concordância com seu propósito. Nenhum documento substitui o conhecimento técnico, a experiência ou o julgamento dos envolvidos.

A qualidade deste conteúdo é uma responsabilidade compartilhada. Identificar inconsistências, sugerir melhorias, corrigir informações ou complementar análises faz parte de um processo colaborativo e contínuo. A responsabilidade pelos resultados não deve ser atribuída a uma única pessoa, mas a todos que participam da sua leitura, revisão e evolução.

## Autoauditoria do framework

Esta versão separa criticidade de prioridade e de tipo; separa análise de consultoria; proíbe oficialidade e invenção; condiciona métricas a denominadores; e exige evidência e baseline. A validação de aplicabilidade normativa, pesos de índices e critérios específicos permanece deliberadamente dependente do contexto, para não criar obrigações fictícias.
