# Relatório de Viabilidade Técnica de Fontes de Dados — Pizza Radar PT

**Data da Observação:** 28 de Setembro de 2026
**Âmbito Geográfico:** Concelho de Lisboa
**Vendedores Analisados:** Domino's Pizza, Pizza Hut, Telepizza, Papa John's
**Ticket de Referência:** Issue #3 (SPIKE)

---

## 1. Resumo Executivo

Este documento apresenta a investigação técnica sobre a viabilidade de obtenção contínua, pública e determinística dos catálogos promocionais oficiais das quatro principais cadeias de pizzarias com presença no concelho de Lisboa (Portugal).

A investigação foi conduzida exclusivamente sobre superfícies públicas, sem login, sem simulação de transações de compra ou checkout e sem contorno de proteções técnicas (CAPTCHA, WAF ou mecanismos anti-bot), em conformidade estrita com o `AGENTS.md`.

### Principais Conclusões

1. **Viabilidade Técnica Observada:** Todas as 4 marcas disponibilizam informação promocional publicamente acessível de forma determinística sem recurso a autenticação ou necessidade imediata de emulação de navegadores pesados (*headless browsers* como Puppeteer ou Playwright). Contudo, por se tratarem de canais sem garantia de estabilidade contratual, os endpoints e estruturas observados podem sofrer alterações futuras unilaterais por parte dos operadores.
2. **Camadas de Dados Identificadas:** Duas marcas (**Papa John's** e **Domino's Pizza**) utilizam endpoints publicamente acessíveis, sem autenticação, utilizados pelo frontend oficial e sem garantia de estabilidade contratual, retornando corpos JSON; a **Pizza Hut** expõe um endpoint REST WordPress (`wp-json`) combinado com SSR; a **Telepizza** utiliza Server-Side Rendering (Salesforce Commerce Cloud) com metadados estruturados em **JSON-LD Schema.org** e atributos HTML `data-*`.
3. **Localização no Concelho de Lisboa:** Nenhuma das quatro marcas exigiu código postal ou morada para consultar as campanhas e preços na data observada. Nas 4 marcas, as promoções são geridas num catálogo unificado a nível nacional ou mapeadas diretamente por lojas físicas conhecidas do concelho de Lisboa.
4. **Variação por Canal (Take Away vs. Delivery):** É o fator determinante de diferenciação em todas as marcas. As promoções de Take Away/Balcão apresentaram preços consistentemente mais baixos (-1,00€ a -4,00€) face às de Entrega ao Domicílio.
5. **Conformidade Arquitetural:** O processo de extração, normalização e ranking pode operar com custo zero em infraestrutura gratuita (*free-tier*), sem qualquer chamada a modelos de IA no *runtime* de produção e com desenho desacoplado e portável entre ambientes de execução.

---

## 2. Matriz Comparativa de Viabilidade

| Vetor de Análise | Domino's Pizza | Pizza Hut | Telepizza | Papa John's |
| :--- | :--- | :--- | :--- | :--- |
| **Domínio Oficial** | `dominospizza.pt` | `pizzahut.pt` | `telepizza.pt` | `papajohns.pt` |
| **Camada Primária** | Endpoint AJAX do frontend (`ajax/order.php`) | WP REST API (`wp-json`) + SSR | SSR (HTML `data-*` + JSON-LD) | Endpoint REST do frontend (`api.papajohns.pt`) |
| **Estabilidade Contratual** | Sem garantia contratual | Sem garantia contratual | Sem garantia contratual | Sem garantia contratual |
| **Renderização JS Necessária?** | Não | Não | Não | Não |
| **Requisito de Morada/CP?** | Nenhum na consulta pública | Nenhum na consulta pública | Nenhum na consulta pública | Nenhum na consulta pública |
| **Lojas Mapeadas em Lisboa** | 8 lojas (Loja base: Areeiro `140`) | 12 lojas (Restelo, Chiado, etc.) | 10 lojas (Campo Ourique, Roma, etc.) | 3 lojas (Amoreiras, Areeiro, Benfica) |
| **Volume de Ofertas Observado** | 34 combos (D) / 34 combos (C) | 26 ofertas ativas | 22 cartões HTML / 12 no ItemList | 14 ofertas observadas por canal |
| **Diferenciação D/C** | Sim (Take-away -1€ a -1,50€) | Sim (ofertas exclusivas de canal) | Sim (Take-away -2€ a -4€) | Sim (Take-away -3€ a -4€) |
| **Proteção WAF/Anti-Bot** | Cloudflare ativo (requer UA browser e header AJAX) | Cloudflare ativo (passa com UA padrão) | Cloudflare ativo (passa com UA padrão) | AWS API Gateway (sem WAF agressivo na data) |
| **Headers Observados** | `User-Agent`, `X-Requested-With` | `User-Agent` | `User-Agent` | `User-Agent` (`X-PLATFORM: web` recomendado) |
| **Dificuldade Técnica Estimada** | **Baixa** | **Baixa a Média** | **Baixa** | **Muito Baixa** |
| **Prioridade de Implementação** | 3.ª Recomendada | 4.ª Recomendada | 2.ª Recomendada | **1.ª Recomendada (Primeiro Adaptador)** |

