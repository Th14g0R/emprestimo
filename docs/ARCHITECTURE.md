# Arquitetura

Aplicação monolítica Flask com templates Jinja2 e SQLite local. Produção
Windows usa Waitress; `teste_local.py` é exclusivo para desenvolvimento.

`app.py` mantém a fábrica e as rotas administrativas. `portal.py` registra o
Blueprint do cliente. `database.py` concentra conexão, schema e migrações;
`money.py`, `financial_rules.py` e `transactions.py` concentram proteções
financeiras. `painel.py` mantém consultas do dashboard e `security.py`, limites
públicos. A extração de outras rotas pode ser incremental, sem separar frontend.

POSTs validados por CSRF adquirem BEGIN IMMEDIATE antes da execução da rota.
Commits internos são adiados até o retorno; falhas fazem rollback. Uma segunda
requisição financeira só lê os saldos depois da conclusão da primeira.

Dados pessoais, banco, comprovantes, chaves e backups são privados e ignorados
pelo Git. Veja TESTE_LOCAL.md para execução isolada, validação e restauração.
