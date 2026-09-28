# Relatório de Viabilidade Técnica de Fontes de Dados — Pizza Radar PT

**Data:** 28 de Setembro de 2026  
**Âmbito Geográfico:** Concelho de Lisboa  
**Vendedores Analisados:** Domino's Pizza, Pizza Hut, Telepizza, Papa John's  
**Ticket de Referência:** Issue #3 (SPIKE)  

---

## 1. Resumo Executivo

Este documento apresenta a investigação técnica sobre a viabilidade de obtenção contínua, pública e determinística dos catálogos promocionais oficiais das quatro principais cadeias de pizzarias a operar no concelho de Lisboa (Portugal).

A investigação foi conduzida exclusivamente sobre superfícies públicas, sem login, sem simulação de transações de compra ou checkout e sem contorno de proteções técnicas (CAPTCHA, WAF ou anti-bot), em estrita conformidade com o `AGENTS.md`.

### Principais Conclusões

1. **Viabilidade Global Excelente:** Todas as 4 marcas disponibilizam informação promocional pública acessível de forma determinística sem recurso a autenticação ou execução de browsers pesados (*headless* como Puppeteer ou Playwright).
2. **Camada de Dados Acessível:** Duas marcas (**Papa John's** e **Domino's Pizza**) dispõem de endpoints de API pública com payloads JSON estruturados; a **Pizza Hut** expõe uma API REST nativa em WordPress (`wp-json`) combinada com SSR; a **Telepizza** utiliza Server-Side Rendering (Salesforce Commerce Cloud) com metadados estruturados em **JSON-LD Schema.org** e atributos HTML `data-*`.
3. **Localização no Concelho de Lisboa:** Nenhuma das quatro marcas exige código postal ou morada para consultar as campanhas e preços. Nas 4 marcas, as promoções são geridas num catálogo unificado a nível nacional ou mapeadas diretamente por lojas físicas conhecidas do concelho de Lisboa.
4. **Variação por Canal (Take Away vs. Delivery):** É o fator determinante de diferenciação em todas as marcas. As promoções de Take Away/Balcão apresentam preços consistentemente mais baixos (-1,00€ a -4,00€) face às de Entrega ao Domicílio.
5. **Conformidade Arquitetural:** O processo de extração, normalização e ranking pode operar com custo zero em infraestrutura gratuita (*free-tier*), sem qualquer chamada a modelos de IA no *runtime* de produção e com total portabilidade entre ambientes de execução.

---

## 2. Matriz Comparativa de Viabilidade

| Vetor de Análise | Domino's Pizza | Pizza Hut | Telepizza | Papa John's |
| :--- | :--- | :--- | :--- | :--- |
| **Domínio Oficial** | `dominospizza.pt` | `pizzahut.pt` | `telepizza.pt` | `papajohns.pt` |
| **Camada Primária** | API Pública AJAX (JSON) | WP REST API (`wp-json`) + SSR | SSR (JSON-LD + HTML `data-*`) | API REST Pública (JSON) |
| **Renderização JS Necessária?** | Não | Não | Não | Não |
| **Requisito de Morada/CP?** | Nenhum | Nenhum | Nenhum | Nenhum |
| **Universo em Lisboa** | 8 lojas mapeadas (Default: Areeiro `140`) | 12 lojas mapeadas (Restelo, Chiado, etc.) | 10 lojas mapeadas (Campo Ourique, Roma, etc.) | 3 lojas mapeadas (Amoreiras, Areeiro, Benfica) |
| **Volume Médio de Ofertas** | 34 combos (D) / 34 combos (C) | 26 ofertas ativas | 22 promoções + 18 menus | ~15 combos/menus ativos |
| **Diferenciação D/C** | Sim (Take-away -1€ a -1,50€) | Sim (ofertas exclusivas TW/DLV/Sala) | Sim (Take-away -2€ a -4€) | Sim (Take-away -3€ a -4€) |
| **Proteção WAF/Anti-Bot** | Cloudflare (requer UA de browser e `X-Requested-With`) | Cloudflare (passa com UA padrão) | Cloudflare (passa com UA padrão) | Nenhuma proteção agressiva (AWS API Gateway) |
| **Headers Exigidos** | `User-Agent`, `X-Requested-With` | `User-Agent` | `User-Agent` | `X-PLATFORM: web` |
| **Dificuldade Técnica (1-5)** | **1 / 5** (Muito Baixa) | **1.5 / 5** (Baixa) | **1 / 5** (Muito Baixa) | **1 / 5** (Muito Baixa) |
| **Prioridade de Implementação** | 3.ª Recomendada | 4.ª Recomendada | 2.ª Recomendada | **1.ª Recomendada (Primeiro Adaptador)** |