---

## 3. Fichas Técnicas Detalhadas por Vendedor

### 3.1. Papa John's Portugal

#### A. Páginas Oficiais Relevantes
- **Portal Principal:** `https://www.papajohns.pt`
- **Hub de Promoções:** `https://www.papajohns.pt/promocoes/`
- **Páginas Individuais:** `https://www.papajohns.pt/promocoes/duo-bestial/`, `super-john/`, `trio-bestial/`, `papa-as-3as/`
- **Lojas de Lisboa:** `https://www.papajohns.pt/lojas/lisboa/` (Amoreiras - ID 2, Areeiro - ID 13, Benfica - ID 3)
- **Endpoints de Rede:**
  - `GET https://api.papajohns.pt/v1/stores?latitude=38.7223&longitude=-9.1393`
  - `GET https://api.papajohns.pt/v1/offers/promotions?store_id={id}&dispatch_method={pj_delivery|in_store}`
  - `GET https://api.papajohns.pt/v1/offers/{offer_id}?store_id={id}`
  *Natureza:* Endpoint publicamente acessível, sem autenticação, utilizado pelo frontend oficial e sem garantia de estabilidade contratual.

#### B. Necessidade de Localização e Concelho de Lisboa
- **Sem morada ou código postal:** O acesso ao catálogo não exigiu autenticação nem inserção de morada no momento do teste.
- **Amostra de Lojas no Concelho de Lisboa:** Foram consultadas as 3 lojas do concelho de Lisboa (Amoreiras - ID 2, Areeiro - ID 13, Benfica - ID 3). Na data da observação (2026-09-28), cada uma destas 3 lojas devolveu exatamente 14 ofertas por canal e payloads idênticos entre si por modalidade de serviço. Esta paridade reflete uma observação empírica válida da amostra, não devendo ser assumida como garantia contratual permanente de paridade futura.
- **Canais:** A diferenciação verificada ocorre na modalidade de serviço:
  - `in_store` (Take Away / Balcão): ofertas com preços inferiores (ex.: Duo Bestial a 17,98€; pizza individual a 7,99€).
  - `pj_delivery` (Entrega ao Domicílio): preço superior (ex.: Duo Bestial a 20,98€; Party Combo a 59,92€).

#### C. Promoções Encontradas e Regras de Negócio (Amostra de 2026-09-28)
- **Duo Bestial (ID 223):** 2 Pizzas Médias à escolha por 17,98€ (Take Away) ou 20,98€ (Delivery).
- **Trio Bestial (ID 200):** 3 Pizzas Médias por 23,97€ (Take Away) ou 25,47€ (Delivery).
- **Super John (ID 177):** 1 Pizza Média (3 ing.) + 1 Entrada + 1 Bebida 500ml por 9,99€ (Take Away) ou 13,99€ (Delivery).
- **O PAPITO Menu Individual (ID 222):** 1 Pizza Individual + 1 Entrada + 1 Bebida 500ml por 6,99€ (Take Away) ou 10,99€ (Delivery).
- **Papa às 3ªs:** Pizza média a 7,50€ na compra de pelo menos duas pizzas (15,00€ total), exclusivamente às terças-feiras.
- **Taxas e Pedidos Mínimos:** Pedido mínimo em delivery observado de 12,95€ e taxa fixa de entrega de 1,99€.

