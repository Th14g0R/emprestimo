# Sistema de Controle de Empréstimos e Cartão de Crédito

Um sistema web responsivo e moderno para gerenciamento de empréstimos pessoais, cálculo de juros mensais, abatimentos, controle de cartão de crédito, relatórios e geração automática de cobranças por WhatsApp.

## 🎯 Funcionalidades

✅ **Gestão de Clientes** - Cadastro completo com histórico
✅ **Gestão de Empréstimos** - Independentes, com juros e abatimentos  
✅ **Controle de Cartão** - Parcelas automáticas e rastreamento
✅ **Dashboard** - Métricas e gráficos em tempo real
✅ **Relatórios** - PDF e Excel com filtros avançados
✅ **WhatsApp** - Mensagens automáticas de cobrança

## 🛠️ Stack

- **Frontend**: Next.js 14 + TypeScript + TailwindCSS + Shadcn UI
- **Backend**: NestJS + TypeScript + Prisma + PostgreSQL
- **DevOps**: Docker + Turborepo

## 🚀 Quick Start

```bash
# 1. Instalar dependências
npm install

# 2. Iniciar banco de dados
docker-compose up -d

# 3. Configurar banco de dados
cd apps/backend && npx prisma migrate dev --name init && cd ../..

# 4. Iniciar desenvolvimento
npm run dev
```

Acesse:
- Frontend: http://localhost:3000
- Backend: http://localhost:3001
- Database UI: http://localhost:8080

## 📖 Documentação

- **[PROJECT_SPEC.md](./PROJECT_SPEC.md)** - Especificação completa
- **[DESENVOLVIMENTO.md](./DESENVOLVIMENTO.md)** - Guia de desenvolvimento
- **[Variáveis de Ambiente](./.env.example)** - Configurações

## 📂 Estrutura

```
apps/
├── backend/          # NestJS API
│   ├── src/modules/
│   │   ├── auth/     # Autenticação JWT
│   │   ├── clientes/ # Clientes CRUD
│   │   ├── emprestimos/ # Empréstimos
│   │   ├── cartao/   # Cartão de crédito
│   │   └── dashboard/ # Dashboard
│   └── prisma/       # Schema
└── frontend/         # Next.js App
    ├── src/app/      # Páginas
    ├── src/components/ # Componentes
    ├── src/services/ # API
    └── src/types/    # Types
```

## 🔌 API Endpoints Principais

```
POST   /api/auth/login
GET    /api/clientes
POST   /api/clientes
GET    /api/clientes/:id
PUT    /api/clientes/:id

GET    /api/emprestimos
POST   /api/emprestimos
POST   /api/emprestimos/:id/abatimento
POST   /api/emprestimos/:id/quitacao

GET    /api/dashboard/metricas
```

## 🔐 Segurança

- JWT Authentication
- Validações de entrada com class-validator
- CORS configurado
- Proteção de rotas

## 📊 Regras de Negócio

✅ Empréstimos independentes por cliente
✅ Taxa de juros mensal específica
✅ Juros não reduzem o saldo devedor
✅ Abatimentos afetam apenas o empréstimo selecionado
✅ Parcelas de cartão geradas automaticamente
✅ Histórico completo de movimentações

## 📱 Responsividade

Mobile-first design com suporte a desktop e dark mode automático.

## 🤝 Próximos Passos

- [ ] Implementar endpoints de autenticação
- [ ] Criar interfaces do frontend
- [ ] Integração WhatsApp
- [ ] Exportação PDF/Excel
- [ ] Testes automatizados
- [ ] CI/CD com GitHub Actions

---

**Status**: Estrutura base concluída ✨