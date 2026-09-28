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
  - Arquitetura de persistência e hosting a custo zero desenhada e documentada, aguardando revisão humana na [PR #15](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/15).
  - Organização da documentação em base de conhecimento navegável em execução ativa ([Issue #16](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/16)).

---

## 2. Decisões Técnicas Vigentes

| Decisão / ADR | Estado | Resumo Técnico | Documento |
| :--- | :--- | :--- | :--- |
| **ADR-001: Contrato Canónico de Dados, Interface de Adaptadores e Core** | **Aceite** *(Integrado em `main`)* | Representação monetária estrita em cêntimos inteiros (`price_cents`, `original_price_cents`); escopo geográfico explícito (`StoreScope`) sem assumir disponibilidade universal; decomposição de componentes de oferta (`OfferComponent`) sem inventar dados; carimbo temporal `observed_at` timezone-aware; interface agnóstica `PromoAdapterInterface`; 100% Python stdlib determinístico (sem dependências externas). | [docs/decisions/0001-data-contract-and-core-architecture.md](decisions/0001-data-contract-and-core-architecture.md) |
| **ADR-002: Execução, Hosting Estático e Persistência Gratuita** | **Proposto** *(Em revisão na [PR #15](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/15))* | Base de dados Turso libSQL (5 GB storage no free tier sem suspensão por inatividade); frontend estático alojado no Cloudflare Pages (CDN global gratuita); coletores Python agendados via GitHub Actions (2x/dia, consumo ~35 min/mês de 2.000 min); publicação híbrida em `promotions.json` em CDN para custo total de 0,00€/mês; zero IA em runtime. | [docs/decisions/README.md](decisions/README.md) / [PR #15](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/15) |

---

## 3. Tickets e Pull Requests Ativos

A tabela reflete o estado no quadro [GitHub Project `Pizza-radar-project`](https://github.com/users/FranciscoSousaSilveira/projects/1):

| Referência | Título | Tipo | Estado no Project | Responsável / Agente | Notas |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **[PR #15](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/15)** / **[#14](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/14)** | [ARCH] Arquitetura de execução, hosting e persistência gratuita | ARCH | `Review` | `orchestrator` / `reviewer` | Documentação concluída e validada por auditor independente. Aguarda revisão e squash merge pelo utilizador. |
| **[#16](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/16)** | [CHORE] Organizar documentação como knowledge base navegável | CHORE | `In Progress` | `implementer` | Em implementação na branch `chore/16-navigable-knowledge-base`. |
| **[#8](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/8)** | [FEAT] Implementar PapaJohnsAdapter para promoções em Lisboa | FEAT | `Backlog` | Por alocar | Primeiro adaptador a implementar após conclusão da arquitetura. |
| **[#9](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/9)** | [FEAT] Implementar DominosAdapter para promoções em Lisboa | FEAT | `Backlog` | Por alocar | Segundo adaptador de recolha. |
| **[#10](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/10)** | [FEAT] Implementar TelepizzaAdapter para promoções em Lisboa | FEAT | `Backlog` | Por alocar | Terceiro adaptador de recolha. |
| **[#11](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/11)** | [FEAT] Implementar PizzaHutAdapter para promoções em Lisboa | FEAT | `Backlog` | Por alocar | Quarto adaptador; depende da estratégia de persistência (#14). |
| **[#12](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/12)** | [FEAT] Motor de Normalização, Deduplicação e Pipeline de Agregação | FEAT | `Backlog` | Por alocar | Integração completa do pipeline de dados; depende de #14. |

---

## 4. Bloqueios e Dependências

- **Bloqueios Atuais:** Não existem bloqueios críticos ou impeditivos de trabalho imediato.
- **Dependências Mapeadas:**
  - Os tickets de integração avançada ([#11](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/11) e [#12](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/12)) dependem da aprovação e merge da arquitetura de persistência ([#14](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/14) / [PR #15](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/15)).
  - O desenvolvimento dos adaptadores ([#8](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/8), [#9](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/9), [#10](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/10)) está desbloqueado pelo contrato canónico já aprovado em [ADR-001](decisions/0001-data-contract-and-core-architecture.md).

---

## 5. Próximo Marco (Next Milestone)

- **Marco Imediato:** Conclusão da base de conhecimento navegável ([Issue #16](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/16)) e aprovação humana da [PR #15](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/15).
- **Marco Subsequente (Implementação de Coletores):** Transitar o [Issue #8](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/8) para `Ready`, alocar o `implementer` e criar a primeira implementação concreta de recolha: `PapaJohnsAdapter`.
