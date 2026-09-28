# ADR-001: Contrato Canónico de Dados, Interface de Adaptadores e Arquitetura do Core

- **Data:** 2026-09-28
- **Estado:** Aceite (Revisto com precisão financeira, geográfica e temporal)
- **Decisores:** Equipa Multiagente Permanente (Project Manager, Orchestrator, Implementer, Reviewer)

## Contexto

O Pizza Radar PT tem como objetivo agregar promoções públicas de quatro cadeias de pizzarias no concelho de Lisboa (Domino's Pizza, Pizza Hut, Telepizza e Papa John's). Conforme demonstrado no relatório de viabilidade (#3), cada cadeia disponibiliza dados em formatos díspares (endpoints REST com JSON estruturado, respostas AJAX com cabeçalhos não canónicos, atributos `data-*` em HTML e metadados via WordPress REST API).

Para garantir que o core da aplicação permanece desacoplado, manutenível, determinístico e auditável, foi necessário:
1. Estabelecer um contrato canónico unificado (`UnifiedPromo`) para representar qualquer promoção de pizza de forma homogénea.
2. Definir uma interface de adaptadores (`PromoAdapterInterface`) que isole as peculiaridades de cada fornecedor.
3. Garantir precisão monetária sem erros de arredondamento inerentes a números de vírgula flutuante (IEEE-754).
4. Modelar rigorosamente a aplicabilidade geográfica e por loja em Lisboa, sem presumir disponibilidade universal.
5. Permitir a decomposição do conteúdo da oferta (pizzas, tamanhos e itens acompanhantes), estabelecendo uma regra estrita de não inventar ou estimar silenciosamente dados omissos na fonte.
6. Garantir auditoria temporal com carimbos timezone-aware, distinguindo a validade anunciada pela marca da data de observação pelo coletor e suportando a desativação determinística de campanhas descontinuadas.
7. Respeitar as restrições inegociáveis: zero IA em runtime, compatibilidade com infraestrutura gratuita (free tier) e prevenção de dependência tecnológica (*vendor lock-in*).

## Decisão

1. **Ambiente de Engenharia e Racional da Stack:**
   - Adotou-se **Python 3.12** com tipagem estrita (`dataclasses`, `enum`, `typing`, `slots=True`) e sem dependências externas de runtime (`dependencies = []` no `pyproject.toml`).
   - A biblioteca padrão disponibiliza suporte nativo a serialização (`json`), parsing de URLs (`urllib.parse`), datas timezone-aware (`datetime`) e suíte de testes (`unittest`), executando em frações de milissegundo.

2. **Dinheiro Determinístico (Integer Cents):**
   - Todos os valores monetários são estritamente modelados como cêntimos inteiros (`price_cents: int | None`, `original_price_cents: int | None`).
   - É expressamente proibida a utilização de `float` para preços monetários nos modelos e na validação.
   - Propriedades auxiliares (`price_euros`, `original_price_euros`, `savings_amount_cents`, `savings_amount_euros`) fornecem representação formatada para apresentação, mantendo a integridade aritmética.

3. **Aplicabilidade Geográfica e por Loja (`StoreScope`):**
   - O contrato distingue formalmente três âmbitos de loja através do enum `StoreScope`:
     - `NATIONAL`: Campanha de âmbito nacional anunciada pela marca como válida em todas as unidades.
     - `SPECIFIC_STORES`: Promoção restrita a lojas identificadas explicitamente em `store_ids` ou `store_names`.
     - `UNKNOWN`: A fonte não explicita a abrangência por loja.
   - **Regra Inegociável:** É proibido presumir que uma promoção está disponível em todas as lojas quando a aplicabilidade for desconhecida (`UNKNOWN`). O método `is_store_eligible(store_id)` devolve `None` em casos desconhecidos para que a camada consumidora apresente uma ressalva ao utilizador.

4. **Conteúdo da Promoção e Comparabilidade Estrita:**
   - A estrutura suporta opcionalmente os componentes da oferta através de `OfferComponent` (`category`, `quantity`, `description`, `size`), além de `pizza_count: int | None` e `pizza_size: PizzaSize`.
   - **Proibição de Estimativa Silenciosa:** Se a fonte oficial não fornecer a contagem de pizzas ou os tamanhos, os campos permanecem `None` / `UNKNOWN`. É expressamente proibido inventar valores presumidos.
   - **Flag de Comparabilidade:** A propriedade `is_comparable_for_unit_price` só devolve `True` se `price_cents` e `pizza_count` estiverem comprovadamente presentes. Caso contrário, a oferta é marcada como não comparável para cálculo de preço por pizza (`price_per_pizza_cents is None`), protegendo o ranking contra distorções.

5. **Temporalidade e Ciclo de Vida Timezone-Aware:**
   - `observed_at`: Campo obrigatório que regista o instante exato em que o coletor consultou a fonte, exigindo obrigatoriamente indicação explícita de fuso horário (ex.: `+01:00` ou `Z`). Registos timezone-naive são rejeitados pelo validador.
   - Distinção explícita entre a validade anunciada pela marca (`valid_from`, `valid_until`) e as observações do sistema (`observed_at`, `last_seen_at`).
   - Campo `is_active: bool` para permitir que o pipeline desative deterministicamente promoções que deixem de ser observadas em sincronizações sucessivas.

6. **Interface de Adaptadores (`PromoAdapterInterface`):**
   - Classe abstrata (`ABC`) que padroniza os métodos `vendor` e `fetch_promotions(timeout: float) -> list[UnifiedPromo]`.
   - Inclui o método `validate_and_filter` para assegurar que nenhum adaptador emite dados fora do contrato canónico.
   - Hierarquia de exceções (`AdapterError`, `NetworkError`, `ParseError`, `RateLimitError`).

## Consequências

### Positivas (Prós)
- **Zero Imprecisão Financeira:** A utilização de cêntimos inteiros elimina desvios de arredondamento em cálculos de desconto e ordenação.
- **Transparência Geográfica:** O utilizador é informado se uma promoção é garantida na sua loja ou se a aplicabilidade é desconhecida.
- **Integridade do Ranking:** Ao impedir valores presumidos e assinalar ofertas não comparáveis, o ranking "mais pizza por euro" baseia-se unicamente em factos comprovados.
- **Rastreabilidade Temporal:** Carimbos timezone-aware permitem auditoria precisa e desativação determinística de campanhas caducadas.

### Negativas / Compromissos (Contras / Trade-offs)
- Ofertas publicitárias complexas e difusas (ex.: "Pede um menu e ganha um brinde") não poderão ser comparadas por preço unitário de pizza e ficarão marcadas com `is_comparable_for_unit_price = False`.

### Riscos Técnicos e Mitigações

1. **Risco:** Quebra de contrato por alterações inesperadas no HTML ou nas APIs dos operadores.
   - **Mitigação:** A interface de adaptadores isola cada fonte através de `ParseError` e `NetworkError`. O validador rejeita itens individuais sem interromper o lote completo (`validate_promos`).
2. **Risco:** Omissão de dados essenciais nas fontes públicas (ex.: falta de indicação de preço original ou de lojas aderentes).
   - **Mitigação:** O modelo trata estes campos como opcionais (`None`) e marca a oferta como não comparável, garantindo que o sistema apresenta a oferta ao utilizador com ressalvas explícitas sem gerar rankings enganadores.
3. **Risco:** Discrepância entre os fusos horários dos servidores das marcas e o horário legal de Lisboa.
   - **Mitigação:** Validação obrigatória de timestamps timezone-aware em `observed_at` e `last_seen_at`.
