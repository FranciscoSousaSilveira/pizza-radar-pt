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

## Navegação

- [Índice Central da Base de Conhecimento](README.md)
- [Estado Atual do Projeto](current-state.md)

---

## Registos

### [2026-09-28] — Organização da Documentação como Base de Conhecimento Navegável

- **Contexto / Ticket:** Issue #16 ([CHORE] Organizar documentação como knowledge base navegável)
- **Desafio / Descoberta:** O crescimento de documentos no repositório (charter, viabilidade, contrato canónico, propostas de arquitetura e equipa permanente) aumentou a necessidade de uma navegação fluida entre artefactos, sem duplicar o estado do projeto nem introduzir ferramentas complexas ou dependências de pesquisa vetorial/RAG.
- **Impacto:** Estabelecido o `docs/README.md` como catálogo central com indicação de finalidade e momento de leitura de cada documento, o `docs/current-state.md` como registo factual conciso do estado vivo, e adicionados 6 trilhos de leitura por especialidade no `AGENTS.md`. Todos os links utilizam sintaxe relativa padrão em Markdown, permitindo navegação tanto no GitHub como em modo Vault no Obsidian.
- **Decisão / Solução:** Manter o `README.md` da raiz focado na proposta de valor pública, delegar o acompanhamento do estado operacional para `docs/current-state.md`, e interligar os documentos existentes através de hiperligações contextuais.
- **Ação Futura:** Manter o `docs/current-state.md` atualizado a cada transição ou fecho de ticket/PR.

### [2026-09-28] — Contrato Canónico de Dados, Precisão Financeira e Integridade de Ofertas (Core)

- **Contexto / Ticket:** Issue #7 ([FEAT] Arquitetura base, contrato de dados unificado e interface de adaptadores)
- **Desafio / Descoberta:** Harmonizar quatro estruturas de dados distintas observadas no spike (#3) exigiu resolver quatro desafios materiais de produto: (1) evitar erros de arredondamento em float; (2) modelar aplicabilidade geográfica por loja sem presunções universais falsas; (3) evitar estimativas ou valores inventados quando a fonte omite a contagem ou tamanho das pizzas; (4) garantir carimbos temporais timezone-aware distinguindo a validade anunciada pela marca da data de recolha pelo coletor para suporte a expiração determinística.
- **Impacto:** O modelo `UnifiedPromo` passa a operar com cêntimos inteiros (`price_cents`, `original_price_cents`), define `store_scope` com identificadores de lojas, decompõe componentes de oferta (`OfferComponent`, `pizza_count`, `pizza_size`) marcando explicitamente ofertas não comparáveis para ranking (`is_comparable_for_unit_price`), e torna obrigatório `observed_at` timezone-aware.
- **Decisão / Solução:** Implementado o core determinístico em Python 3.12 na biblioteca padrão (zero dependências externas), formalizado em ADR-001 revisto e protegido por 31 testes unitários determinísticos executados em ~0.001s.
- **Ação Futura:** Avançar para a definição da arquitetura de hosting e persistência (#14) e implementação do `PapaJohnsAdapter` (#8).

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