#### D. Camada Técnica e Modelo de Dados
- **Tipo de Resposta:** JSON estruturado via API REST.
- **Campos Disponíveis:** `id`, `name`, `description`, `price`, `original_price`, `dispatch_method`, `availability` (dias da semana), `start_datetime`, `end_datetime`, `pictures` (URLs CDN em WebP), `offer_groups` (produtos e diferenciais de preço).
- **Cabeçalhos:** O cabeçalho `X-PLATFORM: web` é utilizado e recomendado pelo frontend oficial da marca. No entanto, testes empíricos efetuados em 2026-09-28 demonstraram que um pedido com `User-Agent` de navegador comum, mas sem o cabeçalho `X-PLATFORM: web`, devolveu igualmente `HTTP 200 OK`. Recomenda-se o envio deste header por boas práticas de simulação do tráfego do frontend oficial, mas não está comprovado que seja estritamente mandatório pelo gateway.

#### E. Frequência, Riscos e Dificuldade
- **Frequência de Alteração:** Baixa (ciclos sazonais mensais e campanhas âncora duradouras).
- **Dificuldade de Recolha:** Muito Baixa no estado atual.
- **Riscos e Limitações:** Ausência de estabilidade formal da API privada do frontend; a marca pode alterar rotas, exigir tokens temporários ou introduzir WAF a qualquer momento.

---

### 3.2. Telepizza Portugal

#### A. Páginas Oficiais Relevantes
- **Hub de Promoções:** `https://www.telepizza.pt/promocoes`
- **Hub de Menus:** `https://www.telepizza.pt/menus`
- **Condições Legais:** `https://www.telepizza.pt/condicoes-promocionais.html`
- **Rodízio:** `https://www.telepizza.pt/rodizio-pizza-e-bebida.html`
- **Endpoint de Lojas (SFCC):**
  - `GET https://www.telepizza.pt/on/demandware.store/Sites-TelepizzaPT-Site/default/Stores-FindStores?lat=38.725377&long=-9.150086`
  *Natureza:* Endpoint publicamente acessível, sem autenticação, utilizado pelo frontend oficial e sem garantia de estabilidade contratual.

#### B. Necessidade de Localização e Concelho de Lisboa
- **Catálogo Nacional Uniforme:** A listagem de promoções e menus em `/promocoes` e `/menus` é pública e universal, não exigindo morada nem código postal para consulta de condições e preços.
- **Presença em Lisboa:** 10 lojas ativas identificadas no município de Lisboa através do endpoint SFCC de lojas (Telheiras, Roma, Parque das Nações, Benfica, Almirante Reis, Belém, Campo de Ourique, Lumiar, São Domingos de Benfica, Santa Apolónia).

#### C. Promoções Encontradas e Regras de Negócio (Amostra de 2026-09-28)
- **Segundas de Massa Mãe (`2ADMMK`):** 10,00€ por pizza média em Massa Mãe (apenas às segundas-feiras).
- **Quartas-feiras Loucas:** 50% de desconto direto sobre pizzas médias, familiares ou king size (apenas às quartas-feiras).
- **1 Pizza Média Descomplicada (`Med595_TK`):** Desde 5,95€ em massa fina ao balcão/take-away.
- **Promoções de Volume:** 2 Pizzas Médias por 9,95€ cada (19,90€ total); 3 Médias por 7,95€ cada (23,85€ Take Away) ou 8,95€ cada (26,85€ Delivery).
- **Promoções 2x1:** 2x1 em Pizzas Médias (`2X1_NC`) e 2x1 em Familiares (`2x1_FAM_NC`).
- **Menus Individuais e Combos:** "Meu Menu" com voucher Staples de 5€ (5,95€ em Take Away; 8,95€ em Domicílio); Menu para 2 (11,95€ / 16,45€); Menu para 4 (18,95€ / 23,95€); Menu para 5 (19,95€ / 24,95€).
- **Rodízio de Pizzas e Bebidas Sem Fim:** 7,95€ (até às 18h) / 8,95€ (após as 18h) em consumo de sala.

