# Architecture Decision Records (ADRs)

Este diretório contém os registos de decisões de arquitetura e design técnico (**ADRs**) do projeto **Pizza Radar PT**.

## O que é uma ADR?

Uma Architecture Decision Record (ADR) é um documento curto que captura uma decisão técnica importante, o contexto em que foi tomada e as suas consequências.

## Quando criar uma ADR?

Cria uma ADR sempre que:
- For escolhida ou alterada a framework/linguagem principal da aplicação.
- For adotada uma estratégia de armazenamento ou base de dados.
- For desenhada a arquitetura de agregação de dados ou atualização periódica.
- For tomada qualquer decisão arquitetural que introduza compromissos (trade-offs) significativos a médio/longo prazo.

## Modelo de ADR (Template)

Para criar uma nova ADR, cria um ficheiro com a convenção `NNN-titulo-da-decisao.md` (ex.: `001-escolha-da-stack-web.md`) seguindo o modelo abaixo:

```markdown
# ADR-NNN: [Título da Decisão]

- **Data:** [YYYY-MM-DD]
- **Estado:** [Proposto | Aceite | Rejeitado | Substituído]
- **Decisores:** [Nomes ou papéis dos intervenientes]

## Contexto

Qual é o problema ou necessidade técnica que motivou esta decisão? Que restrições e opções alternativas foram consideradas?

## Decisão

Qual é a solução escolhida? Como será implementada?

## Consequências

### Positivas (Prós)
- ...

### Negativas / Compromissos (Contras / Trade-offs)
- ...

### Riscos e Mitigações
- ...
```

---

## Índice de Decisões

- [ADR-001: Contrato Canónico de Dados, Interface de Adaptadores e Arquitetura do Core](0001-data-contract-and-core-architecture.md) — *Aceite* (2026-09-28)
- [ADR-002: Arquitetura de Execução, Alojamento, Base de Dados Free-Tier e Publicação de Dados](0002-execution-hosting-and-free-tier-persistence.md) — *Aceite* (2026-09-28)
