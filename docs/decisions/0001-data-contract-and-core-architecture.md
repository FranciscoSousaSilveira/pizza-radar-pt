# ADR-001: Contrato Canónico de Dados, Interface de Adaptadores e Arquitetura do Core

- **Data:** 2026-09-28
- **Estado:** Aceite
- **Decisores:** Equipa Multiagente Permanente (Project Manager, Orchestrator, Implementer, Reviewer)

## Contexto

O Pizza Radar PT tem como objetivo agregar promoções públicas de quatro cadeias de pizzarias no concelho de Lisboa (Domino's Pizza, Pizza Hut, Telepizza e Papa John's). Conforme demonstrado no relatório de viabilidade (#3), cada cadeia disponibiliza os seus dados em formatos díspares (endpoints REST com JSON estruturado, respostas AJAX com cabeçalhos não canónicos, atributos `data-*` em HTML e metadados via WordPress REST API).

Para garantir que o core da aplicação permanece desacoplado, manutenível, testável e escalável, foi necessário:
1. Definir uma linguagem e ambiente de execução para o core determinístico.
2. Estabelecer um contrato canónico unificado (`UnifiedPromo`) para representar qualquer promoção de pizza de forma homogénea.
3. Definir uma interface de adaptadores (`PromoAdapterInterface`) que isole as peculiaridades de cada vendedor.
4. Respeitar as restrições inegociáveis do projeto: zero IA em runtime, compatibilidade com infraestrutura gratuita (free tier) e prevenção de dependência tecnológica (*vendor lock-in*).

## Decisão

1. **Ambiente de Engenharia e Racional da Stack:**
   - Adotou-se **Python 3.12** com tipagem estrita (`dataclasses`, `enum`, `typing`, `slots=True`) e sem dependências externas obrigatórias para o contrato canónico e suíte de testes (`unittest`).
   - A ausência de dependências pesadas garante que o core pode ser executado em qualquer ambiente (CLI local, scripts de cron agendados, GitHub Actions, contentores leves ou funções serverless) com tempo de arranque e de teste na ordem dos milissegundos.

2. **Contrato Canónico (`UnifiedPromo`):**
   - Todos os dados promocionais de Lisboa são normalizados num modelo tipado que inclui:
     - Identificação: `id`, `vendor` (enum `Brand`), `title`, `description`.
     - Preço e Desconto: `price`, `original_price`, `discount_percentage`, `discount_type` (enum `DiscountType`).
     - Condições e Validade: `conditions`, `valid_from`, `valid_until`, `days_of_week` (lista de `Weekday`).
     - Canais: `dispatch_methods` (lista de `DispatchMethod`), `target_audience` (enum `TargetAudience`).
     - Metadados: `image_url`, `source_url`, `scraped_at`, `location_scope` (fixado em `"Lisboa"`).
   - O modelo inclui métodos canónicos de serialização bidirecional (`to_dict`, `from_dict`, `to_json`, `from_json`) e propriedades calculadas (`savings_amount`, `computed_discount_percentage`).

3. **Validação Determinística (`validator.py`):**
   - Módulo independente de validação estrita que rejeita inconsistências (preços negativos, desconto fora de [0, 100], preço promocional superior ao original, concelho divergente de Lisboa, URLs e datas malformatadas).

4. **Interface de Adaptadores (`PromoAdapterInterface`):**
   - Classe abstrata (`ABC`) que exige a definição da propriedade `vendor` e a implementação assíncrona/síncrona de `fetch_promotions(timeout: float) -> list[UnifiedPromo]`.
   - Inclui método utilitário `validate_and_filter` para assegurar que qualquer adaptador só emite instâncias válidas.
   - Hierarquia de exceções dedicada (`AdapterError`, `NetworkError`, `ParseError`, `RateLimitError`).

## Consequências

### Positivas (Prós)
- **Desacoplamento Total:** Cada adaptador pode evoluir isoladamente sem afetar o restante sistema.
- **Determinismo e Auditabilidade:** Validações lógicas explícitas sem qualquer dependência de modelos de IA ou serviços externos.
- **Portabilidade:** Funciona de forma agnóstica a sistemas operativos e fornecedores de cloud.
- **Velocidade de Testes:** 25 testes unitários executados em ~0.001s na biblioteca padrão.

### Negativas / Compromissos (Contras / Trade-offs)
- A homogeneização de ofertas pode exigir que campos muito específicos de uma cadeia particular (ex.: passos de configuração de massa da Domino's) sejam condensados no campo `conditions` ou `description`.

### Riscos e Mitigações
- **Risco:** Alteração na estrutura de dados pública de uma das marcas.
- **Mitigação:** A interface de adaptadores prevê o isolamento através de `ParseError` e `NetworkError`, permitindo que um erro num operador não quebre a recolha dos restantes.
