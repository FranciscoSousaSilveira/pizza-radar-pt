# Project Charter — Pizza Radar PT

## 1. Visão e Propósito

O **Pizza Radar PT** tem como objetivo centralizar e simplificar a consulta de promoções públicas de pizza em Portugal, oferecendo uma forma rápida, neutra e fiável para os consumidores tomarem decisões informadas sobre onde e o que encomendar.

## 2. Problema e Proposta de Valor

- **Problema:** Fragmentação da informação de ofertas promocionais entre múltiplos operadores no mercado português. Cada cadeia mantém campanhas próprias (dias temáticos, cupões, menus de grupo) com formatos distintos e dispersos.
- **Proposta de Valor:** Uma plataforma unificada e intuitiva que apresenta as campanhas ativas com atualização periódica e fiável (não em tempo real), poupando tempo e dinheiro ao consumidor.

## 3. Âmbito do MVP

O Produto Viável Mínimo (MVP) estabelece uma base sólida com limites bem definidos:
- **Localização:** Concelho de Lisboa (cidade de Lisboa; outros concelhos da Área Metropolitana de Lisboa ficam fora do âmbito inicial).
- **Vendedores Iniciais:**
  1. Domino's Pizza
  2. Pizza Hut
  3. Telepizza
  4. Papa John's
- **Fontes de Dados:** Apenas páginas públicas e oficiais de promoções e campanhas.
- **Frequência de Atualização:** Atualizações periódicas regulares (não contínuas / não em tempo real).

## 4. Fora de Âmbito

- Expansão geográfica fora do concelho de Lisboa (restante Área Metropolitana de Lisboa e outras regiões do país neste momento).
- Atualizações em tempo real contínuo ou streaming de dados (a agregação opera com sincronização periódica).
- Outras marcas ou estabelecimentos independentes.
- Intermediação de pagamentos ou checkout interno.
- Campanhas personalizadas baseadas em histórico ou fidelização privada com login.
- Contorno de qualquer proteção técnica (CAPTCHA, logins ou restrições anti-bot).

## 5. Princípios de Engenharia e Ética

- **Transparência:** Indicar sempre a origem dos dados e direcionar o consumidor para os canais oficiais dos vendedores.
- **Respeito pelas Plataformas:** Consulta ética de informação exclusivamente pública, respeitando rate limits e a disponibilidade das plataformas oficiais.
- **Simplicidade:** Soluções leves, pragmáticas e com o menor overhead técnico possível antes de escalar.
- **Segurança:** Nenhuma credencial ou segredo comitada no repositório.

## 6. Utilizadores-Alvo

- Consumidores no concelho de Lisboa à procura de refeições rápidas e económicas.
- Grupos, famílias ou estudantes a organizar jantares partilhados.

## 7. Critérios de Sucesso do MVP

1. Catálogo com atualização periódica e fiável das promoções públicas dos quatro vendedores no concelho de Lisboa.
2. Interface simples e navegável.
3. Manutenção sustentável e processo de recolha de dados documentado e robusto.

---

## 8. Documentos Relacionados

- [Índice Central da Base de Conhecimento](README.md)
- [Estado Atual do Projeto](current-state.md)
- [Relatório de Viabilidade de Fontes](source-feasibility.md)
- [Architecture Decision Records (ADRs)](decisions/README.md)
- [Regras para Agentes e Colaboradores](../AGENTS.md)
