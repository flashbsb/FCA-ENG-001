# Plano de Triagem Adaptativa e Escopo da Revisão Técnica

**Timestamp da Revisão Técnica:** `{{TIMESTAMP}}`  
**Data/Hora da Triagem:** `{{DATE_TIME}}`  
**Status da Triagem:** Perfilamento Concluído — Aguardando Confirmação / Em Execução  

---

## 🔍 1. Perfil da Baseline de Entrada (`entrada/`)

| Arquivo Detectado | Tipo / Extensão | Tamanho | Domínios Identificados |
|---|---|---|---|
{{FILES_TABLE}}

---

## 🛠️ 2. Mapeamento Adaptativo de Checklists (21 Checklists)

### ✅ Checklists ATIVOS (Obrigatórios & Recomendados)
| Checklist | Domínio Relacionado | Motivo da Ativação |
|---|---|---|
{{ACTIVE_CHECKLISTS_TABLE}}

### ⏸️ Checklists DESATIVADOS (Inaplicáveis com Justificativa)
| Checklist | Motivo da Inaplicabilidade | Justificativa Auditável |
|---|---|---|
{{INACTIVE_CHECKLISTS_TABLE}}

---

## 🤖 3. Recomendações de Skills e Agentes de IA

### Skills Ativas para esta Revisão Técnica
- `analisar-documento`: **Ativa** (processamento textual e de tabelas).
- `analisar-diagramas`: **{{SKILL_DIAGRAMAS_STATUS}}** ({{SKILL_DIAGRAMAS_JUSTIFICATIVA}}).

### Sugestão de Criação de Novas Skills Especializadas
{{NEW_SKILLS_SUGGESTIONS}}

---

## 📝 4. Observações de Governança
Nenhum checklist foi desativado sem justificativa baseada em evidência de ausência no material de entrada. Qualquer checklist ambíguo permanece **ATIVO** por padrão conservador.