#### D. Camada Técnica e Modelo de Dados
- **Tipo de Resposta:** Server-Side Rendering (Salesforce Commerce Cloud).
- **Estrutura dos Dados e Cobertura:**
  - Na página `/promocoes`, foram observados **22 cartões HTML** com a classe `.offer-tile__wrap.promo-card-item`. Cada cartão contém atributos semânticos completos: `data-id`, `data-promotion-id`, `data-tab-content="delivery,takeaway"`, `data-detail`, `data-name`, `data-img-url`.
  - Simultaneamente, existe um bloco JSON-LD `<script type="application/ld+json">` com raiz `@graph`. No momento da validação (2026-09-28), dentro deste grafo foi identificado um elemento do tipo `ItemList` com **12 elementos** (`itemListElement`).
  - **Aviso Importante de Implementação:** O número de cartões HTML (22) difere do número de itens no `ItemList` (12). Não é possível afirmar sem evidência adicional que todas as 22 promoções estejam cobertas pelo JSON-LD. O futuro adaptador deve utilizar a extração baseada nos atributos `data-*` do DOM como fonte primária ou mais abrangente, recorrendo ao JSON-LD como complemento quando disponível.
- **Campos Disponíveis:** SKU/ID, Nome, Descrição integral de regras, Preço base, Moeda, Canais (Take Away/Delivery), Validade formal, URL da imagem.

#### E. Frequência, Riscos e Dificuldade
- **Frequência de Alteração:** Baixa a Média.
- **Dificuldade de Recolha:** Baixa.
- **Riscos e Limitações:** Presença de CDN/WAF Cloudflare. Embora chamadas com User-Agent padrão passem sem desafio JS no momento do teste, disparos excessivos podem acionar limites de tráfego.

---

### 3.3. Domino's Pizza Portugal

#### A. Páginas Oficiais Relevantes
- **Domínio Principal e Redirecionamento:** `https://dominos.pt` redireciona para `https://www.dominospizza.pt/`.
- **Homepage:** `https://www.dominospizza.pt/` (4 campanhas em destaque no HTML).
- **Página de Menus e Combos:** `https://www.dominospizza.pt/menu/areeiro#Combo`
- **Diretório de Lojas:** `https://www.dominospizza.pt/stores`
- **Endpoint de Dados do Frontend:**
  - `POST https://www.dominospizza.pt/ajax/order.php`
  *Natureza:* Endpoint publicamente acessível, sem autenticação, utilizado pelo frontend oficial e sem garantia de estabilidade contratual.

#### B. Necessidade de Localização e Concelho de Lisboa
- **Sem exigência de morada:** O catálogo de combos é uniforme a nível nacional.
- **Loja de Referência em Lisboa:** O frontend define a loja do **Areeiro (ID 140)** como predefinição nacional (`perma_st = '140'`). O concelho de Lisboa dispõe de 8 lojas mapeadas.
- **Variação de Canais:**
  - O catálogo devolve 34 promoções ativas em Delivery (`delivery_method: 'D'`) e 34 em Take-away (`delivery_method: 'C'`).
  - O Take-away aplica um desconto sistemático de 1,00€ a 1,50€ face à entrega ao domicílio.

