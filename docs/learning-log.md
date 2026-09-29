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

### [2026-09-29] — Domino's: Resolução de Egress via Browserless Content API (Modo Datacenter Free-Tier)

- **Contexto / Ticket:** Issue #28 ([SPIKE] Domino's Portugal) e PR #30
- **Desafio / Descoberta:** Runners de CI em data centers (Azure ASN no GitHub Actions e Google ASN no Apps Script) sofrem bloqueio HTTP 403 (Cloudflare Bot Fight Mode) tanto no endpoint AJAX como no HTML direto da homepage. Contudo, testes empíricos com a Content API europeia da Browserless (`POST https://production-lon.browserless.io/content`) em modo datacenter (sem proxy residencial, sem bypass de CAPTCHA) obtiveram HTTP 200 com sucesso em 1,54 segundos, extraindo a totalidade dos 5 combos oficiais.
- **Impacto:** O consumo medido é de apenas 1 unidade por execução. Com 1 execução/dia (30 unidades/mês), o consumo representa ~3% da quota mensal gratuita da Browserless (1.000 unidades/mês), mantendo o custo global do projeto rigorosamente em 0,00€/mês.
- **Decisão / Solução:** Atualizado o `DominosAdapter` na PR #30 para executar a Content API da Browserless no fallback de HTTP 403:
  1. Envio da chave de API estritamente no cabeçalho `Authorization: Bearer <token>` (nunca na query string nem exposta em logs/erros).
  2. Rejeição ativa de imagens, fontes, media e folhas de estilo para otimização de tempo e largura de banda.
  3. Validação determinística de ausência de desafio Cloudflare e presença de atributos `combo-id`.
  4. Ausência de segredo ou falhas de rede propagam `NetworkError`, preservando os dados atómicos existentes na base de dados (`status = PRESERVED`).
  5. Injeção do segredo `BROWSERLESS_API_KEY` no workflow agendado de CI.
- **Ação Futura:** Configurar o segredo no repositório GitHub via `gh secret set` e validar o snapshot em dry-run.

### [2026-09-29] — Domino's: Fallback Híbrido para Homepage Pública Oficial e Nível de Cobertura Transparente

- **Contexto / Ticket:** Issue #28 ([SPIKE] Investigar alternativas públicas oficiais para recolha da Domino's Portugal)
- **Desafio / Descoberta:** O endpoint `POST /ajax/order.php` da Domino's é bloqueado com HTTP 403 Forbidden pelo Cloudflare WAF perante pedidos provenientes de runners de CI (GitHub Actions). Contudo, a homepage pública oficial (`https://www.dominospizza.pt/`) está completamente aberta (HTTP 200) e contém a totalidade das campanhas de marketing ativas em elementos HTML com atributos estruturados (`combo-id`, `delivery-type`, `offer-title`, `offer-txt`, `data-src`, `infoTooltip`).
- **Impacto:** O adaptador consegue recolher deterministicamente as 5 campanhas oficiais de topo (Leiria 1=2, Terças de Perder a Cabeça 50% desc, Croissantíssima 9,99€, Média desde 10,95€ e 30% desc frangos), produzindo 8 ofertas unificadas válidas distribuídas pelos canais comprovados (Entrega e Take Away) sem inventar dados nem recorrer a técnicas proibidas de contorno de WAF.
- **Decisão / Solução:** Implementado um fallback híbrido determinístico em `DominosAdapter`:
  1. Tenta prioritariamente `POST /ajax/order.php` para recolha do catálogo integral da loja-âncora (`coverage_level = "FULL"`).
  2. Perante HTTP 403 exclusivamente, ativa o fallback para `https://www.dominospizza.pt/` e extrai as campanhas principais (`coverage_level = "FEATURED"`, nota: `"Campanhas principais publicadas no site oficial"`).
  3. Erros de parsing no endpoint primário NÃO ativam fallback, preservando a visibilidade de eventuais regressões.
  4. Adicionada transparência de cobertura na UI (`web/app.js`) com crachá distintivo "Destaques", cumprindo o compromisso de nunca afirmar "todas as promoções" quando apenas uma seleção representativa está acessível.