---

## 3. Fichas Técnicas Detalhadas por Vendedor

### 3.1. Papa John's Portugal

#### A. Páginas Oficiais Relevantes
- **Portal Principal:** `https://www.papajohns.pt`
- **Hub de Promoções:** `https://www.papajohns.pt/promocoes/`
- **Páginas Individuais:** `https://www.papajohns.pt/promocoes/duo-bestial/`, `super-john/`, `trio-bestial/`, `papa-as-3as/`
- **Lojas de Lisboa:** `https://www.papajohns.pt/lojas/lisboa/` (Amoreiras - ID 2, Areeiro - ID 13, Benfica - ID 3)
- **API REST Pública:**
  - `GET https://api.papajohns.pt/v1/stores?latitude=38.7223&longitude=-9.1393`
  - `GET https://api.papajohns.pt/v1/offers/promotions?store_id={id}&dispatch_method={pj_delivery|in_store}`
  - `GET https://api.papajohns.pt/v1/offers/{offer_id}?store_id={id}`

#### B. Necessidade de Localização e Concelho de Lisboa
- **Sem morada ou código postal:** O acesso ao catálogo e a todas as campanhas públicas não exige autenticação nem inserção de morada.
- **Uniformidade em Lisboa:** Testadas as 3 lojas do concelho de Lisboa (Amoreiras, Areeiro, Benfica). Os preços e produtos elegíveis de cada promoção são **100% idênticos** em todas as lojas de Lisboa.
- **Canais:** A única diferenciação reside na modalidade de serviço:
  - `in_store` (Take Away / Balcão): ofertas mais baratas (ex.: Duo Bestial a 17,98€; pizza individual a 7,99€).
  - `pj_delivery` (Entrega ao Domicílio): preço ligeiramente superior (ex.: Duo Bestial a 20,98€; Party Combo a 59,92€).

#### C. Promoções Encontradas e Regras de Negócio
- **Duo Bestial (ID 223):** 2 Pizzas Médias à escolha por 17,98€ (Take Away) ou 20,98€ (Delivery).
- **Trio Bestial (ID 200):** 3 Pizzas Médias por 23,97€ (Take Away) ou 25,47€ (Delivery).
- **Super John (ID 177):** 1 Pizza Média (3 ing.) + 1 Entrada + 1 Bebida 500ml por 9,99€ (Take Away) ou 13,99€ (Delivery).
- **O PAPITO Menu Individual (ID 222):** 1 Pizza Individual + 1 Entrada + 1 Bebida 500ml por 6,99€ (Take Away) ou 10,99€ (Delivery).
- **Papa às 3ªs:** Pizza média a 7,50€ na compra de pelo menos duas pizzas (15,00€ total), exclusivamente às terças-feiras.
- **Taxas e Pedidos Mínimos:** Pedido mínimo em delivery de 12,95€ e taxa fixa de entrega de 1,99€.

#### D. Camada Técnica e Modelo de Dados
- **Tipo de Resposta:** JSON nativo estruturado via API REST.
- **Campos Disponíveis:** `id`, `name`, `description`, `price`, `original_price`, `dispatch_method`, `availability` (dias da semana), `start_datetime`, `end_datetime`, `pictures` (URLs CDN em WebP), `offer_groups` (produtos e diferenciais de preço).
- **Cabeçalho Obrigatório:** `X-PLATFORM: web`. Pedidos sem este header retornam HTTP 403.