#### C. Promoções Encontradas e Regras de Negócio (Amostra de 2026-09-28)
- **Segundas a Dobrar (ID 2434):** 40% de desconto direto em todas as pizzas e tamanhos às segundas-feiras.
- **Menus Almoço (Lunch Break):** Válidos estritamente das 11h00 às 18h00. Sandx + Bebida a 6,95€; Pizza Média a 7,95€; Pizza PAN a 8,95€.
- **Menus Individuais:** Pizza Média desde 9,95€ (Take-away) ou 10,95€ (Entrega).
- **Menus Duplas (2 Pizzas):** Desde 9,50€ cada (Take-away) ou 9,95€ cada (Entrega).
- **Menus Trios (3 Pizzas):** Desde 8,50€ cada (Take-away) ou 8,95€ cada (Entrega).
- **Menus Família (2 Pizzas + 2 Acompanhamentos + Bebida 1,5L):** Desde 22,95€ (Take-away) ou 23,95€ (Entrega).

#### D. Camada Técnica e Modelo de Dados
- **Tipo de Resposta e Cabeçalho:** O endpoint `POST /ajax/order.php` devolve um corpo JSON perfeitamente parseável, mas com cabeçalho `Content-Type: text/html; charset=UTF-8`.
- **Aviso Importante de Implementação:** O futuro adaptador não poderá confiar no cabeçalho `Content-Type` para a desserialização automática, tendo obrigatoriamente de efetuar a validação e o parse explícito do corpo da resposta como JSON.
- **Campos Disponíveis:** `id`, `title`, `description`, `promo` (badge visual), `delivery_type`, `terms`, `image_url`, `steps` (produtos elegíveis e tamanhos).
- **Particularidade de Parsing:** O preço numérico surge inserido na string do campo `title` (ex.: `"MENU FAMÍLIA GRANDES | Desde 28,00€"`), requerendo uma expressão regular determinística (`r'(\d+[.,]\d{2})\s*€'`).

#### E. Frequência, Riscos e Dificuldade
- **Frequência de Alteração:** Baixa a Média.
- **Dificuldade de Recolha:** Baixa.
- **Riscos e Limitações:** O WAF da Cloudflare bloqueia User-Agents de script genérico (ex.: `Python-urllib`), mas aceitou conexões normais com cabeçalhos padrão de navegador moderno e `X-Requested-With: XMLHttpRequest` na data observada.

---

### 3.4. Pizza Hut Portugal

#### A. Páginas Oficiais Relevantes
- **Portal Institucional de Ofertas:** `https://www.pizzahut.pt/ofertas/`
- **Catálogo Transacional de Encomendas:** `https://encomendar.pizzahut.pt/pt/catalogo/promocoes/`
- **Sitemap Direto de Ofertas:** `https://www.pizzahut.pt/ofertas-sitemap.xml`
- **Endpoint WordPress REST API:**
  - `GET https://www.pizzahut.pt/wp-json/wp/v2/ofertas?per_page=100`
  - `GET https://www.pizzahut.pt/wp-json/wp/v2/restaurantes`
  *Natureza:* Endpoint publicamente acessível, sem autenticação, utilizado pelo frontend oficial e sem garantia de estabilidade contratual.

#### B. Necessidade de Localização e Concelho de Lisboa
- **Sem exigência de morada:** O inventário de promoções é aberto e acessível sem login ou introdução de morada.
- **Restaurantes Aderentes (Filtro Geográfico):** Cada oferta da Pizza Hut possui uma relação de aderência a restaurantes específicos no HTML da página de detalhe.
- **Mapeamento em Lisboa:** Existem 12 restaurantes catalogados no concelho de Lisboa.
  - Lojas com entrega própria (`Restelo`, `Parque das Nações`, `General Roçadas`, `Telheiras`, `Ferreira Borges`, `Av. João XXI`, `Benfica`) cobrem as ofertas de delivery.
  - Lojas de centro comercial (`Colombo`, `Vasco da Gama`, `Alameda`) focam-se em consumo de sala e balcão.
  - Campanhas específicas (ex: *Buffet Almoço*) têm aderência restrita (em Lisboa, apenas `Fontes Pereira de Melo`).

#### C. Promoções Encontradas e Regras de Negócio (Amostra de 2026-09-28)
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
  1. Endpoint WP-JSON (`/wp-json/wp/v2/ofertas`) para obtenção de metadados, títulos, datas e imagens.
  2. SSR nas páginas `/ofertas/<slug>/` para extrair texto de regras e lista de links para os restaurantes aderentes (`/restaurantes/<slug>/`).
