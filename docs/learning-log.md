# Learning Log — Pizza Radar PT

Este ficheiro destina-se a registar aprendizagens, descobertas técnicas, comportamentos observados nos fornecedores de dados e lições aprendidas ao longo da evolução do projeto.

---

## Modelo de Registo de Aprendizagem

Quando encontrares um desafio técnico, uma particularidade de um fornecedor ou uma melhoria de processo, adiciona uma nova entrada no topo da secção de registos com a seguinte estrutura:

```markdown
### [YYYY-MM-DD] — Título curto da aprendizagem

- **Contexto / Ticket:** (ex.: Issue #1, Spike de dados da Domino's, etc.)
- **Desafio / Descoberta:** O que aconteceu ou o que foi descoberto?
- **Impacto:** Como afeta a arquitetura, o fluxo de dados ou a experiência do utilizador?
- **Decisão / Solução:** O que fizemos ou decidimos fazer?
- **Ação Futura:** Há passos subsequentes a tomar ou monitorizar?
```

---

## Registos

### [2026-09-28] — Fundação Documental e Alinhamento de Âmbito

- **Contexto / Ticket:** Issue #1
- **Desafio / Descoberta:** Necessidade de fixar barreiras claras antes de qualquer escrita de código, garantindo que o foco inicial se mantenha estritamente em Lisboa e em 4 vendedores públicos (Domino's, Pizza Hut, Telepizza, Papa John's).
- **Impacto:** Evita escolhas precipitadas de frameworks, dependências não justificadas e desvios de âmbito antes de validar as fontes de dados.
- **Decisão / Solução:** Criada a estrutura de documentação (`project-charter.md`, `learning-log.md`, `docs/decisions/`, `AGENTS.md`) e definido o fluxo de trabalho obrigatório por branch e pull request.
- **Ação Futura:** Proceder à investigação técnica de viabilidade de dados em issues dedicadas e documentar eventuais particularidades de cada fornecedor.