#### E. Frequência, Riscos e Dificuldade
- **Frequência de Alteração:** Baixa (campanhas estruturais anuais, promoções sazonais mensais).
- **Dificuldade de Recolha:** Nível 1 / 5 (Muito Baixa).
- **Riscos / Limitações:** Dependência do cabeçalho estático `X-PLATFORM: web`. Não existe bloqueio de Cloudflare ou CAPTCHA na rota de API.

---

### 3.2. Telepizza Portugal

#### A. Páginas Oficiais Relevantes
- **Hub de Promoções:** `https://www.telepizza.pt/promocoes`
- **Hub de Menus:** `https://www.telepizza.pt/menus`
- **Condições Legais:** `https://www.telepizza.pt/condicoes-promocionais.html`
- **Rodízio:** `https://www.telepizza.pt/rodizio-pizza-e-bebida.html`
- **API Pública de Lojas (SFCC):**
  - `GET https://www.telepizza.pt/on/demandware.store/Sites-TelepizzaPT-Site/default/Stores-FindStores?lat=38.725377&long=-9.150086`

#### B. Necessidade de Localização e Concelho de Lisboa
- **Catálogo Nacional Uniforme:** A listagem de promoções e menus em `/promocoes` e `/menus` é pública e universal. Não requer morada nem código postal para consulta de condições e preços.
- **Presença em Lisboa:** 10 lojas ativas no município de Lisboa (Telheiras, Roma, Parque das Nações, Benfica, Almirante Reis, Belém, Campo de Ourique, Lumiar, São Domingos de Benfica, Santa Apolónia).

#### C. Promoções Encontradas e Regras de Negócio
- **Segundas de Massa Mãe (`2ADMMK`):** 10,00€ por pizza média em Massa Mãe (apenas às segundas-feiras).
- **Quartas-feiras Loucas:** 50% de desconto direto sobre pizzas médias, familiares ou king size (apenas às quartas-feiras).
- **1 Pizza Média Descomplicada (`Med595_TK`):** Desde 5,95€ em massa fina ao balcão/take-away.
- **Promoções de Volume:** 2 Pizzas Médias por 9,95€ cada (19,90€ total); 3 Médias por 7,95€ cada (23,85€ Take Away) ou 8,95€ cada (26,85€ Delivery).
- **Promoções 2x1:** 2x1 em Pizzas Médias (`2X1_NC`) e 2x1 em Familiares (`2x1_FAM_NC`).
- **Menus Individuais e Combos:** "Meu Menu" com voucher Staples de 5€ (5,95€ em Take Away; 8,95€ em Domicílio); Menu para 2 (11,95€ / 16,45€); Menu para 4 (18,95€ / 23,95€); Menu para 5 (19,95€ / 24,95€).
- **Rodízio de Pizzas e Bebidas Sem Fim:** 7,95€ (até às 18h) / 8,95€ (após as 18h) em consumo de sala.

#### D. Camada Técnica e Modelo de Dados
- **Tipo de Resposta:** Server-Side Rendering (Salesforce Commerce Cloud) com dupla exposição estruturada:
  1. `<script type="application/ld+json">` contendo `ItemList` Schema.org com SKUs, preços numéricos, moeda e `priceValidUntil`.
  2. Elementos HTML `.offer-tile__wrap` com atributos ricos: `data-id`, `data-promotion-id`, `data-tab-content="delivery,takeaway"`, `data-detail`, `data-img-url`.
- **Campos Disponíveis:** SKU/ID, Nome, Descrição integral de regras, Preço base, Moeda, Canais (Take Away/Delivery), Validade formal (muitas até 31/12/2026), URL da imagem.

#### E. Frequência, Riscos e Dificuldade
- **Frequência de Alteração:** Baixa a Média (campanhas estruturais anuais; parcerias renovadas a cada 4-8 semanas).
- **Dificuldade de Recolha:** Nível 1 / 5 (Muito Baixa).
- **Riscos / Limitações:** Proteção Cloudflare ativa; contudo, clientes HTTP com User-Agent comum recebem `HTTP 200 OK` de imediato. Não requer emulação de navegador nem cookies de sessão.

