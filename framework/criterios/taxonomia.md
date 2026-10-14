# Taxonomia e escalas controladas

Aplicar as definições das seções 8–13 do FCA-ENG-001. Criticidade mede impacto; prioridade mede ordem de tratamento; confiança mede grau de evidência; tipo identifica a natureza. Não calcular um deles a partir do outro sem regra aprovada no plano de revisoria.

## Types de Achado (Natureza)

| Tipo de Achado | Definição Operacional | Exemplo |
|---|---|---|
| **Erro Técnico** | Informação demonstradamente incorreta ou fisicamente impossível | Porta 100G conectada em switch 10G |
| **Inconsistência / Contradição** | Dois trechos ou artefatos que se contrapõem diretamente | RMA de 8h vs reparo de HW em 45 dias |
| **Lacuna de Informação** | Informação necessária para dimensionamento/execução, mas omitida | Volumetria em EPS (Eventos/Seg) do SIEM |
| **Ambiguidade / Linguagem Subjetiva** | Texto que admite interpretações diversas sem critério objetivo | Uso de termos como "rápido", "preferencialmente" |
| **Falha de Estrutura / Referência** | Numeração quebrada, duplicidade ou citação inexistente | "Ver Seção 4.2" quando a seção correta é 4.3 |
| **Inconformidade Editorial** | Erro ortográfico, gramatical ou de pontuação | Erros de escrita e concordância verbal/nominal |
| **Risco Operacional / Contratual** | Cláusula ou exigência que gera assimetria ou insegurança | Rescisão imotivada em 30 dias sem amortização |
| **Recomendação de Melhoria** | Sugestão técnica não obrigatória | Indicação de boa prática ITIL ou TM Forum |

## Escala de Grau de Evidência

| Código | Descrição | Requisito de Uso |
|---|---|---|
| **E0** | Não verificado / Informação não acessada | Ausência de documento fonte |
| **E1** | Declarado na Baseline | Afirmação textual única no documento fonte |
| **E2** | Corroborado na Baseline | Confronto de dois ou mais trechos/tabelas da baseline |
| **E3** | Confirmado por Confronto Direto | Confronto textual direto com hash SHA-256 e imagem |

## Escala de Criticidade (Consequência Potencial)

| Nível | Impacto Operacional / Financeiro |
|---|---|
| **CRÍTICA** | Paralisação de serviço de missão crítica, indisponibilidade ou dano financeiro |
| **ALTA** | Inconsistência técnica relevante que compromete o dimensionamento ou a integração |
| **MÉDIA** | Falha estrutural, ambiguidade ou divergência de documentação sem parada imediata |
| **BAIXA** | Ajuste editorial, erro de grafia ou melhoria formal de documentação |

## Escala de Prioridade (Janela de Decisão)

| Código | Janela de Decisão |
|---|---|
| **P0 (Imediata)** | Exige retificação urgente antes da publicação do edital/minuta |
| **P1 (Alta)** | Exige esclarecimento no prazo de impugnação do edital |
| **P2 (Contratual)** | Ajuste a ser acordado na assinatura do contrato |
| **P3 (Operacional)** | Ajuste contínuo na fase de execução do projeto |

## Decisão Rápida

1. Há trecho ou artefato recuperável? Se não, E0/E1 e solicitar evidência.
2. Há requisito/objetivo declarado que torna a ausência relevante? Se não, registrar melhoria ou pergunta, não lacuna.
3. O texto é incorreto demonstravelmente? Usar erro. Se apenas admite interpretações, usar ambiguidade.
4. A ação sugerida muda compromisso, custo ou escopo? Marcar como recomendação/consultoria e exigir aprovação separada.
