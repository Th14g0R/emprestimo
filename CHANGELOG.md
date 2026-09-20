# Changelog

## 2.1.1+build.3 — 2026-09-20

- Caminho padrão macOS corrigido para ~/Applications.
- Migração confirmada do caminho antigo, com backup, proteção de instalações
  existentes e recriação do ambiente Python/LaunchAgent. Dados permanecem no lugar.


## 2.1.0+build.2 — 2026-09-20

- Gerenciador macOS: instalação, consulta de atualização, ativação confirmada,
  backup e importação inicial de base v1 com validação em cópia.
- Código por release, dados persistentes separados e execução com LaunchAgent.
- Runner Waitress com rotação de logs e versão discreta no rodapé.
- Testes de cópia SQLite/WAL, bloqueio de sobrescrita e cancelamento da ativação.
- Validação contínua também em macOS. Regras financeiras e schema preservados.


## Documentação multiplataforma — 2026-09-19

- Guias de instalação, execução automática, atualização e diagnóstico para
  Windows, macOS e Linux na branch release/v2.
- Nenhuma alteração de versão da aplicação, regra financeira ou esquema.

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
