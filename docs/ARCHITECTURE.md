# Arquitetura do Sistema

Aplicação monolítica Flask com templates Jinja2 e SQLite local. Em ambiente de produção Windows, a execução é gerenciada pelo serviço Waitress; o script `teste_local.py` e os testes automatizados são utilizados para validação e desenvolvimento.

---

## 1. Módulos e Responsabilidades

- **`app.py`**: Fábrica da aplicação (`create_app`), ciclo de vida de requisição (CSRF, bloqueio de concorrência com `BEGIN IMMEDIATE`), injeção de contexto global (`app_version`) e rotas administrativas principais.
- **`portal.py`**: Blueprint do portal do cliente (`/portal`), com autenticação via token/sessão, headers de segurança estritos (CSP com suporte a fontes locais e Google Fonts, HSTS, X-Frame-Options) e endpoints de autosserviço.
- **`database.py`**: Gerenciador de conexão com SQLite, inicialização de DDL, migrações incrementais (`migrate_schema`) e triggers/guards de integridade.
- **`money.py`**: Utilitários para tratamento seguro de valores monetários estritamente em **centavos inteiros** (sem arredondamentos imprecisos de ponto flutuante).
- **`financial_rules.py`**: Regras de negócio de empréstimos, validação de saldos, cálculo de juros mensais e juros de mora.
- **`transactions.py`**: Execução atômica de movimentações (`EMPRESTIMO`, `JUROS`, `ABATIMENTO`, `QUITACAO`) com snapshot histórico bancário.
- **`painel.py`**: Agregações e consultas analíticas para o dashboard gerencial.
- **`security.py`**: Sanitização, limitação de taxa (*rate limiting*) e controle de tentativas de login.

---

## 2. Integridade e Concorrência Financeira

- **Transações Atômicas**: Requisições do tipo POST que alteram dados financeiros adquirem bloqueio exclusivo no SQLite através de `BEGIN IMMEDIATE` antes da execução dos handlers de rota.
- **Commit / Rollback Centralizado**: Commits são gerenciados no final da requisição; qualquer exceção força um `ROLLBACK`, garantindo que nenhuma transação parcial corrompa o banco.
- **Snapshot Histórico**: Toda movimentação financeira armazena um snapshot das contas e chaves PIX de origem e destino, prevenindo inconsistências caso dados cadastrais sejam alterados futuramente.

---

## 3. Otimizações de Banco e Cache

- **Índices Compostos**:
  - `idx_titulos_receber_status_vencimento` em `(status, data_vencimento, emprestimo_id)`: acelera expressivamente as consultas do dashboard e filtros de cobrança por títulos em aberto e vencidos.
  - `idx_titulos_receber_competencia` em `(emprestimo_id, competencia)`: otimiza verificação de duplicidade de cobrança mensal.
  - `idx_juros_emprestimo_competencia` e `idx_movimentacoes_tipo_competencia`: garantem consultas rápidas de extrato e conciliação.
- **Versionamento de Assets (Cache-Busting)**:
  - Estilos (`app.css`) e scripts (`app.js`) utilizam sufixo de versão dinâmico (`?v={{ app_version }}`), garantindo que atualizações visuais sejam carregadas imediatamente pelos navegadores sem retenção em cache obsoleto.

---

## 4. Estratégia de Modularização Incremental (Roadmap)

Para manter o código limpo, manutenível e desacoplado à medida que novas funcionalidades são adicionadas, a extração de rotas de `app.py` deve seguir o padrão de **Flask Blueprints** modulares, sem separar frontend e backend:

1. **`blueprints/clientes.py`**:
   - Rotas de listagem, cadastro, edição, histórico e ativação/inativação de clientes.
2. **`blueprints/emprestimos.py`**:
   - Criação de contratos de empréstimo, extrato financeiro, amortizações e liquidações.
3. **`blueprints/cobranca.py`**:
   - Títulos a receber, baixa manual/integrada de parcelas, emissão de cobranças e relatórios de inadimplência.
4. **`blueprints/cartoes.py`**:
   - Gestão de cartões de crédito, parcelamentos e conciliação de faturas.

> **Regra de Transição**: Durante a refatoração para Blueprints, mantenha os mesmos nomes de endpoints (`url_for`) ou crie aliases para garantir que templates Jinja2 e rotas externas continuem 100% funcionais e sem quebra de testes.

---

## 5. Privacidade e Segurança

- Dados pessoais, banco de dados (`data/emprestimos.db`), comprovantes, chaves secretas (`data/.secret_key`) e backups são privados e ignorados pelo Git.
- Para execução e testes locais isolados, consulte `TESTE_LOCAL.md`.