- **Ação Futura:** Validar a execução no ambiente real do GitHub Actions após merge da PR #30.

### [2026-09-29] — Decisão de produto: obrigatoriedade estrita de 4 de 4 marcas e bloqueios de infraestrutura de CI

- **Contexto / Ticket:** Issues #24, #25, #28 e #29 (Bloqueios de Release do MVP Lisboa)
- **Desafio / Descoberta:**
  1. **Ensaio em Ambiente Real de CI:** A execução de teste em GitHub Actions com credenciais reais revelou bloqueios de tráfego de data center originados por proteções anti-bot em duas marcas:
     - **Domino's:** Retorna HTTP 403 Forbidden no endpoint oficial de pedidos (`ajax/order.php`) devido a regras de ASN/datacenter do Cloudflare WAF durante o warmup de sessão.
     - **Telepizza:** O servidor Salesforce Commerce Cloud encerra imediatamente a ligação TCP (`Remote end closed connection without response`) para blocos de IP de runners do GitHub Actions.
  2. **Papa John's e Pizza Hut Funcionais:** Papa John's (27 ofertas ativas) e Pizza Hut (19 ofertas válidas, após ignorar de forma tolerante 7 itens sem canal comprovado) demonstraram recolha e persistência 100% determinísticas e bem-sucedidas.
  3. **Decisão de Produto Inflexível:** Não existe MVP nem lançamento público com cobertura parcial (ex.: 2 de 4 marcas). O valor central da proposta ao consumidor exige a presença das 4 marcas de referência em Lisboa.
  4. **Papel dos Estados FAILED/STALE:** Os estados `FAILED` e `STALE` foram concebidos e sanitizados no snapshot para fornecer tolerância operacional temporária a quebras transitórias em produção, nunca para justificar o lançamento de um produto incompleto.
- **Impacto:** O lançamento do MVP fica formalmente condicionado à resolução legítima e sustentável da recolha das 4 marcas. Os Spikes #28 e #29 passam a bloqueadores formais da release.
- **Decisão / Solução:** Merges das melhorias das PRs #27 e #26 mantidos na `main` apenas como evolução interna. Bloqueio estrito de deploy e pipelines agendadas até conclusão da investigação de superfícies públicas oficiais alternativas para Domino's e Telepizza.
- **Ação Futura:** Conduzir investigações paralelas com `source-researcher` focadas em endpoints alternativos públicos oficiais, dados estruturados ou plataformas com rede permitida (ex.: Cloudflare Workers / Pages Functions), sem violar as regras de proibição de proxies pagos, CAPTCHA bypass ou IA em runtime.

### [2026-09-28] — Pipeline de automação, persistência relacional e resiliência a falhas de fornecedores

- **Contexto / Ticket:** Issue #12 — [CHORE] Pipeline de automação para recolha periódica e persistência estática
- **Desafio / Descoberta:**
  1. **Isolamento de Falhas por Vendedor:** Em scrapers agregadores é comum a falha de uma API externa (ex.: timeout, 502, alteração de layout) provocar a remoção ou expiração indevida de dados na base de dados. Era indispensável garantir que a falha de um adaptador deixa intactas as promoções ativas desse operador.
  2. **Contador Condicional de Ausências (`consecutive_misses`):** O contador de ausências só pode ser incrementado se a execução desse vendedor tiver terminado comprovadamente com sucesso. Se o coletor falhou, `consecutive_misses` não é alterado.
  3. **Persistência Relacional vs. Snapshot CDN:** A base de dados relacional (`PromotionRepository` com SQLite local e libSQL remoto) mantém a integridade e histórico de observações (`observation_history`), enquanto o snapshot determinístico (`promotions.json`) é exportado e publicado via CDN no Cloudflare Pages sem cometer ficheiros à `main`.
  4. **Abortamento Seguro:** Se a base de dados falhar durante a recolha, o pipeline aborta a geração e publicação de snapshot, garantindo que a versão estável pré-existente na CDN continua a servir os utilizadores.