---

### 3.3. Domino's Pizza Portugal

#### A. Páginas Oficiais Relevantes
- **Domínio Principal e Redirecionamento:** `https://dominos.pt` redireciona para `https://www.dominospizza.pt/`.
- **Homepage:** `https://www.dominospizza.pt/` (4 campanhas âncora em SSR).
- **Página de Menus e Combos:** `https://www.dominospizza.pt/menu/areeiro#Combo`
- **Diretório de Lojas:** `https://www.dominospizza.pt/stores`
- **Endpoint AJAX Público do Frontend:**
  - `POST https://www.dominospizza.pt/ajax/order.php`

#### B. Necessidade de Localização e Concelho de Lisboa
- **Sem exigência de morada:** O catálogo de combos é uniforme a nível nacional.
- **Loja Âncora de Lisboa:** O próprio frontend da marca estabelece a loja do **Areeiro (ID 140)** como predefinição nacional (`perma_st = '140'`). O concelho de Lisboa dispõe de 8 lojas mapeadas.
- **Variação de Canais:**
  - O catálogo devolve 34 promoções ativas em Delivery (`delivery_method: 'D'`) e 34 em Take-away (`delivery_method: 'C'`).
  - O Take-away aplica um desconto sistemático de 1,00€ a 1,50€ em relação ao serviço de entrega.

#### C. Promoções Encontradas e Regras de Negócio
- **Segundas a Dobrar (ID 2434):** 40% de desconto direto em todas as pizzas e tamanhos às segundas-feiras.
- **Menus Almoço (Lunch Break):** Válidos estritamente das 11h00 às 18h00. Sandx + Bebida a 6,95€; Pizza Média a 7,95€; Pizza PAN a 8,95€.
- **Menus Individuais:** Pizza Média desde 9,95€ (Take-away) ou 10,95€ (Entrega).
- **Menus Duplas (2 Pizzas):** Desde 9,50€ cada (Take-away) ou 9,95€ cada (Entrega).
- **Menus Trios (3 Pizzas):** Desde 8,50€ cada (Take-away) ou 8,95€ cada (Entrega).
- **Menus Família (2 Pizzas + 2 Acompanhamentos + Bebida 1,5L):** Desde 22,95€ (Take-away) ou 23,95€ (Entrega).

#### D. Camada Técnica e Modelo de Dados
- **Tipo de Resposta:** JSON puro retornado pelo endpoint `POST /ajax/order.php` com os parâmetros `get_menu=140`, `time=NOW`, `delivery_method=D` ou `C`.
- **Campos Disponíveis:** `id`, `title`, `description`, `promo` (badge visual), `delivery_type`, `terms`, `image_url`, `steps` (produtos elegíveis e tamanhos).
- **Particularidade de Parsing:** O preço numérico vem inserido na string do `title` (ex.: `"MENU FAMÍLIA GRANDES | Desde 28,00€"`), requerendo uma expressão regular determinística simples (`r'(\d+[.,]\d{2})\s*€'`).

#### E. Frequência, Riscos e Dificuldade
- **Frequência de Alteração:** Baixa a Média.
- **Dificuldade de Recolha:** Nível 1 / 5 (Muito Baixa).
- **Riscos / Limitações:** O WAF da Cloudflare bloqueia User-Agents de bibliotecas padrão (ex: `Python-urllib`), mas aceita conexões normais com cabeçalhos padrão de navegador moderno e `X-Requested-With: XMLHttpRequest`.

---

### 3.4. Pizza Hut Portugal

#### A. Páginas Oficiais Relevantes
- **Portal Institucional de Ofertas:** `https://www.pizzahut.pt/ofertas/`
- **Catálogo Transacional de Encomendas:** `https://encomendar.pizzahut.pt/pt/catalogo/promocoes/`
- **Sitemap Direto de Ofertas:** `https://www.pizzahut.pt/ofertas-sitemap.xml`
- **API REST Pública do WordPress:**
  - `GET https://www.pizzahut.pt/wp-json/wp/v2/ofertas?per_page=100`
  - `GET https://www.pizzahut.pt/wp-json/wp/v2/restaurantes`

