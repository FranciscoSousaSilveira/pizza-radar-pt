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

### [2026-09-28] — Viabilidade de Fontes de Dados e Seleção do Primeiro Adaptador

- **Contexto / Ticket:** Issue #3 (SPIKE)
- **Desafio / Descoberta:** Investigada a viabilidade de recolha de promoções públicas dos 4 operadores em Lisboa. Constatou-se que nenhuma marca exige morada ou código postal para consulta pública de campanhas, existindo endpoints publicamente acessíveis sem autenticação utilizados pelo frontend oficial (na Papa John's, Domino's e Pizza Hut) e dados estruturados em SSR e JSON-LD (na Telepizza), todos sem garantia de estabilidade contratual.
- **Impacto:** Confirma-se a viabilidade de uma arquitetura determinística e testável, sem necessidade de browsers headless (Puppeteer/Playwright) nem chamadas a modelos de IA em tempo de execução, orientada a opções gratuitas (free tier) de alojamento e bases de dados.
- **Decisão / Solução:** Documentada a matriz e evidências de viabilidade em `docs/source-feasibility.md` e recomendada a Papa John's como primeiro adaptador a construir, devido à estrutura JSON tipada e ao menor atrito técnico observado.
- **Ação Futura:** Criar a especificação do contrato canónico de dados e desenhar a interface agnóstica de adaptadores no próximo ticket.

### [2026-09-28] — Fundação Documental e Alinhamento de Âmbito

- **Contexto / Ticket:** Issue #1
- **Desafio / Descoberta:** Necessidade de fixar barreiras claras antes de qualquer escrita de código, garantindo que o foco inicial se mantenha estritamente no concelho de Lisboa (excluindo outros concelhos da Área Metropolitana no MVP) e com atualização periódica regular (evitando a complexidade de tempo real), para 4 vendedores públicos (Domino's, Pizza Hut, Telepizza, Papa John's).
- **Impacto:** Evita escolhas precipitadas de frameworks, dependências não justificadas e desvios de âmbito antes de validar as fontes de dados.
- **Decisão / Solução:** Criada a estrutura de documentação (`project-charter.md`, `learning-log.md`, `docs/decisions/`, `AGENTS.md`) e definido o fluxo de trabalho obrigatório por branch e pull request.
- **Ação Futura:** Proceder à investigação técnica de viabilidade de dados em issues dedicadas e documentar eventuais particularidades de cada fornecedor.
