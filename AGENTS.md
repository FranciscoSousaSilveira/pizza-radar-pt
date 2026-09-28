# Regras para Agentes e Colaboradores — Pizza Radar PT

Este documento estabelece as diretrizes de trabalho obrigatórias, a composição da equipa multiagente permanente e o ciclo de vida operacional para agentes e colaboradores no repositório **Pizza Radar PT**.

---

## 1. Equipa Multiagente Permanente

O projeto dispõe de papéis especializados com definições formais localizadas em `.agents/agents/`:

1. **`project-manager`**:
   - Converte objetivos de negócio em tickets acionáveis com critérios de aceitação, dependências e prioridades.
   - Gere o quadro do GitHub Project (`Pizza-radar-project`).
   - Não implementa código nem instala dependências.
2. **`orchestrator`**:
   - Atua exclusivamente sobre tickets no estado `Ready`.
   - Coordena a alocação de trabalho, analisa dependências e isola o espaço de trabalho (branches/worktrees).
   - Limita a execução concorrente a no máximo **dois implementers simultâneos**.
   - Nunca faz merge.
3. **`implementer`**:
   - Focado estritamente no escopo do ticket atribuído.
   - Escreve e executa testes automatizados, documenta decisões técnicas relevantes e submete a Pull Request (`Closes #X`).
   - Nunca faz merge.
4. **`reviewer`**:
   - Realiza uma primeira passagem em modo exclusivamente de leitura (*read-only*).
   - Audita critérios de aceitação, bugs, segurança, ausência de segredos, testes e regressões.
   - Envia feedback objetivo ao implementer; não aprova trabalho próprio e nunca faz merge.
5. **`ui-designer`**:
   - Responsável pela linguagem visual e experiência de interface, utilizando a skill `frontend-design`.
   - Evita estética genérica de dashboards gerados por IA; valida responsividade, acessibilidade (WCAG AA) e evidências visuais.
   - Não altera lógica de backend fora do escopo do ticket.
6. **`source-researcher`**:
   - Investiga websites e endpoints públicos dos operadores de pizza.
   - Não contorna login, CAPTCHA ou proteções anti-bot; recolhe evidência suficiente sem documentação excessiva.
   - Não altera código em tickets de investigação.

---

## 2. Ciclo de Vida Operacional (Workflow Lifecycle)

O fluxo de trabalho segue as etapas do GitHub Project:

```mermaid
flowchart LR
    Backlog["1. Backlog<br/>(Triagem)"] --> Ready["2. Ready<br/>(Especificado)"]
    Ready --> InProgress["3. In Progress<br/>(Branch / Trabalho)"]
    InProgress --> Review["4. Review<br/>(Auditoria / PR)"]
    Review --> Done["5. Done<br/>(Merge do Utilizador)"]
```

1. **Backlog -> Ready:** O `project-manager` estrutura a tarefa com critérios claros e dependências resolvidas.
2. **Ready -> In Progress:** O `orchestrator` cria a branch dedicada a partir da `main` atualizada (`<tipo>/<issue-id>-descricao`), aloca um `implementer` (respeitando o teto de 2 implementers simultâneos) e move o ticket para `In Progress`.
3. **In Progress -> Review:** O `implementer` conclui o desenvolvimento, valida testes, abre a Pull Request seguindo o template do repositório e notifica o `reviewer`. O ticket transita para `Review`.
4. **Auditoria Independente:** O `reviewer` audita as alterações sem editar código de produção. Se aprovado, a PR é sinalizada como pronta para a revisão do utilizador.
5. **Review -> Done:** Apenas o utilizador humano tem autorização para aprovar e efetuar o merge da PR.

---

## 3. Regras de Autonomia e Critérios de Interrupção

### Autonomia Operacional
- Decisões técnicas pequenas, contextuais e reversíveis são tomadas autonomamente pelos agentes.
- Dúvidas ou questões não urgentes devem ser agrupadas numa única mensagem para evitar dispersão.

### Interrupção Estrita do Utilizador
Os agentes devem trabalhar autonomamente e interromper o utilizador **apenas** nas seguintes situações:
1. **Decisão de Produto:** Decisões estratégicas de negócio ou trade-offs de funcionalidades fundamentais.
2. **Alteração de Âmbito:** Necessidade de expansão de escopo face ao ticket original.
3. **Credenciais ou Custos:** Necessidade de contratação de serviços pagos ou credenciais privadas.
4. **Ação Destrutiva:** Operações de risco irreversível em bases de dados ou no histórico de git.
5. **Bloqueio Anti-Bot:** Deteção de CAPTCHA, desafio Cloudflare ou bloqueio intransponível numa fonte pública.
6. **Conflito entre Tickets:** Sobreposição ou bloqueio mútuo entre branches simultâneas.
7. **Falhas Repetidas:** Erros persistentes após ciclos de correção entre implementer e reviewer.
8. **Deploy:** Lançamento de versão ou alteração de ambiente em produção.
9. **PR Pronta:** Notificação final de que a Pull Request foi auditada e aguarda a revisão e merge do utilizador.

---

## 4. Segurança, Ética e Engenharia

- **Zero IA em Runtime:** É expressamente proibido integrar chamadas a APIs de modelos de linguagem (Gemini, OpenAI, Anthropic, etc.) no runtime de produção da aplicação. A agregação, normalização e ranking devem ser 100% determinísticos e testáveis.
- **Zero Segredos:** Nunca comitar senhas, chaves de API, certificados ou ficheiros de ambiente (`.env`).
- **Acesso Ético:** Consulta estrita a páginas e endpoints publicamente acessíveis, sem autenticação, sem simulação de pedidos de encomenda e respeitando os servidores das marcas.
- **Portabilidade:** Evitar acoplamento proprietário (*vendor lock-in*), mantendo interfaces agnósticas de fornecedor de infraestrutura.
- **Proibição de Merge Autónomo:** Nenhum agente tem permissão para fundir Pull Requests ou efetuar commits diretos na branch `main`.