#### B. Necessidade de Localização e Concelho de Lisboa
- **Sem exigência de morada:** O inventário de promoções é aberto e acessível sem login ou introdução de morada.
- **Restaurantes Aderentes (Filtro Geográfico):** Ao contrário das outras três marcas, cada oferta da Pizza Hut possui uma relação de aderência a restaurantes específicos no HTML da página de detalhe.
- **Mapeamento em Lisboa:** Existem 12 restaurantes da Pizza Hut no concelho de Lisboa.
  - Lojas com entrega própria (`Restelo`, `Parque das Nações`, `General Roçadas`, `Telheiras`, `Ferreira Borges`, `Av. João XXI`, `Benfica`) cobrem as ofertas de delivery.
  - Lojas de centro comercial (`Colombo`, `Vasco da Gama`, `Alameda`) focam-se em consumo de sala e balcão.
  - Campanhas específicas (ex: *Buffet Almoço*) têm aderência hiper-localizada (em Lisboa, apenas `Fontes Pereira de Melo`).

#### C. Promoções Encontradas e Regras de Negócio
- **Rodízio de Pizzas (14,95€ / pessoa):** Consumo ilimitado de fatias + Combi Hut + sobremesa/café em sala.
- **Buffet Almoço com Bebida (9,50€):** Almoço de 2.ª a 6.ª feira das 12:15 às 14:15.
- **Hut Monday (Segundas-feiras):** 50% de desconto em Pizzas Médias e Familiares no domicílio.
- **Hut Days (Quartas-feiras):** 50% de desconto em Stuffed Crust e Cheesy Bites.
- **2x1 (Melhor que uma só duas):** Compra 1 pizza, oferta da 2.ª (com taxa de +1€ no domicílio).
- **Double Stuffed Crust (6,00€ / pessoa em menu para 3 pax):** Menu completo a 24,25€ com entradas e bebida 1,5L.
- **Menu Uno (12,95€):** Pizza Pan individual + 2 Pães de Alho Supremo + Bebida 33cl + 6 Profiteroles.
- **Menu Familiar (24,25€):** Pizza Pan Familiar + 4 Pães de Alho Supremo + Bebida 1,5L.

#### D. Camada Técnica e Modelo de Dados
- **Tipo de Resposta:** Duas etapas determinísticas:
  1. API REST WP-JSON (`/wp-json/wp/v2/ofertas`) para obtenção de metadados, títulos, datas e imagens.
  2. SSR nas páginas `/ofertas/<slug>/` para extrair texto de regras e lista de links para os restaurantes aderentes (`/restaurantes/<slug>/`).
- **Campos Disponíveis:** `id`, `slug`, `title`, `description`, datas de modificação, restaurantes aderentes, termos de acumulação e canais (Sala, Balcão, Domicílio).

#### E. Frequência, Riscos e Dificuldade
- **Frequência de Alteração:** Baixa a Média.
- **Dificuldade de Recolha:** Nível 1.5 / 5 (Baixa).
- **Riscos / Limitações:** O layout em Elementor utiliza classes CSS geradas dinamicamente; por essa razão, a extração deve basear-se nos títulos das secções textuais e nos links dos restaurantes aderentes, em vez de depender de classes de CSS.

---

## 4. Recomendação Fundamentada do Primeiro Adaptador

Recomenda-se formalmente que o **primeiro adaptador a ser implementado seja o da Papa John's Portugal**, seguido sequencialmente por **Telepizza**, **Domino's Pizza** e **Pizza Hut**.

### Justificação da Escolha (Papa John's como MVP Foundation)

