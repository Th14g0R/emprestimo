# Scripts de Instalação e Gerenciamento - Sistema de Empréstimos

## 📋 Visão Geral

Este diretório contém scripts BAT para gerenciar o Sistema de Controle de Empréstimos e Cartão de Crédito no Windows. Cada script realiza tarefas específicas de instalação, atualização e gerenciamento.

## 🛠️ Requisitos

- **Windows 7 ou superior**
- **Privilégios de Administrador**
- **Conexão à Internet** (para download de dependências)

## 📦 Scripts Disponíveis

### 1. **install.bat** - Instalação Completa
Realiza a instalação inicial do sistema.

**O que faz:**
- ✅ Verifica e instala Node.js (se necessário)
- ✅ Verifica Docker (se necessário)
- ✅ Verifica e instala Git (se necessário)
- ✅ Cria diretório de instalação em `C:\Program Files\SistemaEmprestimos`
- ✅ Copia arquivos do projeto
- ✅ Instala dependências npm
- ✅ Instala NSSM (Non-Sucking Service Manager)
- ✅ Cria serviços do Windows (Backend e Frontend)
- ✅ Inicia os serviços
- ✅ Cria atalho na área de trabalho

**Como usar:**
```bash
# Clique com botão direito e escolha "Executar como administrador"
# Ou via linha de comando:
runas /user:Administrator "cmd.exe /c scripts\install.bat"
```

**Tempo estimado:** 15-30 minutos (na primeira vez)

### 2. **update.bat** - Atualização
Atualiza o sistema para a versão mais recente.

**O que faz:**
- ✅ Para os serviços
- ✅ Executa `git pull` para atualizar código
- ✅ Atualiza dependências npm
- ✅ Executa migrations do banco de dados
- ✅ Reinicia os serviços

**Como usar:**
```bash
# Clique com botão direito e escolha "Executar como administrador"
runas /user:Administrator "cmd.exe /c scripts\update.bat"
```

**Tempo estimado:** 5-15 minutos

### 3. **uninstall.bat** - Desinstalação
Remove o sistema completamente da máquina.

**O que faz:**
- ✅ Para os serviços
- ✅ Remove serviços do Windows
- ✅ Remove atalhos
- ✅ Remove diretório de instalação
- ✅ Limpa variáveis de ambiente

**Como usar:**
```bash
# Clique com botão direito e escolha "Executar como administrador"
runas /user:Administrator "cmd.exe /c scripts\uninstall.bat"
```

**Aviso:** Esta operação é irreversível!

### 4. **manage.bat** - Gerenciador
Menu interativo para gerenciar os serviços.

