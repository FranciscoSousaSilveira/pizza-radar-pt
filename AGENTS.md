# Regras para Agentes e Colaboradores — Pizza Radar PT

Este documento estabelece as diretrizes de trabalho obrigatórias para agentes de IA e colaboradores que desenvolvam tarefas no repositório **Pizza Radar PT**.

---

## 1. Fluxo de Trabalho e Git

- **Branch e Pull Request Obrigatórios por Ticket:**
  - Todo o trabalho deve ser realizado numa branch dedicada com nomenclatura semântica (ex.: `feat/<issue-id>-descricao`, `chore/<issue-id>-descricao`, `fix/<issue-id>-descricao`).
  - **Nunca** fazer commits diretos na branch principal (`main`).
  - Todas as alterações devem ser submetidas através de uma **Pull Request** que faça referência e feche o ticket correspondente (ex.: `Closes #1`).
  - **Não fazer merge da Pull Request** de forma autónoma. O merge deve ser revisto e aprovado pelos mantenedores do projeto.

- **Commits Claros e Atómicos:**
  - Escrever mensagens de commit descritivas e estruturadas (preferencialmente seguindo Conventional Commits, ex.: `chore: ...`, `feat: ...`, `docs: ...`).

---

## 2. Ética de Dados e Acesso a Websites Externos

- **Proibição Estrita de Contorno de Proteções:**
  - É expressamente proibido tentar contornar logins, áreas privadas com autenticação, CAPTCHAs, desafios Cloudflare ou quaisquer mecanismos de proteção anti-bot.
  - Apenas dados públicos disponíveis abertamente para qualquer visitante podem ser consultados.
- **Respeito pelas Plataformas:**
  - Respeitar diretivas de acesso, limites de taxa de pedidos (*rate limiting*) e evitar sobrecarga de tráfego nos servidores das marcas monitorizadas.

---

## 3. Segurança e Segredos

- **Zero Segredos no Repositório:**
  - Nunca comitar chaves de API, tokens de acesso, senhas, certificados ou ficheiros com credenciais.
  - Ficheiros de variáveis de ambiente (`.env`, `.env.local`, etc.) devem permanecer sempre excluídos no `.gitignore`.
  - Antes de qualquer push ou abertura de Pull Request, verificar minuciosamente o diff para garantir a ausência total de segredos ou dados sensíveis.

---

## 4. Gestão de Âmbito e Simplicidade

- **Foco Estrito no Âmbito do Ticket:**
  - Implementar exclusivamente o que for solicitado no ticket atribuído.
  - Não antecipar escolhas arquiteturais, dependências ou bibliotecas que não façam parte do âmbito aprovado.
- **Documentação Concisa e Prática:**
  - Manter a documentação focada, direta e fácil de consultar.
  - Evitar texto excessivo ou redundante.
