# Configuração do Domínio pizza-radar.pt no Dominios.pt e Cloudflare Pages

Este documento descreve a arquitetura de alojamento gratuito e o procedimento de ligação do domínio próprio **`pizza-radar.pt`** (registado na **Dominios.pt**) à plataforma **Pizza Radar PT**.

---

## 1. Avaliação de Alojamento Gratuito (Custo Operacional: 0,00 €/mês)

A arquitetura do Pizza Radar PT foi desenhada para operar permanentemente sem qualquer custo de infraestrutura:

| Plataforma | Custo | Edge em Lisboa | Limitações Relevantes | Veredito |
| :--- | :--- | :--- | :--- | :--- |
| **Cloudflare Pages** *(Atual)* | **0,00 €** | **Sim (<15ms)** | Largura de banda ilimitada, 500 deploys/mês, CNAME Flattening no Apex (`@`), SSL Universal automático. Sem restrições de monetização futura. | **MELHOR SOLUÇÃO (Adotada)** |
| **Vercel Hobby** | 0,00 € | Sim | Termos de Serviço proíbem expressamente uso comercial. Limite de 100GB/mês de egress. | Rejeitado (risco de termos de uso) |
| **Netlify Free** | 0,00 € | Sim | Limite estrito de 100GB/mês de egress e 300 minutos de build. | Rejeitado (quotas mais restritivas) |
| **GitHub Pages** | 0,00 € | Limitado | Limite estrito de 100GB/mês; CDN genérica sem regras avançadas de edge caching em Lisboa. | Secundário |
| **Render / Fly.io / Railway** | 0,00 € | Não | Free tiers colocam instâncias em suspensão (*cold starts* de 30-50 segundos) ou exigem cartão de crédito. | Rejeitado para frontend |

---

## 2. Estado Atual dos Domínios Personalizados

Os domínios foram registados no projeto **`pizza-radar-pt`** na Cloudflare Pages via API:
- **Domínio Raiz:** `pizza-radar.pt` (ID: `3616096a-b4a4-428d-8ec2-3f002dc344a4`)
- **Subdomínio:** `www.pizza-radar.pt` (ID: `d99912d9-4208-4f4a-9872-879efe99952f`)

---

## 3. Instruções de Configuração na Dominios.pt

### Opção 1: Delegar Nameservers para a Cloudflare (Recomendada — Padrão Ouro)

Esta opção permite que a Cloudflare efetue o **CNAME Flattening** no domínio raiz (`@`), emitindo certificados SSL automáticos tanto para `pizza-radar.pt` como para `www.pizza-radar.pt`, com proteção DDoS Anycast e cache nos servidores de Lisboa.

#### Passo 1 — Adicionar a zona na Cloudflare:
1. Aceder ao painel da Cloudflare ([dash.cloudflare.com](https://dash.cloudflare.com)).
2. Clicar em **"Add a site"** (Adicionar um site) e introduzir `pizza-radar.pt`.
3. Selecionar o plano **Free** (0,00 €).
4. A Cloudflare apresentará os 2 nameservers atribuídos à conta (exemplo: `anna.ns.cloudflare.com` e `bob.ns.cloudflare.com`).

> [!IMPORTANT]
> **Regra Obrigatória para Domínios `.pt`:** A zona **tem de ser criada na Cloudflare ANTES** de alterar os nameservers na Dominios.pt. A entidade reguladora nacional (**DNS.PT / FCCN**) efetua uma verificação técnica prévia em tempo real; se a zona não existir na Cloudflare quando submeter a alteração, a DNS.PT rejeitará a operação com erro de avaliação técnica.

#### Passo 2 — Alterar os Nameservers na Dominios.pt:
1. Iniciar sessão na Área de Cliente da Dominios.pt em [my.dominios.pt](https://my.dominios.pt).
2. No menu superior, ir a **Domínios** -> **Gerir domínio** -> selecionar `pizza-radar.pt`.
3. No menu lateral/gestão, clicar em **Gestão de Nameservers**.
4. Selecionar **"Usar nameservers personalizados"**.
5. Substituir os nameservers atuais (`dns1.host-redirect.com`, etc.) pelos 2 nameservers fornecidos pela Cloudflare:
   - **Nameserver 1:** `<nameserver-1-da-cloudflare>`
   - **Nameserver 2:** `<nameserver-2-da-cloudflare>`
   - *(Deixar os campos 3 e 4 em branco)*
6. Clicar em **"Alterar Nameservers"**.

#### Passo 3 — Confirmar registos DNS na Cloudflare:
Na Cloudflare, no separador **DNS** do site `pizza-radar.pt`, garantir a existência de dois registos CNAME:
- **Tipo:** `CNAME` | **Nome:** `@` | **Destino:** `pizza-radar-pt.pages.dev` | **Proxy:** Ativado (Nuvem Laranja)
- **Tipo:** `CNAME` | **Nome:** `www` | **Destino:** `pizza-radar-pt.pages.dev` | **Proxy:** Ativado (Nuvem Laranja)

---

### Opção 2: Manter Nameservers na Dominios.pt (Configuração Direta)

Caso não pretenda gerir os DNS na Cloudflare:

1. **Configurar o registo CNAME para `www`:**
   - Na Área de Cliente da Dominios.pt -> **Domínios** -> **Gerir domínio** -> **Gestão de DNS da Zona**.
   - Adicionar o registo:
     - **Tipo:** `CNAME`
     - **Nome:** `www`
     - **Destino / Valor:** `pizza-radar-pt.pages.dev.`
2. **Configurar Redirecionamento Web para a Raiz (`pizza-radar.pt`):**
   - Como os nameservers normais não suportam CNAME no Apex (`@`), aceder a:
     **Domínios** -> **Gerir domínio** -> **Ferramentas de Gestão** -> **Redirecionamentos**.
   - Criar redirecionamento:
     - **Origem:** `pizza-radar.pt`
     - **Tipo:** **URL** (redirecionamento HTTP 301). *Nunca escolher FRAME/Mascaramento, pois o iframe bloqueia a API de geolocalização do browser e prejudica a navegação em telemóveis.*
     - **Destino:** `https://www.pizza-radar.pt`
