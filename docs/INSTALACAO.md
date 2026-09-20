# Instalação e operação — Windows, Linux e macOS

A versão **2.0.0+build.1** está na branch **release/v2**. O sistema é uma aplicação
web: você instala o servidor em um computador e o utiliza pelo navegador.
Não é necessário instalar Node.js, Docker ou outro banco de dados.

| Sistema | Instalação | Execução automática |
| --- | --- | --- |
| [Windows](DEPLOYMENT_WINDOWS.md) | Gerenciador `.bat` / PowerShell ou instalação manual | Serviço `Emprestimo`, Waitress + WinSW |
| [macOS](DEPLOYMENT_MACOS.md) | Terminal, Python e ambiente virtual | LaunchAgent ao fazer login |
| [Linux](DEPLOYMENT_LINUX.md) | Terminal; exemplo de pacotes Ubuntu/Debian | Serviço de usuário systemd, com opção de iniciar no boot |

Siga **somente o guia do seu sistema**. O mesmo código usa Waitress e SQLite nos
três casos. A instalação automática por interface de menu está disponível
apenas no Windows; os outros guias trazem os comandos equivalentes.

## O que preparar

- Python 3.10 ou superior e Git; os guias explicam como instalar ou verificar.
- Uma pasta permanente e gravável no disco local, fora de pastas sincronizadas.
- Uma porta livre. Os exemplos usam `127.0.0.1:5000`, acessível só no computador
  onde o sistema está instalado.
- Um ambiente `.venv` criado no próprio sistema operacional, com
  `requirements.lock`. Não transfira `.venv` entre computadores.

No primeiro acesso, crie o administrador localmente. Não existe senha padrão nem
base demonstrativa. Para dados já restaurados, use os usuários daquele banco.

## Onde ficam os dados

Por padrão, na pasta do projeto:

```text
data/
  emprestimos.db       banco de dados
  .secret_key         chave que preserva as sessões
  comprovantes/       PDFs e imagens enviados
```

O SQLite pode criar também `emprestimos.db-wal` e `emprestimos.db-shm` enquanto
está em uso. Esses arquivos não são lixo. Não os apague com o sistema aberto.
O código, sozinho, não contém clientes ou pagamentos.

`EMPRESTIMO_DATA_DIR`, `EMPRESTIMO_DATABASE` e `EMPRESTIMO_SECRET_KEY_FILE` podem
alterar os caminhos. Se as configurou, faça backup dos caminhos reais. O arquivo
`.env.example` é documentação: não é carregado automaticamente. Configure as
variáveis no Terminal ou no gerenciador de serviço correspondente.

`teste_local.py` utiliza `data/local-test`, separado do banco oficial. Use os
comandos Waitress dos guias para operação normal.

## Backup e atualização

### Antes de qualquer atualização

1. Pare o servidor: Control + C no Terminal, serviço Windows, LaunchAgent ou
   systemd, conforme o guia. Pare também outras instâncias que usem o mesmo banco.
2. Faça uma cópia de **todo o diretório de dados**, incluindo chave e comprovantes,
   e guarde também a versão do código correspondente. Uma cópia manual de apenas
   `.db` enquanto o sistema executa pode perder movimentações ainda no WAL.
3. Guarde o backup fora da instalação e mantenha outra cópia fora do servidor.
   Defina retenção; não inclua backups antigos dentro de cada novo backup.
4. Se estiver trazendo um banco antigo, execute `scripts/verificar_banco.py`
   com o Python da `.venv`. A verificação migra somente uma cópia temporária.

No **Windows**, siga o fluxo do [gerenciador](DEPLOYMENT_WINDOWS.md). Ele faz
backup da pasta `data` da instalação; caminhos externos precisam de cópia adicional.

No **macOS/Linux**, para a instalação padrão por Git, com o servidor parado,
entre na pasta do projeto e execute:

