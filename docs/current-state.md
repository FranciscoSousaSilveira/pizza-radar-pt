# Estado Atual do Projeto — Pizza Radar PT

Este documento reflete a situação factual, as decisões vigentes e as frentes de trabalho ativas no repositório **Pizza Radar PT**. Deve ser mantido atualizado à medida que tickets e Pull Requests são concluídos.

---

## 1. Resumo Executivo

- **Fase Atual:** Fase 2 — Bloqueios de Release do MVP Lisboa (Investigação de Conectividade Externa).
- **Critério Obrigatório de Release:** **4 de 4 marcas** (Domino's Pizza, Pizza Hut, Telepizza, Papa John's) com recolha legítima, determinística e suficientemente fiável no concelho de Lisboa.
- **Decisão de Produto:** Não existe MVP nem lançamento público com cobertura parcial. Os estados `FAILED` e `STALE` servem exclusivamente como mecanismo de tolerância operacional transitória após o lançamento em produção (para absorver indisponibilidades pontuais de rede de fornecedores), nunca para justificar um lançamento incompleto.
- **Progresso Global:**
  - Fundação documental, contratos canónicos (`UnifiedPromo`) e arquitetura integrada em `main`.
  - Motor determinístico de rankings e persistência relacional com Turso libSQL integrada em `main` ([Issue #12](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/12) / [PR #23](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/23)).
  - Fiabilidade e tolerância de fontes integradas em `main` ([Issue #24](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/24) / [PR #27](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/27)): resiliência a falhas de rede, headers legítimos e isolamento de ofertas inválidas da Pizza Hut.
  - Classificação determinística `OfferType` e isolamento de complementos integrados em `main` ([Issue #25](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/25) / [PR #26](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/26)): produtos não-pizza (`2 refrigerantes`, `Copo Gelado`) nunca distorcem rankings de pizza; contagem e tamanho comprovados no Papa John's; sanitização total de `error_message` no snapshot público.
  - Validação empírica em ambiente de CI (GitHub Actions) confirmou recolha e persistência com sucesso para **Papa John's (27 ofertas)** e **Pizza Hut (19 ofertas)**.
  - Revelados bloqueios externos no ambiente de runners para **Domino's (HTTP 403 / Cloudflare WAF)** e **Telepizza (Connection Closed / Salesforce WAF)**.
  - **Issues #28 e #29** abertos e definidos como **bloqueadores formais do MVP**.

---

## 2. Decisões Técnicas Vigentes

| Decisão / ADR | Estado | Resumo Técnico | Documento |
| :--- | :--- | :--- | :--- |
| **ADR-001: Contrato Canónico de Dados, Interface de Adaptadores e Core** | **Aceite** *(Integrado em `main`)* | Representação monetária estrita em cêntimos inteiros (`price_cents`, `original_price_cents`); escopo geográfico explícito (`StoreScope`) sem assumir disponibilidade universal; decomposição de componentes de oferta (`OfferComponent`) sem inventar dados; carimbo temporal `observed_at` timezone-aware; interface agnóstica `PromoAdapterInterface`; 100% Python stdlib determinístico (sem dependências externas). | [docs/decisions/0001-data-contract-and-core-architecture.md](decisions/0001-data-contract-and-core-architecture.md) |
| **ADR-002: Execução, Hosting Estático e Persistência Gratuita** | **Aceite e Integrada** *(Integrado em `main`)* | Base de dados Turso libSQL (5 GB storage no free tier sem suspensão por inatividade); frontend estático alojado no Cloudflare Pages (CDN global gratuita); coletores Python agendados via GitHub Actions (2x/dia); publicação híbrida em `promotions.json` em CDN via GitHub Secrets sem poluir a `main`; tolerância a falhas sem incremento indevido de ausências; orçamento total de 0,00€/mês; zero IA em runtime. | [docs/decisions/0002-execution-hosting-and-free-tier-persistence.md](decisions/0002-execution-hosting-and-free-tier-persistence.md)<br/>[docs/architecture-execution-hosting-persistence.md](architecture-execution-hosting-persistence.md) |
| **Decisão de Produto: Critério Estrito de Lançamento (4 de 4 Marcas)** | **Aceite** | 4 de 4 marcas são obrigatórias para o MVP. Proibido lançamento com cobertura parcial. Estados `FAILED`/`STALE` limitados a tolerância transitória pós-release. | [docs/current-state.md](current-state.md) |

---

## 3. Tickets e Pull Requests Ativos

A tabela reflete o estado no quadro [GitHub Project `Pizza-radar-project`](https://github.com/users/FranciscoSousaSilveira/projects/1):

| Referência | Título Real do Ticket | Tipo | Estado no Project | Responsável / Agente | Notas |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **[#28](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/28)** | [SPIKE] Investigar alternativas públicas oficiais para recolha da Domino's Portugal | SPIKE | `Ready` / `In Progress` | `source-researcher` | **Bloqueador formal de release**. Investigação de superfícies públicas alternativas perante bloqueio HTTP 403 do Cloudflare WAF no runner. |
| **[#29](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/29)** | [SPIKE] Investigar alternativas públicas oficiais para recolha da Telepizza Portugal | SPIKE | `Ready` / `In Progress` | `source-researcher` | **Bloqueador formal de release**. Investigação de alternativas perante fecho de ligação TCP pelo WAF Salesforce Demandware. |
| **[PR #26](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/26)** / **[#25](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/25)** | [FEAT] Classificação de ofertas pizza-only, estado por vendedor e transparência na UI | FEAT | `Done` *(Fechado)* | `orchestrator` / `implementer` | Integrado em `main` via squash merge. 179 testes determinísticos aprovados. |
| **[PR #27](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/27)** / **[#24](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/24)** | [FEAT] Fiabilidade de fontes em GitHub Actions e resiliência por item | FEAT | `Done` *(Fechado)* | `orchestrator` / `implementer` | Integrado em `main` via squash merge. |
| **[PR #23](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/23)** / **[#12](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/12)** | [CHORE] Pipeline de automação para recolha periódica e persistência estática | CHORE | `Done` *(Fechado)* | `implementer` | Integrado em `main` via squash merge. |
| **[PR #22](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/pull/22)** / **[#11](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/11)** | [FEAT] Interface web responsiva para visualização e filtragem de promoções em Lisboa | FEAT | `Done` *(Fechado)* | `orchestrator` / `reviewer` | Integrado em `main` via squash merge. |
| **[#18](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/18)** | [SPIKE] Investigar códigos promocionais em canais sociais e parceiros oficiais | SPIKE | `Backlog` | Por alocar | Não bloqueador. |

---

## 4. Bloqueios e Dependências

- **Bloqueios Formais do MVP:**
  1. **[Issue #28](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/28):** Domino's bloqueia requisições em runners de CI com HTTP 403 (Cloudflare WAF).
  2. **[Issue #29](https://github.com/FranciscoSousaSilveira/pizza-radar-pt/issues/29):** Telepizza fecha ligações de runners de CI (Salesforce WAF).
- **Diretrizes Estritas:**
  - Proibidos proxies residenciais ou pagos, serviços pagos de scraping, bypass de CAPTCHA/WAF e credenciais privadas.
  - Proibido implementar soluções dependentes de computador pessoal sempre ligado sem aprovação como decisão de produto.
  - Investigação focada exclusivamente em superfícies públicas oficiais, APIs de clientes oficiais e ambientes de execução gratuitos (Cloudflare Workers/Pages Functions, etc.).

---

## 5. Próximos Passos

1. Executar as investigações técnicas dos Spikes #28 e #29 através de `source-researcher` independentes.
2. Produzir diagnóstico factual, opções técnicas com custos/limites/riscos e recomendação sustentável para alcançar 4 de 4 marcas.
3. Não efetuar merge de novos adaptadores nem ativar deploy/pipeline até decisão explícita do utilizador.