- **Campos Disponíveis:** `id`, `slug`, `title`, `description`, datas de modificação, restaurantes aderentes, termos de acumulação e canais (Sala, Balcão, Domicílio).

#### E. Frequência, Riscos e Dificuldade
- **Frequência de Alteração:** Baixa a Média.
- **Dificuldade de Recolha:** Baixa a Média.
- **Riscos e Limitações:** O layout em Elementor utiliza classes CSS geradas dinamicamente; por essa razão, a extração deve basear-se nos títulos das secções textuais e nos links dos restaurantes aderentes, em vez de depender de classes de CSS.

---

## 4. Evidência e Reprodutibilidade

Esta secção documenta os parâmetros de teste e as observações empíricas realizadas em 2026-09-28 para garantir a auditabilidade técnica das fontes:

### 4.1. Papa John's Portugal
- **Data/Hora da Observação:** 2026-09-28 ~16:07 UTC
- **URL Testado:** `https://api.papajohns.pt/v1/offers/promotions?store_id=2&dispatch_method=in_store`
- **Método HTTP:** `GET`
- **Headers Utilizados:** `User-Agent: Mozilla/5.0` (sem header `X-PLATFORM`)
- **Status HTTP:** `200 OK`
- **Content-Type:** `application/json; charset=utf-8`
- **Contagem Observada:** 14 ofertas no array raiz
- **Estrutura / Chaves Principais:** `id`, `name`, `description`, `price`, `original_price`, `dispatch_method`, `availability`, `start_datetime`, `end_datetime`, `pictures`
- **Limitações da Amostra:** Teste realizado numa única data; as 14 ofertas observadas em Lisboa podem variar noutros dias da semana (ex.: terças-feiras para a promoção semanal) ou conforme a loja e modalidade.

### 4.2. Domino's Pizza Portugal
- **Data/Hora da Observação:** 2026-09-28 ~16:07 UTC
- **URL Testado:** `https://www.dominospizza.pt/ajax/order.php`
- **Método HTTP:** `POST`
- **Headers Utilizados:** `User-Agent: Mozilla/5.0`, `X-Requested-With: XMLHttpRequest`, `Content-Type: application/x-www-form-urlencoded`
- **Payload Enviado:** `get_menu=140&time=NOW&delivery_method=D`
- **Status HTTP:** `200 OK`
- **Content-Type:** `text/html; charset=UTF-8`
- **Contagem Observada:** 34 combos dentro de `combos.data`
- **Estrutura / Chaves Principais:** Raiz com `combos.data[]` contendo `id`, `title`, `description`, `promo`, `delivery_type`, `terms`, `image_url`, `steps`
- **Limitações da Amostra:** O endpoint devolve `Content-Type: text/html` apesar do corpo ser JSON; depende da loja 140 (Areeiro) como referência inicial para Lisboa.

### 4.3. Telepizza Portugal
- **Data/Hora da Observação:** 2026-09-28 ~16:07 UTC
- **URL Testado:** `https://www.telepizza.pt/promocoes`
- **Método HTTP:** `GET`
- **Headers Utilizados:** `User-Agent: Mozilla/5.0`
- **Status HTTP:** `200 OK`
- **Content-Type:** `text/html; charset=UTF-8`
- **Contagem Observada:** 22 cartões `.offer-tile__wrap` no DOM HTML; 12 elementos no `ItemList` do grafo `@graph` JSON-LD
- **Estrutura / Chaves Principais:** Atributos DOM `data-id`, `data-tab-content`, `data-detail`, `data-name`; JSON-LD `@graph[].itemListElement[].item` com `sku`, `name`, `offers.price`
- **Limitações da Amostra:** Divergência quantitativa entre o número de cartões visuais (22) e os elementos serializados no JSON-LD (12). Requer extração no DOM para cobertura integral.