- **Impacto:** Arquitetura robusta de recolha 2x/dia (10:30 e 17:30 UTC via GitHub Actions), com tolerância total a falhas isoladas de fornecedores e suíte unitária determinística cobrindo persistência, isolamento e exportação.
- **Decisão / Solução:** Implementados os módulos `pizza_radar.persistence` (`schema.sql`, `PromotionRepository`, `SQLitePromotionRepository`, `TursoPromotionRepository`, `export_snapshot`) e `pizza_radar.pipeline` (`run_pipeline`, `cli`), e workflow agendado `.github/workflows/scheduled-pipeline.yml`.
- **Ação Futura:** Conectar os segredos do repositório (`TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`) quando o utilizador desejar ativar a infraestrutura na nuvem.

### [2026-09-28] — Interface web responsiva: identidade autêntica, rankings explicáveis e transparência de dados

- **Contexto / Ticket:** Issue #11 — [FEAT] Interface web responsiva para visualização e filtragem de promoções em Lisboa
- **Desafio / Descoberta:**
  1. **Evitar Clichés Genéricos de IA:** Fugir do padrão comum de fundos creme (#F4F1EA), serifas clássicas artificiais e acentos terracota. Desenhou-se um design system deliberado e focado no tema (Pizza Radar Lisboa) com contraste WCAG elevado, fontes de sistema limpas, números tabulares para preços e paleta com identidade própria de cada pizzaria.
  2. **Rankings Explicáveis com Banners de Contexto:** Cada um dos 4 rankings (`LOWEST_ABSOLUTE_PRICE`, `HIGHEST_DISCOUNT`, `BEST_UNIT_PRICE`, `RECENTLY_OBSERVED`) apresenta um banner explicativo contextual que descreve exatamente o critério matemático utilizado, sem ambiguidades.
  3. **Transparência na Incerteza Geográfica:** Quando o âmbito de lojas é desconhecido na fonte (`StoreScope.UNKNOWN`), o cartão exibe com clareza o aviso "Lojas participantes não discriminadas no catálogo online oficial", nunca inventando cobertura nem assumindo disponibilidade universal.
  4. **Sem Checkout nem Intermediação:** Cada cartão inclui botão direto "Ver oferta no site oficial" que direciona o utilizador para a página oficial da marca (`source_url`), sem formulários de pagamento nem recolha de dados pessoais.
- **Impacto:** Aplicação web estática ultra-leve (< 20 KB de JS/CSS puros), zero dependências externas, compatível com Cloudflare Pages, com screenshots desktop e mobile validados e 117 testes unitários determinísticos.
- **Decisão / Solução:** Implementados `web/index.html`, `web/styles.css`, `web/app.js` e fixture canónica `web/data/promotions.json`. Capturados screenshots determinísticos em `docs/screenshots/`.
- **Ação Futura:** Integrar com o deploy automatizado do GitHub Actions implementado no Issue #12.


### [2026-09-28] — Adaptadores Telepizza, Domino's e Pizza Hut: especificidades de parsing, âmbito geográfico e isolamento

- **Contexto / Ticket:** Issue #9 — Implementar adaptadores para Telepizza, Domino's e Pizza Hut (Lisboa)
- **Desafio / Descoberta:**
  1. **Domino's:** O endpoint `POST ajax/order.php` devolve `Content-Type: text/html` apesar de o payload ser JSON estrito; títulos incluem preços inteiros (`12€`, `27€`) e decimais (`10,95€`), exigindo conversão direta para `Decimal`. A loja 140 (Areeiro) é utilizada estritamente como amostra/âncora de Lisboa sem extrapolar cobertura de todo o concelho. Campos obrigatórios ausentes (`id`, `title`) emitem `ParseError` explícito.
  2. **Telepizza:** O catálogo público em `/promocoes` possui cartões HTML cuja ordem de atributos varia. Foi implementado `TelepizzaHTMLParser` (`html.parser.HTMLParser`) para extração imune à permutação de atributos. Não se assume delivery + takeaway por omissão: os canais são extraídos apenas mediante evidência na fonte (`data-tab-content` ou texto), emitindo `ParseError` se não houver canal comprovado. `store_scope` é explicitamente `StoreScope.UNKNOWN` pois a página pública não comprova a lista de lojas participantes no concelho.
  3. **Pizza Hut:** O endpoint WP REST API (`/wp-json/wp/v2/ofertas`) devolve 26 ofertas ativas; títulos contêm entidades HTML (`&#8211;`). Os canais são identificados determinísticamente pelo slug (`-tw` balcão, `-dlv` entrega, `-ei` sala) e texto, nunca presumindo entrega e takeaway em simultâneo sem evidência. O âmbito de lojas é definido como `StoreScope.UNKNOWN` (a menos que lojas aderentes venham comprovadas no payload).
  4. **Isolamento de Falhas e Orquestração:** Os testes unitários verificam o isolamento contratual entre adaptadores (falha de um não propaga para outros). Fica expressamente documentado que a orquestração de produção, agendamento de execução e recuperação de falhas no runner efémero pertencem ao escopo do Issue #12 (pipeline de automação).
- **Impacto:** Cobertura determinística das 4 marcas do MVP de Lisboa com contratos auditáveis, precisão monetária estrita em Decimal/cêntimos e representação fidedigna de incerteza geográfica e de canais.
- **Decisão / Solução:** Implementados `DominosAdapter`, `TelepizzaAdapter` e `PizzaHutAdapter` com testes unitários determinísticos cobrindo permutações de atributos HTML, lojas conhecidas vs. desconhecidas, canais e isolamento contratual.
- **Ação Futura:** Integrar no pipeline agendado do GitHub Actions no Issue #12.


### [2026-09-28] — Identidade persistente de histórico vs. agrupamento visual e rankings explicáveis

- **Contexto / Ticket:** Issue #10 — Motor determinístico de normalização, cálculo de descontos e ranking de ofertas
- **Desafio / Descoberta:** Diferenciar claramente três conceitos que frequentemente colidem em agregadores:
  1. A identidade estável no tempo necessária para a tabela de histórico (`observation_history`), que não pode mudar quando lojas convergem ou divergem em preço;
  2. A variante concreta por loja que retém especificidades de preço e validade;
  3. O agrupamento visual para o frontend, que deve garantir que o utilizador nunca vê cartões duplicados para a mesma campanha no mesmo canal.
- **Impacto:** Criada a distinção formal entre `PersistentIdentity` (chave lógica imutável `vendor + campaign + channel`), `StoreVariant` e `VisualPromoGroup`. Os rankings (`BEST_UNIT_PRICE`, `HIGHEST_DISCOUNT`, `LOWEST_ABSOLUTE_PRICE`, `RECENTLY_OBSERVED`) fornecem justificações explícitas e operam 100% matematicamente sem modelos de IA.
- **Decisão / Solução:** Implementado módulo `pizza_radar/engine/` com 82 testes unitários determinísticos a cobrir estabilidade de IDs, cálculos de métricas, filtros e ausência de cartões duplicados.
- **Ação Futura:** Integrar com o motor de persistência SQLite/Turso no Issue #12.


### [2026-09-28] — Estrutura real da API Papa John's, precisão Decimal e desduplicação entre lojas

- **Contexto / Ticket:** Issue #8 — PapaJohnsAdapter
- **Desafio / Descoberta:**
  1. A investigação confirmou que o endpoint `/v1/offers/promotions` não inclui `offer_groups` (detalhes de composição estão apenas em `/v1/offers/{id}`).
  2. O uso de representação em `float` arrisca perda de precisão binária IEEE-754; o parsing JSON nativo deve utilizar `parse_float=Decimal` e conversão determinística para integer cents via `(Decimal * 100).quantize(1, ROUND_HALF_UP)`. Valores inválidos não devem ser silenciados para `None`.
  3. As 3 lojas de Lisboa (Amoreiras, Areeiro, Benfica) partilham os mesmos catálogos promocionais por canal; produzir um cartão por loja gerava duplicações artificiais.
  4. O endpoint expõe itens de teste/internos com flag `hidden=true`, que não devem ser publicados.
- **Impacto:** O adaptador agrega deterministicamente lojas com preços e condições idênticos num único `UnifiedPromo` (`pj_{id}_{canal}` com `store_ids` e `store_names` consolidados), mantendo variantes separadas apenas quando há divergência real. Itens com `hidden=true` são excluídos no parser. Preços utilizam `Decimal` em toda a cadeia de ingestão.
- **Decisão / Solução:** Implementado `parse_price_to_cents` estrito, agrupamento por assinatura de conteúdo da oferta, filtro de ofertas ocultas e 63 testes unitários sem chamadas de rede.
- **Ação Futura:** Criada nota no Issue #8 para futura evolução de enriquecimento via `/v1/offers/{id}` e páginas públicas de promoções.


### [2026-09-28] — Organização da Documentação como Base de Conhecimento Navegável

- **Contexto / Ticket:** Issue #16 ([CHORE] Organizar documentação como knowledge base navegável)
- **Desafio / Descoberta:** O crescimento de documentos no repositório (charter, viabilidade, contrato canónico, propostas de arquitetura e equipa permanente) aumentou a necessidade de uma navegação fluida entre artefactos, sem duplicar o estado do projeto nem introduzir ferramentas complexas ou dependências de pesquisa vetorial/RAG.
- **Impacto:** Estabelecido o `docs/README.md` como catálogo central com indicação de finalidade e momento de leitura de cada documento, o `docs/current-state.md` como registo factual conciso do estado vivo, e adicionados 6 trilhos de leitura por especialidade no `AGENTS.md`. Todos os links utilizam sintaxe relativa padrão em Markdown, permitindo navegação tanto no GitHub como em modo Vault no Obsidian.
- **Decisão / Solução:** Manter o `README.md` da raiz focado na proposta de valor pública, delegar o acompanhamento do estado operacional para `docs/current-state.md`, e interligar os documentos existentes através de hiperligações contextuais.
- **Ação Futura:** Manter o `docs/current-state.md` atualizado a cada transição ou fecho de ticket/PR.

### [2026-09-28] — Arquitetura de Execução, Alojamento e Persistência Free-Tier

- **Contexto / Ticket:** Issue #14 ([ARCH] Arquitetura de execução, alojamento e persistência free-tier)
- **Desafio / Descoberta:** Conciliar o requisito obrigatório de uma base de dados relacional real com um orçamento estrito de 0,00€/mês e a necessidade de não sofrer pausas por inatividade (problema crítico do Supabase Free). Adicionalmente, mapear com rigor as diferenças de protocolo/DDL do Turso remoto e modelar a tolerância a falhas sem penalizar vendedores cujos coletores sofreram erro de rede transitório.
- **Impacto:** Adotou-se o Turso (libSQL/SQLite Serverless) com 5 GB gratuitos e sem suspensão por inatividade como base de dados canónica primária, complementado por geração periódica de snapshot estático (`promotions.json`) distribuído na CDN global do Cloudflare Pages (deploy direto do CI via GitHub Secrets, sem ficheiro gerado na `main`).
- **Decisão / Solução:** Formalizada na ADR-002 e documentada em `docs/architecture-execution-hosting-persistence.md`. Os coletores Python executam via GitHub Actions (consumo estimado de ~20-60 min/mês de 2.000 min gratuitos), persistem na base de dados com regras de expiração determinísticas (apenas incrementando ausências quando a recolha desse vendedor tem sucesso), e utilizam a interface `PromotionRepository` para garantir portabilidade real entre Turso, SQLite local e PostgreSQL. Runners efémeros não utilizam falso fallback local durável, mantendo intacto o snapshot íntegro na CDN em caso de falha de conexão.
- **Ação Futura:** Implementar os adaptadores de recolha (#8, #9) e configurar o pipeline agendado (#12) sobre esta infraestrutura.


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
