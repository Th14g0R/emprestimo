# Correções dos scripts Windows

Esta revisão corrige quatro pontos:

1. **Publicar-GitHub.ps1**
   - não usa mais `$PSScriptRoot` como valor padrão dentro de `param()`;
   - detecta Git for Windows;
   - oferece instalação automática via WinGet quando o Git não existe;
   - solicita nome/e-mail para o commit se o Git ainda não tiver identidade configurada;
   - continua excluindo banco SQLite e `.secret_key` da publicação.

2. **Gerenciar-Emprestimo.ps1**
   - `0 - Sair` não atribui mais `$null` à variável `$Acao`, que possui `ValidateSet`;
   - usa a variável separada `$SelectedAction` para a escolha interativa.

3. **Codificação**
   - os arquivos `.ps1` são gravados como UTF-8 com BOM para compatibilidade com Windows PowerShell 5.1 e textos em português.

4. **Arquivos BAT**
   - chamam diretamente os scripts na pasta `scripts`;
   - removida a cópia temporária desnecessária do gerenciador.