### 4.4. Pizza Hut Portugal
- **Data/Hora da Observação:** 2026-09-28 ~16:07 UTC
- **URL Testado:** `https://www.pizzahut.pt/wp-json/wp/v2/ofertas?per_page=100`
- **Método HTTP:** `GET`
- **Headers Utilizados:** `User-Agent: Mozilla/5.0`
- **Status HTTP:** `200 OK`
- **Content-Type:** `application/json; charset=UTF-8`
- **Contagem Observada:** 26 ofertas no array raiz (`X-WP-Total: 26`)
- **Estrutura / Chaves Principais:** `id`, `slug`, `title.rendered`, `modified`, `yoast_head_json.description`, `yoast_head_json.og_image`
- **Limitações da Amostra:** O endpoint REST fornece apenas metadados; as regras contratuais e a lista de lojas aderentes exigem a leitura subsequente das páginas HTML individuais em `pizzahut.pt/ofertas/<slug>/`.

---

## 5. Recomendação Fundamentada do Primeiro Adaptador

Recomenda-se formalmente que o **primeiro adaptador a ser implementado seja o da Papa John's Portugal** (`PapaJohnsAdapter`), seguido sequencialmente por **Telepizza**, **Domino's Pizza** e **Pizza Hut**.

### Justificação da Escolha

1. **Payload JSON Nativo e Tipado:** O endpoint devolve campos estruturados com valores numéricos separados para preço de venda (`price`) e preço de referência (`original_price`), reduzindo o risco de erro em expressões regulares textuais na fase inicial de desenho do modelo canónico.
2. **Baixo Atrito Técnico Observado:** O endpoint responde diretamente com o catálogo sem necessidade de parsing complexo de marcação HTML nem de múltiplas etapas relacionais de resolução.
3. **Ausência de Desafios WAF no Momento do Teste:** Na data de observação, a infraestrutura da AWS API Gateway não apresentou bloqueios de Cloudflare ou desafios CAPTCHA.
4. **Isolamento de Lisboa Simplificado:** A consistência de dados observada entre as lojas do concelho de Lisboa permite estabelecer e validar a estrutura do `UnifiedPromoSchema` antes de introduzir a lógica relacional de lojas aderentes necessária para a Pizza Hut.

### Roteiro Sequencial Proposto
1. **Fase 1 (Pioneiro):** `PapaJohnsAdapter` (Estabelece o contrato canónico de dados e valida o pipeline).
2. **Fase 2 (DOM & JSON-LD):** `TelepizzaAdapter` (Implementa o parser de atributos HTML `data-*` e enriquece com JSON-LD).
3. **Fase 3 (Endpoint AJAX POST):** `DominosAdapter` (Implementa o parse explícito do corpo JSON com cabeçalho text/html e regex de preços).
4. **Fase 4 (Multi-step & Aderentes):** `PizzaHutAdapter` (Implementa a resolução em duas fases com filtro das 12 lojas de Lisboa).

---

## 6. Alinhamento com as Restrições de Arquitetura e Engenharia

### 6.1. Alojamento e Base de Dados com Free-Tier
- O volume total de dados gerado pela agregação das quatro marcas em Lisboa é reduzido (amostra estimada em menos de 150 promoções ativas em simultâneo e menos de 2 MB de payload consolidado).
- Esse dimensionamento enquadra-se nas quotas gratuitas de plataformas modernas:
  - **Hospedagem Web:** Provisoriamente avaliada em Cloudflare Pages, Vercel ou GitHub Pages (opções gratuitas para frontends estáticos/JAMstack).
  - **Base de Dados:** Provisoriamente avaliada em Supabase (PostgreSQL), Neon ou Turso (SQLite distribuído), que oferecem planos gratuitos.
  - **Agendamento de Coleta:** Relativamente ao GitHub Actions, os *runners* padrão são gratuitos para repositórios públicos, enquanto para repositórios privados o plano GitHub Free disponibiliza uma quota de 2.000 minutos mensais. Uma vez que este repositório se encontra atualmente privado, a viabilidade dependerá do consumo real do processo, devendo a estimativa de consumo ser apurada após a implementação de um *benchmark* real do tempo de execução dos adaptadores.