1. **Payload JSON Nativo e Tipado:** A API REST pública em `api.papajohns.pt` devolve campos estritamente tipados com valores numéricos separados para preço com desconto (`price`) e preço de referência (`original_price`), eliminando a necessidade de parsers de regex complexos para extrair preços de blocos textuais.
2. **Zero Fricção de Scraping:** A API dispensa totalmente o parsing de HTML, renderização de JavaScript ou gestão de sessões. Três chamadas HTTP simples obtêm todo o catálogo de Lisboa em menos de 100 milissegundos.
3. **Ausência de WAF Agressivo:** A infraestrutura na AWS API Gateway não possui proteção de bloqueio por Cloudflare ou CAPTCHA, apresentando o menor risco de falsos positivos ou bloqueios acidentais.
4. **Isolamento de Lisboa Simplificado:** Os preços e promoções são uniformes e idênticos em todas as lojas de Lisboa, permitindo validar o modelo canónico de dados e o motor de normalização antes de introduzir a lógica de lojas aderentes da Pizza Hut.

### Roteiro Sequencial de Implementação dos Adaptadores
1. **Fase 1 (Pioneiro):** `PapaJohnsAdapter` (Estabelece o contrato de dados canónico e prova de conceito do pipeline).
2. **Fase 2 (JSON-LD & SSR):** `TelepizzaAdapter` (Implementa o parser de Schema.org ItemList e atributos de canais).
3. **Fase 3 (Endpoint AJAX POST):** `DominosAdapter` (Implementa a extração dos 34 combos e extração por regex de preços de strings).
4. **Fase 4 (Multi-step & Aderentes):** `PizzaHutAdapter` (Implementa a resolução relacional de lojas aderentes de Lisboa via WP-JSON e SSR).

---

## 5. Alinhamento com as Restrições de Arquitetura e Engenharia

Em conformidade estrita com os requisitos do projeto, a futura implementação dos coletores e da plataforma respeitará integralmente os seguintes princípios:

### 5.1. Alojamento e Base de Dados com Free-Tier
- O volume total de dados gerado pela agregação das quatro marcas em Lisboa é extremamente reduzido (menos de 150 promoções ativas em simultâneo e menos de 2 MB de payload JSON consolidado).
- Esse dimensionamento encaixa com folga nas quotas gratuitas de plataformas modernas:
  - **Hospedagem Web:** Provisoriamente avaliada em Cloudflare Pages, Vercel ou GitHub Pages (gratuitas para frontends estáticos/JAMstack).
  - **Base de Dados:** Provisoriamente avaliada em Supabase (PostgreSQL free tier de 500 MB), Neon ou Turso (SQLite distribuído gratuito).
  - **Agendamento de Coleta:** Provisoriamente avaliado em GitHub Actions (2.000 minutos/mês gratuitos em repositórios públicos, sendo necessários menos de 15 minutos/mês para 1 execução diária).

### 5.2. Runtime 100% Determinístico e Sem Modelos de IA
- **Proibição Absoluta de IA em Produção:** O *runtime* do Pizza Radar PT não invocará APIs de LLMs (Gemini, OpenAI, Anthropic, etc.).
- **Extração Determinística:** Toda a recolha é feita por chamadas HTTP determinísticas a endpoints e páginas públicas, com validação de schemas estruturados (ex.: Zod ou Pydantic).
- **Ranking e Recomendações Determinísticas:** O cálculo do ranking promocional (ex.: rácio de desconto percentual, preço por pessoa, preço por pizza individual ou menu mais económico) será executado através de fórmulas matemáticas e regras lógicas explícitas, garantindo repetibilidade e testabilidade por testes unitários automatizados.

### 5.3. Portabilidade Arquitetural (Anti Vendor Lock-In)
- Os coletores serão desenhados como classes ou módulos desacoplados que implementam uma interface comum (`PromoAdapterInterface`), devolvendo uma estrutura normalizada agnóstica (`UnifiedPromoSchema`).
- O código do coletor não dependerá de primitivas exclusivas de um único fornecedor cloud, podendo ser executado indiferentemente via CLI local, script em cron num servidor Linux genérico, container Docker ou função serverless.
- Cloudflare Pages, Supabase e GitHub Actions permanecem como hipóteses provisórias sob avaliação, e não decisões definitivas acopladas ao código-fonte.
