# 🔄 Fluxograma de Operação - Scripts Windows

## 📊 Ciclo de Vida do Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                    SISTEMA DE EMPRÉSTIMOS                       │
│                   Ciclo de Vida Completo                        │
└─────────────────────────────────────────────────────────────────┘

                         ┌──────────────┐
                         │  PRIMEIRO    │
                         │  ACESSO      │
                         └──────┬───────┘
                                │
                    ┌───────────▼───────────┐
                    │   run.bat install     │
                    └───────────┬───────────┘
                                │
    ┌───────────────────────────┼───────────────────────────┐
    │                           │                           │
    ▼                           ▼                           ▼
┌─────────────┐          ┌──────────────┐          ┌──────────────┐
│ Verifica    │          │  Instala     │          │    Cria      │
│ Node.js     │  ──>     │  Docker      │  ──>     │  Serviços    │
│ Git         │          │  Git         │          │  Windows     │
└─────────────┘          └──────────────┘          └──────┬───────┘
                                                          │
                                                   ┌──────▼──────┐
                                                   │   Inicia    │
                                                   │  Serviços   │
                                                   └──────┬──────┘
                                                          │
                                                   ✅ PRONTO!
                                                          │
                                 ┌────────────────────────┘
                                 │
                    ┌────────────▼──────────────┐
                    │   Acesso em Browser       │
                    │ http://localhost:3000     │
                    └───────────────────────────┘


┌─────────────────────────────────────────────────────────────────┐
│                    USO DIÁRIO DO SISTEMA                        │
└─────────────────────────────────────────────────────────────────┘

    ┌────────────────────────────────────┐
    │      run.bat manage                │
    │   (Menu de Gerenciamento)          │
    └────────┬───────────────────────────┘
             │
    ┌────────┴──────────────────────────────────────────────┐
    │                                                        │
    ▼                                      ▼
┌─────────────────┐                  ┌──────────────────┐
│  Iniciar        │                  │  Ver Status      │
│  Parar          │    ┌───────>     │  Parar           │
│  Reiniciar      │    │             │  Reiniciar       │
│  Ver Status     │    │             │  Logs            │
│  Abrir Apps     │◄───┘             │  Aplicações      │
│  Ver Logs       │                  └──────────────────┘
└─────────────────┘


┌─────────────────────────────────────────────────────────────────┐
│              ATUALIZAR PARA NOVA VERSÃO                         │
└─────────────────────────────────────────────────────────────────┘

    ┌─────────────────────┐
    │  run.bat update     │
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │  Para Serviços      │
    │  (Backend/Frontend) │
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │  Git Pull           │
    │  (Atualiza Código)  │
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │  npm install        │
    │  (Dependências)     │
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │  Prisma Migrate     │
    │  (Banco de Dados)   │
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │  Reinicia Serviços  │
    │  (Backend/Frontend) │
    └──────────┬──────────┘
               │
            ✅ ATUALIZADO!


┌─────────────────────────────────────────────────────────────────┐
│           DESINSTALAÇÃO COMPLETA                                │
└─────────────────────────────────────────────────────────────────┘

    ┌──────────────────────┐
    │  run.bat uninstall   │
    └──────────┬───────────┘
               │
    ┌──────────▼───────────┐
    │  Pede Confirmação    │
    │  (Digite: S/N)       │
    └──────────┬───────────┘
               │
    ┌──────────▼───────────┐
    │  Para Serviços       │
    │  Backend/Frontend    │
    └──────────┬───────────┘
               │
    ┌──────────▼───────────┐
    │  Remove Serviços     │
    │  do Windows (SC)     │
    └──────────┬───────────┘
               │
    ┌──────────▼───────────┐
    │  Remove Atalhos      │
    │  (Desktop)           │
    └──────────┬───────────┘
               │
    ┌──────────▼───────────┐
    │  Remove Diretórios   │
    │  C:\Program Files\   │
    │  SistemaEmprestimos  │
    └──────────┬───────────┘
               │
            ✅ REMOVIDO!
```

## 🔄 Fluxo de Inicialização de Serviços

```
Windows Inicia
    │
    ▼
┌──────────────────────────┐
│ Serviços Automáticos     │
│ (configurados)           │
└──────────┬───────────────┘
           │
    ┌──────┴──────┐
    │             │
    ▼             ▼
┌────────┐   ┌─────────────┐
│Backend │   │  Frontend   │
│Service │   │  Service    │
└────┬───┘   └──────┬──────┘
     │              │
     ▼              ▼
┌────────────┐  ┌──────────┐
│ npm start  │  │npm start │
│ Port 3001  │  │Port 3000 │
└────┬───────┘  └──────┬───┘
     │                 │
     └────────┬────────┘
              │
           ✅ RODANDO!
```

## 📋 Checklist de Operação

### Instalação
- [ ] Executar `run.bat install`
- [ ] Aguardar conclusão
- [ ] Verificar logs de erro
- [ ] Acessar http://localhost:3000
- [ ] Confirmar funcionamento

### Atualização
- [ ] Executar `run.bat update`
- [ ] Aguardar conclusão
- [ ] Verificar status `run.bat manage` → opção 4
- [ ] Testar aplicação

### Manutenção Diária
- [ ] Verificar status `run.bat manage` → opção 4
- [ ] Reiniciar se necessário `run.bat manage` → opção 3
- [ ] Revisar logs se houver problemas

### Desinstalação
- [ ] Fazer backup de dados (se necessário)
- [ ] Executar `run.bat uninstall`
- [ ] Confirmar remoção
- [ ] Aguardar conclusão

## 🚨 Cenários de Erro e Recuperação

```
┌─────────────────────────────────────┐
│  CENÁRIO: Serviço não inicia        │
└────────────┬────────────────────────┘
             │
    ┌────────▼────────┐
    │  run.bat manage │
    │  Opção 4: Ver   │
    │  status         │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │  Parado?        │
    │  Erro?          │
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │  Reiniciar      │
    │  Opção 3        │
    └────────┬────────┘
             │
    ✓ Rodando │ ✗ Erro persistente
             │
      ┌──────┴──────┐
      │             │
      ▼             ▼
  Pronto!      Ver logs
                Opção 8/9
                   │
                Verificar
                problemas
                   │
                Reinstalar
               (update.bat)
```

## 🔐 Privilégios e Permissões

```
run.bat
  │
  ├─ Detecta se é admin?
  │  ├─ SIM → Continua normalmente
  │  └─ NÃO → Solicita elevação de privilégios
  │
  ├─ PowerShell -Verb RunAs
  │  └─ Usuário aceita prompt UAC?
  │     ├─ SIM → Executa com admin
  │     └─ NÃO → Cancela operação
  │
  └─ Script continua com privilégios admin
```

## 📊 Estado do Sistema

### Estado: RODANDO
```
Backend Service    ✅ RUNNING
Frontend Service   ✅ RUNNING
PostgreSQL         ✅ UP
Docker Compose     ✅ UP
```

### Estado: PARADO
```
Backend Service    ⛔ STOPPED
Frontend Service   ⛔ STOPPED
PostgreSQL         ⛔ DOWN
Docker Compose     ⛔ DOWN
```

### Estado: ERRO
```
Backend Service    ⚠️  ERROR / RESTARTING
Frontend Service   ⚠️  ERROR / RESTARTING
PostgreSQL         ⚠️  CONNECTION FAILED
Docker Compose     ⚠️  ERROR
```

---

**Versão:** 1.0.0  
**Última atualização:** 02/09/2026