### 6.2. Runtime Determinístico e Sem Modelos de IA
- **Proibição de IA em Produção:** O *runtime* do Pizza Radar PT não invocará APIs de LLMs (Gemini, OpenAI, Anthropic, etc.).
- **Extração Determinística:** Toda a recolha é efetuada por chamadas HTTP determinísticas a endpoints e páginas públicas, com validação de esquemas tipados (ex.: Zod ou Pydantic).
- **Ranking e Recomendações Determinísticas:** O cálculo do ranking promocional (ex.: rácio de desconto percentual, preço por pessoa, preço por pizza individual) será executado através de fórmulas matemáticas e regras lógicas explícitas, garantindo repetibilidade e testabilidade por testes unitários automatizados.

### 6.3. Portabilidade Arquitetural (Prevenção de Vendor Lock-In)
- Os adaptadores serão desenvolvidos como módulos desacoplados sob uma interface comum (`PromoAdapterInterface`), devolvendo um modelo unificado (`UnifiedPromoSchema`).
- O código do coletor não dependerá de primitivas exclusivas de um único fornecedor de nuvem, podendo ser executado indiferentemente via CLI local, script agendado em cron num servidor Linux genérico, contentor Docker ou função serverless.
- Cloudflare Pages, Supabase e GitHub Actions permanecem como hipóteses provisórias sob avaliação, e não como decisões técnicas fechadas ou acopladas ao código-fonte.

---

## 7. Registo da Auditoria e Validação Independente

Em conformidade com o fluxo de trabalho, o relatório foi submetido a auditoria independente antes da submissão da Pull Request. Segue o registo dos critérios verificados e das evidências auditadas:

| Item da Checklist de Auditoria | Estado | Evidências e Notas da Verificação |
| :--- | :--- | :--- |
| **1. Cobertura das 4 marcas em Lisboa** | Conforme | Mapeadas lojas físicas no concelho de Lisboa: Domino's (8 lojas, Areeiro 140 base), Pizza Hut (12 lojas), Telepizza (10 lojas), Papa John's (3 lojas). |
| **2. Tópicos obrigatórios por marca** | Conforme | Documentados URLs oficiais, requisitos de localização, campanhas e regras, tecnologia subjacente, campos, periodicidade, riscos e evidências empíricas. |
| **3. Natureza dos endpoints documentada** | Conforme | Formulados rigorosamente como "endpoints publicamente acessíveis, sem autenticação, utilizados pelo frontend oficial e sem garantia de estabilidade contratual". |
| **4. Validação de particularidades de rede** | Conforme | Papa John's: header `X-PLATFORM: web` não obrigatório no teste; Domino's: `Content-Type: text/html` com corpo JSON; Telepizza: 22 cartões HTML vs. 12 itens no JSON-LD. |
| **5. Recomendação fundamentada do 1.º adaptador** | Conforme | Recomendação formal da Papa John's com justificação técnica (JSON tipado, sem regex no preço, baixa fricção) e roteiro sequencial subsequente. |
| **6. Proibição de IA em Runtime** | Conforme | Registada na secção 6.2 a proibição absoluta de chamadas a LLMs em runtime de produção, garantindo determinismo e testabilidade. |
| **7. Free-Tier e Portabilidade** | Conforme | Documentada a compatibilidade com opções gratuitas e distinção das regras de minutos de GitHub Actions para repositórios privados. |
| **8. Sem código ou dependências prematuras** | Conforme | Confirmada a ausência de ficheiros de código de aplicação, scrapers ou dependências no repositório. |
| **9. Conformidade com AGENTS.md e sem segredos** | Conforme | Trabalho em branch semântica, apenas dados públicos sem login/CAPTCHA e ausência total de credenciais ou segredos. |

---

## 8. Documentos Relacionados

- [Índice Central da Base de Conhecimento](README.md)
- [Estado Atual do Projeto](current-state.md)
- [Project Charter](project-charter.md)
- [ADR-001: Contrato Canónico de Dados, Interface de Adaptadores e Core](decisions/0001-data-contract-and-core-architecture.md)
- [Learning Log](learning-log.md)
