# 📋 Guia de Desenvolvimento - Sistema de Empréstimos

## ✅ Status da Estrutura Base

### Infraestrutura Criada
- ✅ Monorepo com Turborepo (root)
- ✅ Docker Compose com PostgreSQL
- ✅ Backend NestJS com Prisma
- ✅ Frontend Next.js com TailwindCSS

### Banco de Dados
- ✅ Schema Prisma (Clientes, Empréstimos, Cartão, Movimentações)
- ⏳ Migrations

### Backend - Módulos a Implementar

#### 1. Auth Module (Prioritário)
- [ ] JWT Strategy
- [ ] Auth Controller
- [ ] Auth Service
- [ ] Login endpoint
- [ ] Register endpoint

#### 2. Clientes Module
- [ ] Cliente Controller
- [ ] Cliente Service
- [ ] CRUD endpoints
- [ ] Validações

#### 3. Empréstimos Module
- [ ] Emprestimo Controller
- [ ] Emprestimo Service
- [ ] Cálculo de juros (lógica mensal)
- [ ] Abatimentos
- [ ] Quitação

#### 4. Movimentações Module
- [ ] Registro automático
- [ ] Histórico completo
- [ ] Tipos de movimentação

#### 5. Cartão Module
- [ ] CartaoCredito Controller
- [ ] CartaoCredito Service
- [ ] Geração automática de parcelas

#### 6. Dashboard Module
- [ ] Cards de resumo
- [ ] Cálculos agregados
- [ ] Filtros temporais

#### 7. Relatórios Module
- [ ] PDF Export
- [ ] Excel Export
- [ ] Filtros avançados

#### 8. WhatsApp Integration
- [ ] Geração de mensagens
- [ ] Links clicáveis
- [ ] Agendamento

### Frontend - Páginas a Implementar

#### 1. Layout Base
- [ ] Navbar
- [ ] Sidebar
- [ ] Footer
- [ ] Theme Toggle

#### 2. Dashboard
- [ ] Cards de resumo
- [ ] Gráficos com Recharts
- [ ] Filtros

#### 3. Clientes
- [ ] Listagem com paginação
- [ ] Busca e filtros
- [ ] Formulário de cadastro
- [ ] Edição

#### 4. Empréstimos
- [ ] Listagem por cliente
- [ ] Detalhes do empréstimo
- [ ] Novo empréstimo
- [ ] Movimentações

#### 5. Cartão
- [ ] Listagem de parcelas
- [ ] Registro de pagamentos
- [ ] Status visual

#### 6. Relatórios
- [ ] Gerador de relatórios
- [ ] Export PDF/Excel
- [ ] Filtros avançados

#### 7. Agenda de Cobranças
- [ ] Calendário
- [ ] Próximos vencimentos
- [ ] Integração WhatsApp

## 🚀 Próximos Passos

1. **Setup Inicial**
   ```bash
   cd emprestimo
   npm install
   docker-compose up -d
   ```

2. **Configurar Banco de Dados**
   ```bash
   cd apps/backend
   npx prisma migrate dev --name init
   ```

3. **Iniciar Desenvolvimento**
   ```bash
   npm run dev  # Roda backend e frontend
   ```

## 📂 Estrutura de Pastas

```
emprestimo/
├── apps/
│   ├── backend/
│   │   ├── src/
│   │   │   ├── modules/
│   │   │   │   ├── auth/
│   │   │   │   ├── clientes/
│   │   │   │   ├── emprestimos/
│   │   │   │   ├── cartao/
│   │   │   │   ├── dashboard/
│   │   │   │   └── relatorios/
│   │   │   ├── prisma/
│   │   │   ├── app.module.ts
│   │   │   └── main.ts
│   │   ├── prisma/
│   │   │   └── schema.prisma
│   │   └── package.json
│   │
│   └── frontend/
│       ├── src/
│       │   ├── app/
│       │   ├── components/
│       │   ├── context/
│       │   ├── hooks/
│       │   ├── services/
│       │   ├── types/
│       │   └── lib/
│       └── package.json
│
├── docker-compose.yml
├── package.json
├── turbo.json
└── PROJECT_SPEC.md
```

## 🔑 Variáveis de Ambiente

### Backend (.env)
```
DATABASE_URL=postgresql://emprestimo:password123@localhost:5432/emprestimos_db
BACKEND_PORT=3001
JWT_SECRET=your_secret_key
NODE_ENV=development
```

### Frontend (.env.local)
```
NEXT_PUBLIC_API_URL=http://localhost:3001/api
```

## 📱 Funcionalidades Principais

### Regras de Negócio Implementadas
- ✅ Empréstimos independentes por cliente
- ✅ Taxa de juros mensal específica
- ✅ Cálculo de juros não reduz saldo
- ✅ Abatimentos afetam apenas empréstimo selecionado
- ✅ Parcelas de cartão geradas automaticamente
- ✅ Histórico completo de movimentações

### Segurança
- JWT Authentication
- Validações de entrada
- Auditoria de alterações
- Backup automático

## 💡 Dicas de Desenvolvimento

1. Use as entidades de tipo no frontend (`src/types/index.ts`)
2. Aproveite o `apiClient` para chamadas de API (`src/services/api.ts`)
3. Utilize o contexto de tema para dark mode
4. Todas as datas são em ISO format (PT-BR)
5. Valores monetários em float (centavos como decimais)

---

**Status**: Estrutura base criada ✨
**Próxima Fase**: Implementação dos módulos
