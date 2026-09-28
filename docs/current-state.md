# Estado Atual do Projeto — Pizza Radar PT

Este documento reflete a situação factual, as decisões vigentes e as frentes de trabalho ativas no repositório **Pizza Radar PT**. Deve ser mantido atualizado à medida que tickets e Pull Requests são concluídos.

---

## 1. Resumo Executivo

- **Fase Atual:** Fase 1 — Fundação, Arquitetura e Contrato Canónico (MVP Lisboa).
- **Cobertura Alvo do MVP:** Concelho de Lisboa (Domino's Pizza, Pizza Hut, Telepizza, Papa John's).
- **Progresso Global:**
  - Fundação documental e regras de equipa consolidadas (`main`).
  - Investigação empírica de viabilidade concluída para os 4 fornecedores (`main`).
  - Equipa multiagente permanente configurada com 6 papéis em `.agents/agents/` (`main`).
  - Contrato canónico de dados (`UnifiedPromo`), interface agnóstica (`PromoAdapterInterface`), cálculos monetários em cêntimos inteiros e 31 testes unitários determinísticos integrados em `main` ([Issue #7](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/7)).
  - Arquitetura técnica global de execução, alojamento e persistência free-tier (Turso libSQL, Cloudflare Pages, GitHub Actions) formalizada, aprovada e integrada em `main` via squash merge da [PR #15](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/15) ([Issue #14](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/14)).
  - Organização da documentação em base de conhecimento navegável concluída e integrada em `main` via squash merge da [PR #17](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/17) ([Issue #16](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/16)).
  - **PapaJohnsAdapter** em desenvolvimento na branch `feat/8-papa-johns-adapter` ([Issue #8](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/8)): 67 novos testes unitários determinísticos (98 no total), separação de camadas fetch/parse/adapt, fixtures sanitizadas, zero IA em runtime.


---

## 2. Decisões Técnicas Vigentes

| Decisão / ADR | Estado | Resumo Técnico | Documento |
| :--- | :--- | :--- | :--- |
| **ADR-001: Contrato Canónico de Dados, Interface de Adaptadores e Core** | **Aceite** *(Integrado em `main`)* | Representação monetária estrita em cêntimos inteiros (`price_cents`, `original_price_cents`); escopo geográfico explícito (`StoreScope`) sem assumir disponibilidade universal; decomposição de componentes de oferta (`OfferComponent`) sem inventar dados; carimbo temporal `observed_at` timezone-aware; interface agnóstica `PromoAdapterInterface`; 100% Python stdlib determinístico (sem dependências externas). | [docs/decisions/0001-data-contract-and-core-architecture.md](decisions/0001-data-contract-and-core-architecture.md) |
| **ADR-002: Execução, Hosting Estático e Persistência Gratuita** | **Aceite e Integrada** *(Integrado em `main`)* | Base de dados Turso libSQL (5 GB storage no free tier sem suspensão por inatividade); frontend estático alojado no Cloudflare Pages (CDN global gratuita); coletores Python agendados via GitHub Actions (2x/dia, consumo estimado ~20-60 min/mês de 2.000 min); publicação híbrida em `promotions.json` em CDN via GitHub Secrets sem poluir a `main`; tolerância a falhas sem incremento indevido de ausências; orçamento total de 0,00€/mês; zero IA em runtime. | [docs/decisions/0002-execution-hosting-and-free-tier-persistence.md](decisions/0002-execution-hosting-and-free-tier-persistence.md)<br/>[docs/architecture-execution-hosting-persistence.md](architecture-execution-hosting-persistence.md) |

---

## 3. Tickets e Pull Requests Ativos

A tabela reflete o estado no quadro [GitHub Project `Pizza-radar-project`](https://github.com/users/FranciscoSousaSilveira/projects/1):

| Referência | Título | Tipo | Estado no Project | Responsável / Agente | Notas |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **[Issue #8](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/8)** / **PR a abrir** | [FEAT] Implementar PapaJohnsAdapter para promoções em Lisboa | FEAT | `In Progress` | `implementer` | Branch `feat/8-papa-johns-adapter`. Implementação completa com 67 testes, aguarda auditoria e abertura de PR. |
| **[PR #17](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/17)** / **[#16](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/16)** | [CHORE] Organizar documentação como knowledge base navegável | CHORE | `Done` *(Fechado)* | `orchestrator` / `reviewer` | Concluído e integrado em `main` via squash merge. |
| **[PR #15](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/15)** / **[#14](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/14)** | [ARCH] Arquitetura de execução, hosting e persistência gratuita | ARCH | `Done` *(Fechado)* | `orchestrator` / `reviewer` | Concluído e integrado em `main` via squash merge. |
| **[#9](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/9)** | [FEAT] Implementar DominosAdapter para promoções em Lisboa | FEAT | `Backlog` | Por alocar | Segundo adaptador de recolha. |
| **[#10](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/10)** | [FEAT] Implementar TelepizzaAdapter para promoções em Lisboa | FEAT | `Backlog` | Por alocar | Terceiro adaptador de recolha. |
| **[#11](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/11)** | [FEAT] Implementar PizzaHutAdapter para promoções em Lisboa | FEAT | `Backlog` | Por alocar | Quarto adaptador; arquitetura de base de dados já definida (#14). |
| **[#12](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/12)** | [FEAT] Motor de Normalização, Deduplicação e Pipeline de Agregação | FEAT | `Backlog` | Por alocar | Pipeline de persistência e deploy automatizado (estratégia definida em #14). |

---

## 4. Bloqueios e Dependências

- **Bloqueios Atuais:** Não existem bloqueios ativos no projeto.
- **Dependências Resolvidas:** A formalização e integração da arquitetura de persistência e hosting ([Issue #14](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/14) / [PR #15](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/15)) desbloqueou os requisitos de persistência para os adaptadores subsequentes e para o pipeline de dados ([#11](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/11) e [#12](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/12)).
- **Prontidão de Implementação:** Todos os contratos canónicos (ADR-001) e decisões de infraestrutura (ADR-002) estão aprovados em `main`.

---

## 5. Próximo Marco (Next Milestone)

- **Marco Imediato:** Conclusão da auditoria independente e abertura da **Pull Request** para o **[Issue #8](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/8)** (`PapaJohnsAdapter`), colocando-o em `Review` para validação do utilizador.
- **Marco Subsequente:** Após aprovação e squash merge do #8, iniciar o **[Issue #9](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/9)** (`DominosAdapter`).
