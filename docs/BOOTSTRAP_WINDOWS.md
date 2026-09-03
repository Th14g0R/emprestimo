# Bootstrap autônomo do Gerenciador

## Objetivo

O arquivo `Gerenciar-Emprestimo.bat` pode ser usado sozinho em um computador
Windows novo.

### Instalação

1. Baixe somente `Gerenciar-Emprestimo.bat`.
2. Execute com dois cliques.
3. Escolha `1 - Instalar`.
4. O Windows abrirá um seletor gráfico de pasta.
5. Se for escolhida `D:\Sistemas`, a instalação será feita em
   `D:\Sistemas\Emprestimo`.
6. O gerenciador verifica Git, Python e pip.
7. Dependências ausentes podem ser instaladas pelo WinGet mediante confirmação.
8. O repositório `https://github.com/Th14g0R/emprestimo` é clonado na pasta.
9. É criado `.venv`, instalado `requirements.txt`, configurado WinSW/Waitress,
   instalado o serviço Windows `Emprestimo`, criado o atalho e testado `/health`.

### Atualização

Execute o mesmo `.bat` e escolha `2 - Atualizar`.
A pasta instalada é descoberta pelo Registro do Windows. O banco local é
preservado e é criado backup antes da atualização.

### Desinstalação

Execute o mesmo `.bat` e escolha `3 - Desinstalar`.
O serviço é parado/removido, atalhos e arquivos são removidos e o usuário pode
optar por preservar uma cópia dos dados.

## Comportamento do bootstrap

- Se `scripts\Gerenciar-Emprestimo.ps1` existir ao lado do `.bat`, usa a versão
  local. Isso permite testar alterações antes de publicar.
- Se o script local não existir, baixa a versão atual diretamente de
  `raw.githubusercontent.com`.
- O PowerShell é iniciado em modo STA para suportar `FolderBrowserDialog`.