**Opções disponíveis:**
- 1 - Iniciar serviços
- 2 - Parar serviços
- 3 - Reiniciar serviços
- 4 - Ver status dos serviços
- 5 - Abrir Frontend (http://localhost:3000)
- 6 - Abrir Backend API (http://localhost:3001/api)
- 7 - Abrir Database Admin (http://localhost:8080)
- 8 - Ver logs do Backend
- 9 - Ver logs do Frontend
- 0 - Sair

**Como usar:**
```bash
# Clique com botão direito e escolha "Executar como administrador"
runas /user:Administrator "cmd.exe /c scripts\manage.bat"
```

**Tempo estimado:** Instantâneo

## 🚀 Guia de Uso

### Primeira Instalação

1. **Baixe ou clone o repositório**
   ```bash
   git clone https://github.com/seu-usuario/emprestimo.git
   cd emprestimo
   ```

2. **Execute o instalador**
   ```bash
   # Clique com botão direito em scripts\install.bat
   # Escolha "Executar como administrador"
   ```

3. **Aguarde a conclusão**
   - O script vai verificar e instalar dependências
   - Criar serviços do Windows
   - Iniciar os serviços automaticamente

4. **Acesse o sistema**
   - Abra seu navegador
   - Acesse: http://localhost:3000

### Atualizar para Nova Versão

1. **Execute o atualizador**
   ```bash
   # Clique com botão direito em scripts\update.bat
   # Escolha "Executar como administrador"
   ```

2. **Aguarde a conclusão**
   - O script vai parar os serviços
   - Atualizar o código
   - Aplicar migrations
   - Reiniciar os serviços

### Gerenciar Serviços

1. **Abra o gerenciador**
   ```bash
   # Clique com botão direito em scripts\manage.bat
   # Escolha "Executar como administrador"
   ```

2. **Escolha a operação desejada**
   - Iniciar/Parar/Reiniciar
   - Ver status
   - Abrir aplicações
   - Ver logs

### Desinstalar Sistema

1. **Execute o desinstalador**
   ```bash
   # Clique com botão direito em scripts\uninstall.bat
   # Escolha "Executar como administrador"
   ```

2. **Confirme a operação**
   - Digite "S" para confirmar
   - Aguarde a conclusão

## 🐛 Solução de Problemas

### Erro: "Acesso negado" ou "Permissão insuficiente"
- **Solução:** Abra o Prompt de Comando como Administrador
- Clique com botão direito em "Prompt de Comando"
- Escolha "Executar como administrador"

### Erro: "Node.js não foi instalado"
- **Solução:** Instale Node.js manualmente de https://nodejs.org
- Ou deixe o script instalar automaticamente
- Reinicie o computador após a instalação

### Erro: "Docker não encontrado"
- **Solução:** Instale Docker Desktop de https://www.docker.com/products/docker-desktop
- Após a instalação, reinicie o computador
- Execute o script novamente

### Serviços não iniciam
- **Solução:** Verifique o status:
  ```bash
  scripts\manage.bat
  Opção 4: Ver status dos serviços
  ```
- Tente reiniciar:
  ```bash
  scripts\manage.bat
  Opção 3: Reiniciar serviços
  ```

### Porta já em uso
- **Erro:** "Port 3000 is already in use"
- **Solução:** Encontre o processo usando a porta:
  ```bash
  netstat -ano | findstr :3000
  ```
- Encerre o processo:
  ```bash
  taskkill /PID <PID> /F
  ```

## 📊 Diretórios Criados

Após a instalação, a seguinte estrutura será criada:

```
C:\Program Files\SistemaEmprestimos\
├── apps/
│   ├── backend/        # NestJS backend
│   └── frontend/       # Next.js frontend
├── docker-compose.yml
├── package.json
├── .env                # Configurações
└── INSTALACAO_INFO.txt # Informações de instalação
```

## 🔑 Variáveis de Ambiente

Os scripts usam as seguintes variáveis:

```
INSTALL_DIR=%ProgramFiles%\SistemaEmprestimos
SERVICE_NAME=SistemaEmprestimosBackend
FRONTEND_SERVICE_NAME=SistemaEmprestimosFrontend
```

Para modificar, edite os scripts ou as variáveis do Windows:

```bash
setx INSTALL_DIR "C:\Caminho\Customizado"
```

## 🔄 Serviços Criados

Após a instalação, dois serviços Windows serão criados:

### 1. **Sistema de Empréstimos - Backend**
- **Nome interno:** SistemaEmprestimosBackend
- **Status:** Automático (inicia com Windows)
- **Porta:** 3001
- **Comando:** `npm start` (apps/backend)

### 2. **Sistema de Empréstimos - Frontend**
- **Nome interno:** SistemaEmprestimosFrontend
- **Status:** Automático (inicia com Windows)
- **Porta:** 3000
- **Comando:** `npm start` (apps/frontend)

## 🔗 Acessos Rápidos

Após a instalação, você pode acessar:

- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:3001/api
- **Database Admin:** http://localhost:8080
- **Atalho Desktop:** Sistema Emprestimos.lnk

## 📝 Logs e Debugging

Os logs são salvos em:
- Backend: `C:\Program Files\SistemaEmprestimos\apps\backend\logs\`
- Frontend: `C:\Program Files\SistemaEmprestimos\apps\frontend\logs\`

Para visualizar:
```bash
scripts\manage.bat
Opção 8: Ver logs do Backend
Opção 9: Ver logs do Frontend
```

## 🆘 Suporte

Se encontrar problemas:

1. Verifique o status dos serviços:
   ```bash
   scripts\manage.bat → Opção 4
   ```

2. Consulte os logs:
   ```bash
   scripts\manage.bat → Opção 8 ou 9
   ```

3. Tente reiniciar:
   ```bash
   scripts\manage.bat → Opção 3
   ```

4. Se tudo falhar, desinstale e reinstale:
   ```bash
   scripts\uninstall.bat
   scripts\install.bat
   ```

## ⚙️ Configuração Avançada

### Alterar porta de execução

1. Edite o arquivo `.env` em `C:\Program Files\SistemaEmprestimos\`
2. Modifique as variáveis de porta
3. Execute `scripts\update.bat` para aplicar

### Remover serviços manualmente

```bash
# Para remover o serviço Backend:
sc delete SistemaEmprestimosBackend

# Para remover o serviço Frontend:
sc delete SistemaEmprestimosFrontend
```

### Reinstalar serviços

```bash
# Desinstale
scripts\uninstall.bat

# Reinstale
scripts\install.bat
```

## 📄 Licença

Estes scripts são parte do Sistema de Controle de Empréstimos e Cartão de Crédito.

## 📞 Contato e Suporte

Para suporte, consulte a documentação principal do projeto ou abra uma issue no repositório.

---

**Versão:** 1.0.0  
**Última atualização:** 02/09/2026  
**Sistema Operacional:** Windows 7+
