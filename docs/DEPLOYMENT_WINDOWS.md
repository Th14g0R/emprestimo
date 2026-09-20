# Instalação e atualização da versão 2 no Windows

Versão 2.1.0+build.2, branch `release/v2`, serviço `Emprestimo`.
O gerenciador e o bootstrap desta branch usam `release/v2`, sem publicar ou
incorporar mudanças na `main`.

## 1. Pré-requisitos e download

Use uma conta com permissão de administrador para instalar o serviço. O
bootstrap localiza Python e pode oferecer sua instalação via WinGet. Também
é possível instalar Python 3.10+ previamente pelo
[site oficial](https://www.python.org/downloads/windows/), habilitando o acesso
pelo PATH. O gerenciador verifica Git e os demais componentes durante a instalação.

Você pode obter esta versão de duas formas:

- **Pelo navegador:** abra a [branch release/v2](https://github.com/Th14g0R/emprestimo/tree/release/v2),
  selecione **Code → Download ZIP** e extraia todos os arquivos antes de executar.
- **Pelo Git**, em PowerShell ou Prompt, com Git instalado:

```powershell
git clone --branch release/v2 --single-branch https://github.com/Th14g0R/emprestimo.git emprestimo-v2
cd emprestimo-v2
```

Não execute o `.bat` de dentro do ZIP nem misture arquivos da `main` com a v2.

## 2. Instalação como serviço

1. Execute **Gerenciar-Emprestimo.bat** na pasta extraída/clonada e aceite a
   solicitação de administrador do Windows. No PowerShell: `./Gerenciar-Emprestimo.bat`.
2. Escolha **Instalar**, diretório, porta e acesso local/rede. O gerenciador clona
   `release/v2`, cria `.venv`, instala as dependências fixadas e configura
   Waitress como serviço Windows por meio de WinSW.
3. Abra **http://127.0.0.1:5000** no navegador do computador instalado, ou a porta
   que escolheu. Crie o primeiro administrador antes de liberar acesso externo.
   Não existe senha padrão ou geração de exemplos. Em banco restaurado, use
   um usuário já existente.
4. Confira `http://127.0.0.1:5000/health`: a versão inicial é `2.1.0+build.2`.

O serviço continua executando depois de fechar o gerenciador e inicia com o
Windows. Em PowerShell **como administrador**, consulte ou controle assim:

```powershell
Get-Service Emprestimo
Stop-Service Emprestimo
Start-Service Emprestimo
Restart-Service Emprestimo
```

Execute apenas a linha correspondente à ação desejada. Também pode usar o
aplicativo **Serviços** do Windows e localizar **Emprestimo**.

## 3. Alternativa: iniciar manualmente, sem instalar serviço

Na pasta do projeto, em PowerShell ou Prompt, com Python já instalado:

```powershell
python --version
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock
.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:5000 --threads=4 wsgi:application
```

Se só possui o launcher `py`, use `py -3` no lugar de `python` nas duas primeiras
linhas. Confirme Python 3.10 ou superior. Não é necessário ativar a `.venv` nem
alterar a política de execução do PowerShell.

Abra **http://127.0.0.1:5000**. Neste modo, mantenha o Terminal aberto e pressione
**Control + C** para parar. Não inicie este comando na mesma porta de um serviço
já ativo. Não reutilize a `.venv` de outro computador ou sistema operacional.

## Logs e espaço

O serviço usa um processo com quatro threads. Os logs têm rotação por tamanho:
10 MiB por arquivo e cinco arquivos de rotação por fluxo configurados no WinSW.
Backups permanecem separados e precisam de política de retenção.

## Atualização de instalação anterior

Use o gerenciador obtido da branch **release/v2**. Um gerenciador antigo pode
continuar acompanhando a `main`. Existe apenas um serviço com o nome `Emprestimo`;
não tente instalar as duas versões simultaneamente com esse mesmo nome.

Antes da atualização, guarde código da versão instalada, dependências e cópia
consistente de todo o diretório de dados. O gerenciador para o serviço e cria
backup de `data` antes de sincronizar o código. Se usa caminhos externos via
variáveis de ambiente, faça também backup desses caminhos: o backup automático
da instalação cobre a pasta `data` dentro dela.

Valide o banco antigo com `scripts/verificar_banco.py`; a ferramenta trabalha em
cópia temporária e não altera o original. A sincronização substitui alterações
locais do código após confirmação no gerenciador. Não guarde arquivos pessoais
não ignorados na pasta do código.

Na primeira inicialização, as migrações acrescentam estruturas compatíveis sem
recriar o banco ou recalcular recebimentos históricos. Confira clientes, saldos,
últimos recebimentos e acesso aos comprovantes antes de retomar a operação.

## Restauração

Pare o serviço. Restaure **código e dados da mesma cópia anterior**, incluindo
comprovantes e chave de sessão, em um diretório vazio. Recrie as dependências
daquela versão e reconfigure o serviço para esse diretório. Não sobreponha
um `.db` a arquivos WAL/SHM de outra instalação. Não use rollback de código
como substituto de restauração consistente dos dados.

## Rede e HTTPS

Por padrão, prefira acesso local. Para rede, restrinja firewall e hosts permitidos
conforme `.env.example`. Em acesso externo, configure HTTPS no proxy e
`EMPRESTIMO_HTTPS=1`. Use `EMPRESTIMO_BEHIND_PROXY=1` somente atrás de exatamente
um proxy confiável. Configure essas variáveis no ambiente do serviço e reinicie-o.
Não coloque senhas ou chaves no código nem no XML versionado.

## Validação deste build

Os testes automatizados verificam regras financeiras, segurança, migração de
estrutura legada sem dados privados e inicialização por script/WSGI. O runner
Waitress gerado pelo gerenciador também tem validação de importação. A instalação
como serviço, elevação UAC e firewall precisam ser conferidos no Windows;
esta preparação foi executada no macOS.

## Problemas comuns

- **Porta ocupada:** confira se o serviço já está aberto. No PowerShell, use
  `Get-NetTCPConnection -LocalPort 5000 -State Listen`, ou configure outra porta
  pelo gerenciador. Não encerre processos sem identificá-los.
- **Falha ao iniciar:** confira `Get-Service Emprestimo` e os arquivos em `logs`
  dentro da instalação. O gerenciador também apresenta diagnóstico de serviço.
- **Python não encontrado:** reabra o Terminal após instalar Python; confira
  `python --version` ou `py -3 --version` antes de repetir a instalação.
- **Dados diferentes do esperado:** confira o caminho de instalação e as
  variáveis de ambiente. `data/local-test` é exclusivo do inicializador de testes.

Para visão geral, backup e comparação entre sistemas, veja
[Instalação e operação](INSTALACAO.md).
