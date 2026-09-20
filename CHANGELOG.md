# Changelog

## 2.0.0+build.1 — 2026-09-19

- Publicação da versão 2 na branch release/v2, sem dados demonstrativos.
- Interface administrativa e portal do cliente completos.
- Juros de atraso proporcionais, prévia de reagendamento e recebimentos agrupados.
- Transações atômicas, proteções financeiras e migrações incrementais.
- Sincronização da agenda em lote e sem regravação de previsões inalteradas.
- Dependências de produção fixadas e gerenciador Windows direcionado à v2.
- Testes de restauração independentes de backups privados.


## 2026-09-02 — Arquitetura Python/SQLite

- substituição da arquitetura Next.js/NestJS/PostgreSQL/Docker por Flask + SQLite;
- autenticação local;
- clientes;
- empréstimos independentes;
- juros integrais por competência;
- abatimentos múltiplos;
- quitação;
- movimentações e auditoria básica;
- contas bancárias e chaves PIX com snapshots históricos;
- cartões, lançamentos parcelados e pagamentos;
- dashboard financeiro;
- documentação para agentes de IA;
- gerenciador Windows para instalação, atualização e desinstalação;
- Waitress + WinSW para execução como serviço `Emprestimo`.
