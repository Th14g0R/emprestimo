# Sistema de Controle de Empréstimos e Cartão de Crédito

## 📋 Visão Geral
Sistema web responsivo para gestão de empréstimos pessoais, cálculo de juros mensais, abatimentos, controle de cartão de crédito, relatórios e geração automática de cobranças por WhatsApp.

## 🏗️ Arquitetura

### Frontend
- **Framework**: Next.js 14+ com App Router
- **Linguagem**: TypeScript
- **Styling**: TailwindCSS + Shadcn UI
- **Gráficos**: Recharts
- **Estado**: Context API / React Query
- **Dark Mode**: Suportado nativamente

### Backend
- **Framework**: NestJS
- **Autenticação**: JWT
- **Banco de Dados**: PostgreSQL com TypeORM
- **Validação**: class-validator
- **Logging**: Winston

### Infraestrutura
- **Database**: PostgreSQL
- **Backup**: Automático
- **CI/CD**: GitHub Actions
- **Deploy**: Docker + Railway/Vercel

## 📦 Entidades Principais

### Cliente
- Informações pessoais (nome, telefone, email, CPF)
- Endereço completo
- Status (ativo/inativo)
- Timestamp de criação/atualização

### Empréstimo
- Valor original e saldo atual independentes
- Taxa de juros mensal específica
- Data de vencimento e dia de vencimento
- Status (ativo/quitado/vencido)
- Relacionado a um único cliente

### Movimentação de Empréstimo
- Tipos: EMPRESTIMO, JUROS, ABATIMENTO, QUITACAO
- Histórico completo de movimentos
- Rastreamento auditável

### Cartão de Crédito
- Independente de empréstimos
- Contém lançamentos e parcelas
- Parcelas geradas automaticamente

### Lançamento de Cartão
- Valor total e quantidade de parcelas
- Data de compra
- Parcelas com vencimentos individuais

## 💼 Regras de Negócio

### Empréstimos
✓ Cada empréstimo é independente
✓ Um cliente pode ter vários empréstimos ativos
✓ Juros não reduzem saldo devedor
✓ Apenas abatimentos ou quitação reduzem saldo
✓ Abatimentos afetam apenas empréstimo selecionado
✓ Novos juros calculados sobre saldo atualizado
✓ Novos empréstimos criam novos contratos

### Cartão de Crédito
✓ Independente de empréstimos
✓ Parcelas geradas automaticamente
✓ Rastreamento de pagamentos

## 🎨 Telas Principais

1. **Dashboard** - Visão geral com cards e gráficos
2. **Clientes** - Listagem e cadastro
3. **Detalhes do Cliente** - Empréstimos e cartão
4. **Empréstimos** - Gestão com movimentações
5. **Movimentações** - Histórico completo
6. **Cartão de Crédito** - Gestão de parcelas
7. **Agenda de Cobranças** - Próximos vencimentos
8. **Relatórios** - Filtros e exportação PDF/Excel

## 📊 Dashboard - Cards

- Total emprestado
- Saldo devedor total
- Juros previstos no mês
- Clientes ativos
- Clientes inadimplentes
- Recebimentos do mês
- Abatimentos do mês

## 📈 Dashboard - Gráficos

- Saldo devedor por cliente
- Saldo devedor por empréstimo
- Recebimentos por mês
- Juros recebidos por período
- Evolução da carteira

## 🔔 Funcionalidades Adicionais

- Dark Mode
- Filtros avançados
- Auditoria de alterações
- Histórico completo
- Confirmação antes de exclusões
- Backup automático
- Validação financeira
- **WhatsApp**: Mensagens automáticas de cobrança com link clicável

## 🔐 Permissões (Admin)

- Gerenciar clientes
- Gerenciar empréstimos
- Gerenciar cartões
- Registrar pagamentos
- Gerar relatórios
- Gerar mensagens WhatsApp
- Visualizar dashboard

## 📱 Responsividade

- Mobile-first design
- Desktop optimization
- Tablets support
