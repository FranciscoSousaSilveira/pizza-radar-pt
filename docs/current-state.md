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
  - **PapaJohnsAdapter** implementado na branch `feat/8-papa-johns-adapter` e submetido para revisão na [PR #19](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/19) ([Issue #8](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/8)): parsing de preços via Decimal nativo, desduplicação e agregação entre lojas, exclusão de itens ocultos, separação de camadas fetch/parse/adapt, 63 testes unitários determinísticos, zero IA em runtime.

---

## 2. Decisões Técnicas Vigentes

| Decisão / ADR | Estado | Resumo Técnico | Documento |
| :--- | :--- | :--- | :--- |
| **ADR-001: Contrato Canónico de Dados, Interface de Adaptadores e Core** | **Aceite** *(Integrado em `main`)* | Representação monetária estrita em cêntimos inteiros (`price_cents`, `original_price_cents`); escopo geográfico explícito (`StoreScope`) sem assumir disponibilidade universal; decomposição de componentes de oferta (`OfferComponent`) sem inventar dados; carimbo temporal `observed_at` timezone-aware; interface agnóstica `PromoAdapterInterface`; 100% Python stdlib determinístico (sem dependências externas). | [docs/decisions/0001-data-contract-and-core-architecture.md](decisions/0001-data-contract-and-core-architecture.md) |
| **ADR-002: Execução, Hosting Estático e Persistência Gratuita** | **Aceite e Integrada** *(Integrado em `main`)* | Base de dados Turso libSQL (5 GB storage no free tier sem suspensão por inatividade); frontend estático alojado no Cloudflare Pages (CDN global gratuita); coletores Python agendados via GitHub Actions (2x/dia, consumo estimado ~20-60 min/mês de 2.000 min); publicação híbrida em `promotions.json` em CDN via GitHub Secrets sem poluir a `main`; tolerância a falhas sem incremento indevido de ausências; orçamento total de 0,00€/mês; zero IA em runtime. | [docs/decisions/0002-execution-hosting-and-free-tier-persistence.md](decisions/0002-execution-hosting-and-free-tier-persistence.md)<br/>[docs/architecture-execution-hosting-persistence.md](architecture-execution-hosting-persistence.md) |

---

## 3. Tickets e Pull Requests Ativos

A tabela reflete o estado no quadro [GitHub Project `Pizza-radar-project`](https://github.com/users/FranciscoSousaSilveira/projects/1):

| Referência | Título Real do Ticket | Tipo | Estado no Project | Responsável / Agente | Notas |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **[PR #19](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/19)** / **[#8](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/8)** | [FEAT] Implementar adaptador para Papa John's Portugal (Lisboa) | FEAT | `Review` | `implementer` / `reviewer` | Implementado com precisão monetária Decimal, desduplicação entre lojas, exclusão de ofertas ocultas e 63 testes unitários. Aguarda revisão do utilizador. |
| **[PR #17](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/17)** / **[#16](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/16)** | [CHORE] Organizar documentação como knowledge base navegável | CHORE | `Done` *(Fechado)* | `orchestrator` / `reviewer` | Concluído e integrado em `main` via squash merge. |
| **[PR #15](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/15)** / **[#14](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/14)** | [ARCH] Arquitetura de execução, alojamento e persistência free-tier | ARCH | `Done` *(Fechado)* | `orchestrator` / `reviewer` | Concluído e integrado em `main` via squash merge. |
| **[#9](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/9)** | [FEAT] Implementar adaptadores para Telepizza, Domino's e Pizza Hut (Lisboa) | FEAT | `Backlog` | Por alocar | Adaptadores subsequentes para as restantes marcas em Lisboa. |
| **[#10](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/10)** | [FEAT] Motor determinístico de normalização, cálculo de descontos e ranking de ofertas | FEAT | `Backlog` | Por alocar | Regras determinísticas de ordenação e comparabilidade de preços. |
| **[#11](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/11)** | [FEAT] Interface web responsiva para visualização e filtragem de promoções em Lisboa | FEAT | `Backlog` | Por alocar | Frontend para apresentação e pesquisa de ofertas. |
| **[#12](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/12)** | [CHORE] Pipeline de automação para recolha periódica e persistência estática | CHORE | `Backlog` | Por alocar | Workflows agendados de CI/CD para ingestão e deploy no Cloudflare Pages. |
| **[#18](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/18)** | [SPIKE] Investigar códigos promocionais em canais sociais e parceiros oficiais | SPIKE | `Backlog` | Por alocar | Estudo de viabilidade sem bloqueio do roadmap do MVP. |

---

## 4. Bloqueios e Dependências

- **Bloqueios Atuais:** Não existem bloqueios ativos no projeto.
- **Dependências Resolvidas:** Contratos canónicos (ADR-001) e decisões de infraestrutura (ADR-002) integrados em `main`.
- **Estado de Execução:** [PR #19](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/19) aberta e em `Review` para validação final do utilizador.

---

## 5. Próximo Marco (Next Milestone)

- **Marco Imediato:** Revisão e aprovação da **[Pull Request #19](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/19)** ([Issue #8](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/8)), consolidando o `PapaJohnsAdapter` em `main`.
- **Marco Subsequente:** Após merge do #8, avançar para o **[Issue #9](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/9)** (`[FEAT] Implementar adaptadores para Telepizza, Domino's e Pizza Hut (Lisboa)`).