```sh
mkdir -p "$HOME/Backups/emprestimo"
EMPRESTIMO_BACKUP_DIR="$HOME/Backups/emprestimo/$(date +%Y%m%d-%H%M%S)"
mkdir -m 700 "$EMPRESTIMO_BACKUP_DIR"
git rev-parse HEAD > "$EMPRESTIMO_BACKUP_DIR/COMMIT.txt"
git archive --format=zip --output="$EMPRESTIMO_BACKUP_DIR/codigo.zip" HEAD
tar -czf "$EMPRESTIMO_BACKUP_DIR/dados.tar.gz" data
```

Este exemplo supõe dados em `data` e código sem alterações locais. Se usa dados
externos, inclua-os em cópia separada. O arquivo de código contém somente o commit;
guarde também alterações locais, caso existam. Interrompa o procedimento se
qualquer comando falhar. Confira se os arquivos foram criados antes de atualizar.

### Atualizar uma instalação Git no macOS/Linux

Com o backup concluído e o serviço ainda parado, na pasta do projeto:

```sh
git branch --show-current
git status --short
```

A branch deve ser `release/v2` e o segundo comando deve retornar vazio. Se houver
alterações, guarde-as e resolva a divergência antes de continuar; não utilize
`reset --hard` para ignorar o problema.

```sh
git pull --ff-only origin release/v2
.venv/bin/python -m pip install -r requirements.lock
```

Se algum comando falhar, não continue a inicialização sem corrigir a causa.
Depois, inicie pelo mesmo método indicado no guia do seu sistema. A aplicação
executa migrações incrementais no primeiro início. Confira `/health`, login,
clientes, saldos, últimos pagamentos e comprovantes antes de retomar o uso.

Se instalou por **ZIP**, não há `git pull`: baixe o novo pacote da branch,
extraia em uma pasta nova, crie a `.venv` nela e, com ambos os servidores parados,
transfira os dados. Ajuste os caminhos do serviço. Não substitua somente `app.py`,
pois a aplicação depende dos demais módulos, templates e arquivos estáticos.

### Restaurar ou voltar à versão anterior

Pare o serviço e preserve primeiro uma cópia do estado atual. Restaure código e
dados **do mesmo backup** em uma pasta vazia. Não misture o `.db` restaurado com
WAL/SHM de outra instalação. Recrie a `.venv` usando as dependências daquela
versão e ajuste o serviço para o diretório restaurado.

Voltar apenas o código não desfaz as migrações ou movimentações. Veja as regras
específicas de [compatibilidade do banco](JUROS_ATRASO_E_RESTAURACAO.md).

## Acesso pela rede

`127.0.0.1` significa o próprio computador. Para aceitar conexões de outros
computadores da rede, o processo precisa escutar uma interface de rede:

```text
--listen=0.0.0.0:5000
```

`0.0.0.0` é configuração do servidor, não endereço para digitar no navegador.
Use o IP real do computador, por exemplo `http://192.168.1.20:5000`, e permita
somente a rede necessária no firewall. No Windows, use a opção de acesso em
rede do gerenciador; no Mac/Linux altere o comando ou a configuração do serviço.
Se trocar a porta, atualize também o endereço do navegador e o firewall.

Para acesso pela internet, configure um proxy HTTPS e hosts permitidos antes
de expor o serviço. Defina `EMPRESTIMO_HTTPS=1` somente quando o navegador usar
HTTPS. Ative `EMPRESTIMO_BEHIND_PROXY=1` apenas atrás de exatamente um proxy
confiável. Esses guias não instalam nem configuram automaticamente domínio,
certificados ou proxy. Para administrar um servidor remoto sem expor a porta,
pode usar o túnel SSH explicado no guia Linux.

## Conferência e limites de validação

A versão inicial passou nos testes automatizados Windows e Linux com Python
3.11 e 3.14; também foi validada localmente em macOS com Python 3.14. Isso testa
a aplicação, não a instalação de serviços, firewall, suspensão ou permissões
específicas de cada máquina. Os modelos de LaunchAgent e systemd são opcionais
e devem ser conferidos no computador de destino.

Acompanhe espaço de banco, comprovantes, backups e logs conforme o
[guia de recursos](RECURSOS_E_MANUTENCAO.md). Os arquivos legítimos de operações
não são descartáveis para liberar espaço.
