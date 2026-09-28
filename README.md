# Pizza Radar PT

Agregador de promoções públicas de pizza em Portugal.

## Problema

Encontrar e comparar ofertas e promoções de pizza entre diferentes marcas em Portugal é um processo manual, moroso e fragmentado. Os consumidores precisam de visitar vários websites e aplicações móveis para descobrir quais os descontos, menus especiais ou cupões atualmente em vigor.

## Público-Alvo

Consumidores em Portugal que pretendem encomendar pizza e procuram rapidamente as melhores promoções, ofertas e menus disponíveis, quer para refeições individuais quer para grupos e famílias.

## Âmbito do MVP

O primeiro MVP (Produto Viável Mínimo) foca-se geograficamente no **concelho de Lisboa** (cidade de Lisboa), agregando promoções ativas disponíveis nos canais oficiais das marcas selecionadas através de atualizações periódicas (não em tempo real contínuo), de forma simples, transparente e acessível.

## Vendedores Iniciais

Nesta fase inicial, o radar monitoriza promoções oficiais de quatro cadeias:

1. **Domino's Pizza**
2. **Pizza Hut**
3. **Telepizza**
4. **Papa John's**

## Coisas Fora de Âmbito (Out of Scope)

Para manter o foco no valor essencial e respeitar boas práticas técnicas e operacionais, ficam explicitamente fora do âmbito inicial:

- Outros concelhos da Área Metropolitana de Lisboa e restantes regiões do país (o foco do MVP é estritamente o concelho de Lisboa).
- Atualizações em tempo real contínuo ou streaming de ofertas (o catálogo é atualizado periodicamente).
- Outras cadeias ou pizzarias locais/independentes.
- Realização de encomendas diretas ou integração de checkout (o utilizador é direcionado para o site oficial da marca).
- Acesso a áreas autenticadas, dados privados de clientes ou contorno de mecanismos como CAPTCHA ou proteções anti-bot.
- Aplicações móveis nativas (iOS/Android) durante o MVP.

## Estado Atual do Projeto

O projeto encontra-se na fase de **fundação documental e estruturação inicial**. Ainda não foram definidas frameworks, instaladas dependências ou desenvolvido código de aplicação e scrapers.

## Documentação

Para mais detalhes sobre a organização e regras do projeto:

- [Project Charter](docs/project-charter.md)
- [Learning Log](docs/learning-log.md)
- [Architecture Decision Records (ADRs)](docs/decisions/README.md)
- [Arquitetura de Execução, Alojamento e Persistência](docs/architecture-execution-hosting-persistence.md)
- [Relatório de Viabilidade de Fontes](docs/source-feasibility.md)
- [Fluxo de Trabalho Multiagente](docs/agent-workflow.md)
- [Regras para Agentes e Colaboradores](AGENTS.md)