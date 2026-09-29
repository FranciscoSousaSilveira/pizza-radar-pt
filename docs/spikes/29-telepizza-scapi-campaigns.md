# Spike Report: Investigação Telepizza SCAPI (Issue #29)

**Data:** 2026-09-29  
**Autor:** Antigravity (Pair Programming com Utilizador)  
**Objetivo:** Investigar viabilidade de métodos SCAPI da Salesforce B2C Commerce (`getPromotionsForCampaign` vs `getPromotions`) e descoberta de campanhas.

---

## 1. Investigação de Endpoints SCAPI Shopper Promotions

A documentação oficial da Salesforce B2C Commerce API especifica os seguintes caminhos para Shopper Promotions:
1. **`getPromotions(ids)`**:  
   `GET /pricing/shopper-promotions/v1/organizations/{organizationId}/promotions?siteId={siteId}&ids={promo_ids}`
2. **`getPromotionsForCampaign(campaignId)`**:  
   `GET /pricing/shopper-promotions/v1/organizations/{organizationId}/promotions/campaigns/{campaignId}?siteId={siteId}&currency={currency}`

---

## 2. Testes Empíricos com Token SLAS Guest (PKCE)

### 2.1. Autenticação SLAS
- **Host:** `https://e6dubte9.api.commercecloud.salesforce.com/` (Cloudflare AS13335).
- **Fluxo:** PKCE Guest com `client_id=33caf917-7f3d-4a33-b78e-75424c3e4985` e `site_id=TelepizzaPT`.
- **Acesso no GitHub Actions:** **100% acessível** (Ubuntu, Windows, macOS). Não sofre qualquer bloqueio de IP de datacenter.

### 2.2. Teste do Método `getPromotions(ids)`
- **IDs testados:** `2x1_MedFam`, `3PMENOSTK`, `Med595_TK`, `2porMenos`, `3porMenos`, `1porMenos`, `1PMENOSTK`, `D30_NC`, `55_NC`.
- **Resultado:** **HTTP 200 OK**. Devolve todos os metadados das promoções em JSON estruturado com atributos `c_tpz_*` (dias da semana, entrega/takeaway, regras de ingredientes, títulos, imagens).
- **Inspeção de `campaignId`:** **Nenhum** dos itens devolve qualquer campo `campaignId`, `campaign_id` ou referência a campanhas.

### 2.3. Teste do Método `getPromotionsForCampaign(campaignId)`
- **Path testado:** `GET /pricing/shopper-promotions/v1/organizations/f_ecom_bktv_prd/promotions/campaigns/{campaignId}?siteId=TelepizzaPT&currency=EUR`
- **Identificadores testados:** `promocoes`, `promocoes-pt`, `promotions`, `default`, `TelepizzaPT`, `offers`, `campanhas`, `campanhas-pt`, `takeaway`, `delivery`, `site-promotions`, `telepizza`, `geral`, `global`, `all`, `pizzas`, `menu`, `deals`, `bts`, `bts-pt`, `2x1`, `martes-locos`, `double-tercas`, `quintas`.
- **Resultado:** **HTTP 200 OK** para todos os pedidos, mas devolvendo sempre array vazio `{"data": []}`.
- **Causa Arquitetural:** No Salesforce Commerce Cloud, as promoções da Telepizza estão configuradas como promoções de site gerais sem associação a campanhas com target de grupos de clientes públicos no storefront.

### 2.4. Descoberta de Promoções Ativas na Aplicação Oficial
- Na aplicação web oficial (`app.telepizza.pt/promocoes`), a lista das 20 promoções ativas é emitida dinamicamente num bloco de dados analíticos (`dataLayer` / `view_promotion`):
  - `2x1_MedFam`, `MMINDTSTK`, `MMINDDSTK`, `MMBRGTSTK`, `MMMEDTSTK`, `MMMEDDSTK`, `MMBRGDSTK`, `3PMENOSTK`, `3porMenos`, `2porMenos`, `1PMENOSTK`, `1porMenos`, `Med595_TK`, `8PIZZOLINO`, `2BEBGARX`, `2BEB33K`, `2x1_Gel`, `D30_NC`, `55_NC`, `BUCKETSLK`.
