---
name: analisar-diagramas
description: Skill especializada para Revisão Técnica de artefatos visuais (PNG, JPG, SVG, DrawIO). Realiza OCR de rótulos, análise de topologia, verificação de fluxos e confronto direto entre o que está ilustrado no diagrama e o que está descrito no texto do mesmo lote. Ativa automaticamente quando o lote contém imagens.
---

# Skill: Análise de Diagramas e Artefatos Visuais

Esta skill executa a inspeção multimodal de diagramas de arquitetura, fluxogramas, topologias de rede e esquemas técnicos presentes no lote.

---

## Contexto de Ativação

Ative quando o lote contiver arquivos `.png`, `.jpg`, `.jpeg`, `.svg`, `.drawio`, `.bmp` ou quando `inventario_visual.json` apontar imagens embutidas/renderizadas de `.pdf` ou `.docx`.

---

## Nomenclatura Recomendada de Imagens

Para facilitar rastreabilidade, imagens devem seguir o padrão:
```
fig{NN}_{documento}_{secao_ou_pagina}_{descricao_curta}.png
```
*Exemplo:* `fig01_rfp_pag09_topologia_geral.png`

É uma convenção recomendada para novas imagens-fonte. A ausência desse padrão, por si só, não é achado: imagens embutidas em PDF/DOCX não têm necessariamente nome próprio, e os IDs gerados pelo inventário são identificadores técnicos, não nomes de origem.

---

## Workflow de Análise Multimodal

### 0. Recepção e Cobertura dos Ativos

1. Depois de `run_full_audit`, chame `get_visual_assets(timestamp, offset, limit=6)` e inspecione visualmente cada bloco de imagem retornado; continue paginando até `has_more=false`.
2. Considere o ativo como não analisado quando a imagem não foi efetivamente exibida ou está ilegível. Metadados/OCR ajudam na leitura, mas não substituem a inspeção visual.
3. Classifique cada ativo (diagrama, tabela/figura, página de contexto, elemento decorativo ou ilegível). Elemento decorativo não exige achado; renderizações e imagens embutidas da mesma página devem ser correlacionadas para evitar duplicidade.

### 1. OCR e Extração de Rótulos

1. Extraia todos os rótulos de texto visíveis: nomes de componentes, interfaces, portas, protocolos, VLANs, IPs, legendas.
2. Identifique direções de setas e fluxos de dados.
3. Identifique zonas, camadas ou agrupamentos representados.

### 2. Análise Topológica

- Identifique o esquema de redundância ilustrado (single, dual-homing, anel, malha).
- Identifique pontos únicos de falha (SPOF) visualmente presentes mas não declarados no texto.
- Verifique se a escala/quantidade de equipamentos no diagrama bate com o texto.

### 3. Confronto Diagrama × Texto (E3 obrigatório)

Para cada diagrama, localize a seção correspondente no documento textual e compare:
- Componentes ilustrados vs componentes descritos (diferença = Inconsistência)
- Protocolos/interfaces no diagrama vs no texto (diferença = Inconsistência)
- Quantidades de links, nós ou zonas (diferença = Inconsistência)
- Fluxos de dados ilustrados vs fluxos descritos (diferença = Inconsistência)

Somente uma inconsistência confirmada por comparação com trecho textual literal recebe **Grau de Evidência E3 (Confronto Direto)**. Observações sem confronto textual comprovado não devem ser rotuladas como E3.

### 4. Qualidade e Legibilidade

- O diagrama é legível em tamanho normal de documento?
- Há legenda explicando os símbolos utilizados?
- Os rótulos estão em PT-BR (ou idioma consistente com o documento)?

---

## Achados Típicos de Diagramas

| Tipo | Exemplo |
|------|---------|
| Inconsistência E3 | Diagrama mostra 2 uplinks; texto descreve 4 uplinks com bonding |
| Inconsistência E3 | Diagrama rotula interface como "10GbE"; texto especifica "40GbE" |
| Lacuna | Diagrama referenciado na seção 3.2 está ausente do lote |
| Editorial | Diagrama ilegível em resolução de documento impresso |
| Risco | SPOF visível no diagrama sem declaração de risco aceito no texto |

---

## Saída Esperada

Ao concluir cada grupo de ativos, chame `record_visual_analysis(timestamp, reviewed_asset_ids, findings)`. Informe somente IDs efetivamente inspecionados; envie `findings=[]` quando não houver problema. Para cada achado, use `asset_id`, `title`, `fato`, `observacao_visual`, `tipo`, `criticidade`, `prioridade`, `evidencia`, `impacto` e `solucao`. Para E3, inclua também `trecho_textual_correlacionado` literal e `documento_textual_correlacionado` com o caminho exato da baseline. Não fabrique rótulos, topologias, redundância ou divergências.

Registre os achados em `dados_analise.json` com categoria `Diagrama/Imagem` para exibição nas Fichas 360° do `index.html` com:
- Inventário de imagens encontradas
- Achados de confronto diagrama × texto (grau E3 quando confirmado)
- Achados de qualidade e legibilidade
- Estado de cobertura visual: só declare concluída quando todos os ativos do inventário tiverem sido efetivamente revisados; caso contrário, registre a limitação como parcial.
