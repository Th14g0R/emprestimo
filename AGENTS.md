# AGENTS.md — Contexto obrigatório para IAs

## Objetivo

Este repositório implementa um sistema web de controle de empréstimos pessoais e cartão de crédito. A prioridade do projeto é **simplicidade operacional**, integridade financeira e rastreabilidade.

## Stack obrigatória

- Python
- Flask
- SQLite
- Jinja2 / HTML / CSS
- Waitress no Windows para produção

Não introduzir Node.js, npm, Docker, PostgreSQL, Next.js, NestJS, Prisma ou uma arquitetura frontend/backend separada sem solicitação explícita.

## Inicialização

Desenvolvimento:

```text
python app.py
```

Produção Windows:

```text
Waitress -> Flask -> SQLite
```

O serviço Windows chama-se `Emprestimo`.

## Banco

Arquivo: `data/emprestimos.db`.

- Usar `PRAGMA foreign_keys = ON` em toda conexão.
- Preservar dados existentes em upgrades.
- Migrações devem ser incrementais/compatíveis.
- Valores monetários são armazenados em **centavos inteiros**.
- Nunca usar `float` para valores monetários.
- O banco e `data/.secret_key` não pertencem ao Git.

## Regras financeiras obrigatórias

1. Cada empréstimo pertence a um cliente e é independente dos demais empréstimos do mesmo cliente.
2. Todo movimento financeiro de empréstimo pertence obrigatoriamente a um `emprestimo_id`.
3. `EMPRESTIMO` cria o principal e o saldo inicial.
4. `JUROS` é integral por competência mensal e não reduz nem aumenta o saldo principal.
5. Não pode existir mais de um lançamento `JUROS` para a mesma competência e empréstimo.
6. `ABATIMENTO` pode ocorrer várias vezes no mesmo mês e reduz apenas o saldo principal do empréstimo selecionado.
7. `QUITACAO` deve corresponder ao saldo principal restante, zerar o saldo e marcar o empréstimo como `QUITADO`.
8. Um empréstimo permanece ativo enquanto possuir saldo principal maior que zero.
9. Origem/destino bancários precisam ser associados às movimentações e manter snapshot histórico do banco/PIX usados na operação.
10. Edição/correção de valor financeiro já lançado é proibida por padrão. Se futuramente for implementada, deve exigir nova confirmação da senha do usuário atualmente logado e manter auditoria da alteração.

## Fluxo bancário

Empréstimo inicial:

```text
conta própria -> conta do cliente
```

Juros, abatimento e quitação:

```text
conta do cliente -> conta própria
```

## Segurança

- Senhas armazenadas somente com hash Werkzeug.
- Sessões protegidas pela `SECRET_KEY`.
- Formulários POST usam CSRF.
- Nunca colocar senha, token, banco de produção ou chave privada no repositório.
- O repositório público não é backup adequado para dados financeiros.

## Antes de alterar lógica financeira

Leia `docs/BUSINESS_RULES.md` e confirme que a alteração mantém os invariantes descritos acima.
