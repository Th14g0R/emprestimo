# 📤 Guia: Como Fazer Upload para o GitHub

## ✅ Pré-Requisitos

Você já tem:
- ✅ Git instalado localmente
- ✅ Repositório local: `C:\Users\thiago.rezende\.copilot\repos\copilot-worktrees\emprestimo\th14g0r-glowing-memory`
- ✅ Repositório remoto: `https://github.com/Th14g0R/emprestimo`
- ✅ Todos os commits locais já feitos

## 🚀 Passo 1: Verificar Status

Abra o **PowerShell** ou **CMD** e execute:

```bash
cd C:\Users\thiago.rezende\.copilot\repos\copilot-worktrees\emprestimo\th14g0r-glowing-memory
git status
```

Você deve ver algo como:
```
On branch th14g0r-sistema-emprestimos-cartao
nothing to commit, working tree clean
```

## 📋 Passo 2: Verificar Commits Locais

Veja os commits que serão enviados:

```bash
git log --oneline -10
```

Você deve ver:
```
570a0b8 fix: Remover codigos ANSI e melhorar instalacao
2125828 fix: Adicionar suporte UTF-8 a todos os scripts BAT
c67b87d fix: Corrigir run.bat - input e encoding de caracteres
624e7d5 docs: Adicionar guias visuais e fluxogramas de operacao
de87d91 feat: Adicionar scripts BAT para instalacao e gerenciamento
...
```

## 🔐 Passo 3: Configurar Credenciais do GitHub (Se Não Feito)

### Opção A: Token de Acesso Pessoal (Recomendado)

1. **Gere um token em:** https://github.com/settings/tokens
   - Clique em "Generate new token (classic)"
   - Selecione escopos: `repo`, `admin:repo_hook`
   - Copie o token gerado

2. **Configure no Git:**
   ```bash
   git config --global credential.helper wincred
   git clone https://seu_token@github.com/Th14g0R/emprestimo.git
   ```
   Windows vai pedira para salvar a credencial na primeira execução

### Opção B: SSH (Avançado)

Se já tem SSH configurado, pule para o Passo 4.

## 📤 Passo 4: Fazer Push (Enviar) para o GitHub

### Opção 1: Se a Branch Já Existe no GitHub

```bash
git push origin th14g0r-sistema-emprestimos-cartao
```

### Opção 2: Se é a Primeira Vez (Criar Branch no GitHub)

```bash
git push -u origin th14g0r-sistema-emprestimos-cartao
```

### Opção 3: Enviar Múltiplos Branches

```bash
git push origin --all
```

## ✅ Verificar Upload Bem-Sucedido

1. Acesse: https://github.com/Th14g0R/emprestimo
2. Clique em "Branches"
3. Procure por: `th14g0r-sistema-emprestimos-cartao`
4. Você deve ver todos os commits listados

## 🔄 Próximos Passos: Criar Pull Request (PR)

Após fazer push, você pode criar um PR:

1. Acesse: https://github.com/Th14g0R/emprestimo
2. Clique em "Compare & pull request"
3. Preencha:
   - **Title:** Implementar Sistema de Controle de Empréstimos
   - **Description:** Adiciona funcionalidade completa com:
     - Backend NestJS
     - Frontend Next.js
     - Docker setup
     - Scripts de instalação Windows
4. Clique em "Create pull request"

## 🆘 Resolvendo Problemas

### "Permission denied (publickey)"

Use token de acesso em vez de SSH:
```bash
git remote set-url origin https://seu_token@github.com/Th14g0R/emprestimo.git
git push origin th14g0r-sistema-emprestimos-cartao
```

### "fatal: not a git repository"

Certifique-se que está no diretório correto:
```bash
cd C:\Users\thiago.rezende\.copilot\repos\copilot-worktrees\emprestimo\th14g0r-glowing-memory
```

### "Everything up-to-date"

Significa que já foi feito push com sucesso. Tente:
```bash
git log -1 --oneline
```
Se aparecer seu commit, já está no GitHub!

### "Rejeitado: branch protegida"

Se a branch main está protegida, é normal. Você pode:
1. Fazer merge da branch atual para main (via PR)
2. Ou pedir permissão ao proprietário do repositório

## 📊 Resumo dos Comandos

```bash
# Configurar credenciais
git config --global user.name "Seu Nome"
git config --global user.email "seu@email.com"

# Verificar status
git status
git log --oneline -5

# Fazer push
git push origin th14g0r-sistema-emprestimos-cartao

# Ver commits no GitHub
git log --oneline --decorate --graph

# Sincronizar com repositório remoto
git fetch origin
git pull origin th14g0r-sistema-emprestimos-cartao
```

## 🎯 Situação Atual

Seus arquivos estão:
- ✅ Localmente: `C:\Users\thiago.rezende\.copilot\repos\copilot-worktrees\emprestimo\th14g0r-glowing-memory`
- ✅ Já fazem parte do Git (repositório local)
- ⏳ Aguardando: Upload para GitHub (next step)

## 📝 Checklist Final

- [ ] Executei `git status` e está limpo
- [ ] Executei `git log` e vejo meus commits
- [ ] Configurei credenciais do GitHub
- [ ] Executei `git push origin th14g0r-sistema-emprestimos-cartao`
- [ ] Acessei GitHub e vejo minha branch
- [ ] Criei Pull Request (opcional)

---

**Próximo:** Execute `git push origin th14g0r-sistema-emprestimos-cartao` agora!
