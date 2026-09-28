# ADR-002: Arquitetura de Execução, Alojamento, Base de Dados Free-Tier e Publicação de Dados

- **Data:** 2026-09-28
- **Estado:** Aceite
- **Decisores:** Equipa Multiagente Permanente (Project Manager, Orchestrator, Implementer, Reviewer)

## Contexto

Após a consolidação do contrato canónico de dados (`UnifiedPromo`) e da interface de adaptadores na ADR-001 (#7), o projeto necessitava de definir a sua arquitetura global de infraestrutura, alojamento e persistência para o MVP, dando resposta ao Issue #14.

Os requisitos fundamentais eram:
1. **Alojamento Frontend Online:** Solução estável, com CDN global e sem custos mensais.
2. **Base de Dados Relacional Free-Tier Real:** O sistema deve operar sobre uma base de dados relacional para consistência transacional, auditoria e histórico de preços; o uso de ficheiros JSON não pode substituir a decisão de base de dados.
3. **Coletores Python Agendados:** Execução periódica determinística sem custos de infraestrutura.
4. **Publicação Eficiente:** Estratégia que não sobrecarregue a base de dados com o tráfego dos utilizadores finais.
5. **Atualização, Expiração e Histórico:** Regras claras e determinísticas para desativação de campanhas caducadas ou descontinuadas.
6. **Observabilidade e Resiliência:** Tratamento e notificação de falhas sem ferramentas pagas.
7. **Orçamento Zero (0,00 € / mês):** Cumprimento estrito de planos gratuitos reais.
8. **Portabilidade e Plano de Saída:** Código agnóstico de fornecedor, com migração direta sem reescrita de código.
9. **Zero IA em Runtime:** Proibição absoluta de modelos de linguagem em produção.

## Decisão

1. **Alojamento Web:** **Cloudflare Pages**
   - Oferece largura de banda ilimitada, 500 builds por mês, certificados SSL automáticos e distribuição global Anycast. Não impõe restrições não-comerciais restritivas (como o Vercel Hobby).

2. **Base de Dados Canónica:** **Turso (libSQL / SQLite Serverless)**
   - O Turso disponibiliza 5 GB de armazenamento gratuito e 10 milhões de escritas mensais.
   - **Vantagem Crítica sobre o Supabase:** O Turso **não suspende nem pausa a base de dados por inatividade** no plano gratuito (ao contrário do Supabase, que pausa ao fim de 7 dias sem queries SQL).
   - **Zero Lock-in:** O motor utiliza a sintaxe e tipos padrão do SQLite. Em ambiente local e nos testes automatizados, o sistema corre diretamente sobre o módulo nativo `sqlite3` de Python sem dependências externas de rede.
   - Como alternativa e plano de saída para PostgreSQL, o esquema relacional é compatível com Neon e Supabase via abstração de repositório (`PromotionRepository`).

3. **Agendamento de Coletores:** **GitHub Actions**
   - Workflow agendado duas vezes ao dia (10:30 e 17:30 UTC), cobrindo almoço e jantar.
   - Consumo mensal previsto de ~35 minutos, representando menos de 2% do limite de 2.000 minutos do GitHub Free em repositórios privados.

4. **Estratégia de Publicação Híbrida (Base de Dados + Cache Estática CDN):**
   - A base de dados funciona como a Fonte Única da Verdade (*Single Source of Truth*), histórico e auditoria.
   - A cada ciclo de recolha, o pipeline gera um artefacto determinístico `promotions.json` com as ofertas atualmente ativas (`is_active = 1`).
   - O artefacto é publicado na CDN do Cloudflare Pages e consumido pelo frontend web.
   - Os utilizadores beneficiam de carregamento quase instantâneo (<50ms) e a base de dados não sofre pressão de leitura.

5. **Política Determinística de Expiração e Histórico:**
   - Ofertas com data `valid_until` ultrapassada são desativadas (`is_active = 0`).
   - Ofertas ausentes na fonte por 2 sincronizações consecutivas (~24 horas de *grace period*) são desativadas automaticamente.
   - Todas as observações de preços são registadas em `observation_history` para análise histórica.

6. **Observabilidade e Tolerância a Falhas:**
   - Notificações de falha no pipeline via alertas por email do GitHub Actions.
   - Falhas individuais de vendedores (ex.: site em manutenção) não bloqueiam os restantes adaptadores.

## Consequências

### Positivas (Prós)
- **Custo Operacional Totalmente Nulo:** 0,00 €/mês garantido para a escala do MVP.
- **Alta Resiliência e Desempenho:** Separação entre a persistência em BD e o tráfego de leitura via CDN estática.
- **Portabilidade Total:** O coletor pode ser executado localmente via CLI, em cron de servidor Linux, ou em contentores Docker.
- **Auditabilidade e Histórico:** Dados históricos preservados na base de dados para futuras análises de evolução de preços.

### Negativas / Compromissos (Contras / Trade-offs)
- A sincronização periódica (2x/dia) não reflete ofertas flash de duração inferior a algumas horas (compromisso assumido no charter do projeto: atualização periódica, não em tempo real contínuo).

### Riscos Técnicos e Mitigações

1. **Risco:** Alteração unilateral de quotas por parte dos fornecedores gratuitos (Cloudflare, Turso, GitHub).
   - **Mitigação:** Planos de saída documentados para cada componente (SQLite local / VPS gratuita / Vercel / Neon).
2. **Risco:** Falha de conectividade do runner do GitHub Actions com a base de dados Turso.
   - **Mitigação:** Suporte a fallback de persistência em ficheiro local com retentativa na sincronização seguinte.
