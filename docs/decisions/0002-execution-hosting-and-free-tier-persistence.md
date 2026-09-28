# ADR-002: Arquitetura de Execução, Alojamento, Base de Dados Free-Tier e Publicação de Dados

- **Data:** 2026-09-28
- **Estado:** Aceite
- **Decisores:** Equipa Multiagente Permanente (Project Manager, Orchestrator, Implementer, Reviewer)

## Contexto

Após a consolidação do contrato canónico de dados (`UnifiedPromo`) e da interface de adaptadores na ADR-001 (#7), o projeto necessitava de definir a sua arquitetura global de infraestrutura, alojamento e persistência para o MVP, dando resposta ao Issue #14.

Os requisitos fundamentais eram:
1. **Alojamento Frontend Online:** Solução estável, com CDN global e sem custos mensais.
2. **Base de Dados Relacional Free-Tier Real:** O sistema deve operar sobre uma base de dados relacional para consistência transacional, auditoria e histórico de preços; o uso de ficheiros JSON não pode substituir a decisão de base de dados.
3. **Coletores Python Agendados:** Execução periódica determinística sem custos de infraestrutura.
4. **Publicação Eficiente:** Estratégia que não sobrecarregue a base de dados com o tráfego dos utilizadores finais.
5. **Atualização, Expiração e Histórico:** Regras claras e determinísticas para desativação de campanhas caducadas ou descontinuadas.
6. **Observabilidade e Resiliência:** Tratamento e notificação de falhas sem ferramentas pagas.
7. **Orçamento Zero (0,00 € / mês):** Cumprimento estrito de planos gratuitos reais.
8. **Portabilidade e Plano de Saída:** Código agnóstico de fornecedor, com abstrações formais e procedimentos de migração documentados.
9. **Zero IA em Runtime:** Proibição absoluta de modelos de linguagem em produção.

## Decisão

1. **Alojamento Web:** **Cloudflare Pages**
   - Oferece largura de banda ilimitada, 500 builds por mês, certificados SSL automáticos e distribuição global Anycast. Não impõe restrições não-comerciais restritivas (como o Vercel Hobby).

2. **Base de Dados Canónica:** **Turso (libSQL / SQLite Serverless)**
   - O Turso disponibiliza 5 GB de armazenamento gratuito e 10 milhões de escritas mensais.
   - **Vantagem Crítica sobre o Supabase:** O Turso **não suspende nem pausa a base de dados por inatividade** no plano gratuito (ao contrário do Supabase, que pausa ao fim de 7 dias sem queries SQL).
   - **Protocolo e Autenticação:** O Turso remoto opera sobre o protocolo libSQL (HTTP/WebSocket) e exige autenticação por token (`TURSO_AUTH_TOKEN`).
   - **Portabilidade Real e Plano de Saída:** A portabilidade não se resume a alterar uma string `DATABASE_URL`. A migração apoia-se em:
     - **Abstração por Repositório (`PromotionRepository`):** Interface Python desacoplada da implementação concreta (`LibSqlPromotionRepository`, `SqlitePromotionRepository`, `PostgresPromotionRepository`).
     - **Divergências de Dialeto e Esquema SQL:** SQLite/libSQL difere de PostgreSQL (ex.: `AUTOINCREMENT` vs. `IDENTITY`/`SERIAL`, semântica de datas e tipos booleanos). Esquemas DDL separados e scripts de migração são documentados formalmente.
     - **Exportação de Dados:** Dados exportáveis via dump SQL ou extração canónica em JSON para reconstituição noutro SGBD.

3. **Agendamento de Coletores:** **GitHub Actions**
   - Workflow agendado duas vezes ao dia (10:30 e 17:30 UTC), cobrindo almoço e jantar.
   - **Estimativa de Consumo:** Estima-se preliminarmente um consumo de ~30 a 60 minutos/mês (cerca de 1.5% a 3% do teto de 2.000 minutos do GitHub Free em repositórios privados). A duração real de cada execução depende da latência externa das fontes e será validada através de benchmarks reais durante a implementação da pipeline.

4. **Estratégia de Publicação Híbrida (Base de Dados + Cache Estática CDN):**
   - A base de dados funciona como a Fonte Única da Verdade (*Single Source of Truth*), histórico e auditoria.
   - A cada ciclo de recolha bem-sucedido, o pipeline extrai as promoções ativas (`is_active = 1`) e gera um artefacto determinístico `promotions.json`.
   - **Mecanismo Concreto de Publicação no Cloudflare Pages:**
     - O ficheiro `promotions.json` **não é comitado manualmente nem adicionado à branch `main`**, evitando poluição do histórico git e conflitos de merge.
     - O upload/deploy para o Cloudflare Pages é realizado diretamente a partir do runner de CI via API/Action oficial (ex.: `cloudflare/wrangler-action`), autenticado através de **GitHub Secrets** (`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`).
     - A implementação concreta e configuração de secrets fica reservada para o ticket da pipeline de automação (#12), sem criação de credenciais nesta fase.
   - **Desempenho Estimado:** Carregamento ultra-rápido estimado (da ordem de sub-50ms no edge cache, a validar por medições e benchmarks reais de rede).

5. **Política Determinística de Expiração e Tolerância a Falhas:**
   - **Expiração por Data Anunciada:** Ofertas com data `valid_until` ultrapassada são desativadas (`is_active = 0`).
   - **Isolamento de Falhas e Contador de Ausências (`consecutive_misses`):**
     - Uma falha de rede ou erro de parsing na recolha de um vendedor específico **não conta como ausência** das suas promoções.
     - O contador `consecutive_misses` **só é incrementado quando a recolha desse vendedor terminar comprovadamente com sucesso** e a oferta não estiver presente no lote extraído.
     - As duas sincronizações diárias ocorrem a intervalos assimétricos (7 horas entre almoço e jantar; 17 horas durante a noite), pelo que o critério de expiração é baseado em **sincronizações consecutivas com sucesso** (ex.: `consecutive_misses >= 2`) e não numa presunção fixa de "24 horas".
   - **Registo Histórico:** Todas as observações de preços confirmadas são registadas em `observation_history`.

6. **Observabilidade e Resiliência sem Recuperação Efémera Falsa:**
   - Notificações de falha no pipeline via alertas por email do GitHub Actions.
   - **Sem Fallback Local Durável em Runners Efémeros:** O sistema de ficheiros do runner do GitHub Actions é destruído no final da execução. Se a base de dados Turso estiver inacessível, o runner **não altera estados nem publica snapshots parciais/incompletos** na CDN. A falha é registada nos logs, mantendo a versão íntegra anterior na CDN, e uma nova tentativa ocorrerá na sincronização agendada seguinte. Ficheiros gerados localmente no runner servem apenas para artefactos temporários de diagnóstico/depuração.

## Consequências

### Positivas (Prós)
- **Custo Operacional Totalmente Nulo:** 0,00 €/mês para a escala do MVP, sustentado em quotas oficiais verificadas.
- **Isolamento entre Leitura e Escrita:** A CDN absorve 100% das leituras do utilizador final; a BD serve apenas para sincronizações pontuais.
- **Portabilidade Real:** Suportada por abstração de interface (`PromotionRepository`) e esquemas adaptados por motor relacional.
- **Integridade de Dados:** Falhas parciais de rede não provocam desativação acidental de promoções legítimas.

### Negativas / Compromissos (Contras / Trade-offs)
- A sincronização periódica (2x/dia) não reflete ofertas flash de duração inferior a algumas horas (compromisso assumido no charter: atualização periódica, não contínua).
- A publicação via CDN tem uma latência de propagação de alguns segundos após o término do pipeline de CI.

### Riscos Técnicos e Mitigações

1. **Risco:** Alteração unilateral de quotas por parte dos fornecedores gratuitos (Cloudflare, Turso, GitHub).
   - **Mitigação:** Planos de saída documentados para cada componente (SQLite local / VPS gratuita / Vercel / Neon).
2. **Risco:** Falha transitória de conectividade entre o GitHub Actions runner e o endpoint remoto do Turso.
   - **Mitigação:** O runner aborta de forma segura sem tocar no snapshot em produção na CDN nem cometer dados parciais. A execução subsequente retoma a sincronização.

---

## 7. Fontes Oficiais e Data de Verificação de Quotas

Todas as quotas, limites e políticas dos fornecedores avaliados foram confirmadas diretamente na respetiva documentação oficial:

| Fornecedor / Serviço | Documento / Fonte Oficial Consultada | Data de Verificação | Quotas e Regras Confirmadas |
| :--- | :--- | :--- | :--- |
| **Turso (libSQL)** | [Turso Pricing](https://turso.tech/pricing) e [Plan Limits](https://docs.turso.tech/plans) | **2026-09-28** | **5 GB** de armazenamento, **10M de escritas/mês**, **500M de leituras/mês**. Confirmada a **ausência de pausa ou suspensão por inatividade** no plano gratuito. |
| **Cloudflare Pages** | [Cloudflare Pages Limits](https://developers.cloudflare.com/pages/platform/limits/) e [Plans](https://www.cloudflare.com/plans/) | **2026-09-28** | **Largura de banda ilimitada**, **500 builds/mês**, 100 domínios personalizados, requisições estáticas ilimitadas. |
| **GitHub Actions** | [About Billing for GitHub Actions](https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions) | **2026-09-28** | **2.000 minutos/mês** gratuitos para contas padrão em repositórios privados (e ilimitado em repositórios públicos). |
| **Supabase** | [Supabase Project Pausing](https://supabase.com/docs/guides/platform/pausing) e [Pricing](https://supabase.com/pricing) | **2026-09-28** | Projetos no plano Free entram em **pausa automática após 7 dias de inatividade** sem queries SQL ou chamadas API diretas. |
