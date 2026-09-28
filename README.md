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

Para consultar o estado vivo do repositório, decisões ativas, tickets em curso e próximos marcos, consulta o documento canónico:
👉 **[docs/current-state.md](docs/current-state.md)**

## Documentação e Base de Conhecimento

A documentação do projeto está estruturada como uma base de conhecimento navegável, compatível com o GitHub e pronta a ser aberta como um **Vault do Obsidian** (através de links relativos padrão em Markdown):

- **[docs/README.md](docs/README.md)** — **Índice Central da Base de Conhecimento**
- [Estado Atual do Projeto](docs/current-state.md)
- [Project Charter](docs/project-charter.md)
- [Relatório de Viabilidade de Fontes](docs/source-feasibility.md)
- [Architecture Decision Records (ADRs)](docs/decisions/README.md)
- [Arquitetura de Execução, Alojamento e Persistência](docs/architecture-execution-hosting-persistence.md)
- [Fluxo de Trabalho Multiagente](docs/agent-workflow.md)
- [Learning Log](docs/learning-log.md)
- [Regras para Agentes e Colaboradores](AGENTS.md)
