# Instalação da versão 2 no macOS

Este guia instala o sistema para uso real, na branch `release/v2`, sem dados
fictícios. Funciona com o mesmo Flask, Waitress e SQLite da versão Windows.
O arquivo `Gerenciar-Emprestimo.bat` é exclusivo do Windows e não deve ser usado
no Mac. Os comandos abaixo são executados no aplicativo **Terminal**.

## 1. Preparar Python e Git

Instale Python 3.14 pelo [instalador oficial para macOS](https://www.python.org/downloads/macos/).
Abra o `.pkg` e siga o instalador. Depois, abra `Install Certificates.command`
na pasta `/Applications/Python 3.14/`, conforme a
[documentação do Python](https://docs.python.org/3/using/mac.html).
Não remova nem substitua o Python fornecido pela Apple.

Feche e reabra o Terminal e confira:

```sh
python3.14 --version
git --version
```

Se Git não estiver disponível, execute `xcode-select --install`, conclua a
instalação das ferramentas da Apple e repita `git --version`.
Se já possui outro Python 3.10 ou superior instalado, pode usá-lo no lugar de
`python3.14` para criar o ambiente abaixo. A versão usada deve aparecer em
`--version`; não assuma que `python3` é o Python recém-instalado.

## 2. Baixar o código e instalar as dependências

Escolha uma pasta local permanente, fora de iCloud Drive, Dropbox ou pasta de
rede. Este exemplo usa `Aplicativos` dentro da sua pasta pessoal:

```sh
mkdir -p "$HOME/Aplicativos"
cd "$HOME/Aplicativos"
git clone --branch release/v2 --single-branch https://github.com/Th14g0R/emprestimo.git emprestimo-v2
cd emprestimo-v2
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
```

Execute o clone apenas na primeira instalação. Se a pasta já contém o sistema,
siga a seção de atualização. O ambiente `.venv` é criado neste Mac; não copie
um ambiente virtual do Windows, Linux ou de outra instalação.

## 3. Iniciar e acessar

Na pasta `emprestimo-v2`, execute:

```sh
.venv/bin/waitress-serve --listen=127.0.0.1:5000 --threads=4 wsgi:application
```

Mantenha o Terminal aberto. No navegador do mesmo Mac, acesse:

**http://127.0.0.1:5000**

Crie o primeiro administrador. Não há login, senha ou clientes pré-cadastrados.
Se restaurou um banco com usuários, use as credenciais desse banco. Confira a
versão em `http://127.0.0.1:5000/health`.

Para parar, pressione **Control + C** no Terminal do servidor. Para voltar a
abrir em outro dia:

```sh
cd "$HOME/Aplicativos/emprestimo-v2"
.venv/bin/waitress-serve --listen=127.0.0.1:5000 --threads=4 wsgi:application
```

Esse modo já utiliza o servidor Waitress. `python app.py` e `teste_local.py`
são alternativas de desenvolvimento, não os comandos deste guia de operação.

## 4. Opcional: iniciar automaticamente ao fazer login

Este exemplo usa um **LaunchAgent** do seu usuário. Ele inicia após seu login,
continua sem Terminal aberto e encerra ao sair da sessão. Não é um serviço que
inicia antes do login. Para disponibilidade contínua, o Mac deve permanecer
ligado e sem suspensão; um servidor Linux/Windows pode ser mais apropriado.

Primeiro, pare o processo manual com Control + C. Depois, na pasta do projeto,
copie e execute todo o bloco abaixo, incluindo a última linha `PY`:

```sh
cd "$HOME/Aplicativos/emprestimo-v2"
.venv/bin/python - <<'PY'
from pathlib import Path
import plistlib

project = Path.cwd()
runner = project / '.venv/bin/waitress-serve'
if not runner.is_file():
    raise SystemExit('Execute na pasta do projeto, após instalar as dependências.')
plist = Path.home() / 'Library/LaunchAgents/br.com.emprestimo.v2.plist'
plist.parent.mkdir(parents=True, exist_ok=True)
config = {
    'Label': 'br.com.emprestimo.v2',
    'ProgramArguments': [str(runner), '--listen=127.0.0.1:5000',
                         '--threads=4', 'wsgi:application'],
    'WorkingDirectory': str(project),
    'EnvironmentVariables': {'EMPRESTIMO_DATA_DIR': str(project / 'data')},
    'RunAtLoad': True,
    'KeepAlive': True,
    'ThrottleInterval': 10,
}
with plist.open('wb') as stream:
    plistlib.dump(config, stream)
print(f'Criado: {plist}')
PY
plutil -lint "$HOME/Library/LaunchAgents/br.com.emprestimo.v2.plist"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/br.com.emprestimo.v2.plist"
```

O plist utiliza caminhos absolutos da instalação. Se mover a pasta, pare o
agente, recrie o ambiente virtual no destino e gere o plist novamente.
O exemplo usa `data` dentro do projeto; se já utiliza diretório externo,
substitua o valor de `EMPRESTIMO_DATA_DIR` pelo caminho desse diretório antes
de carregar o agente. O agente não herda os `export` do Terminal.

Consultar:

```sh
launchctl print "gui/$(id -u)/br.com.emprestimo.v2"
```

Parar e descarregar antes de atualizar ou fazer backup:

```sh
launchctl bootout "gui/$(id -u)/br.com.emprestimo.v2"
```

Iniciar novamente:

```sh
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/br.com.emprestimo.v2.plist"
```

Para desativar também nos próximos logins, depois de `bootout`, mova o arquivo
`br.com.emprestimo.v2.plist` de `~/Library/LaunchAgents` para uma pasta de backup.
Não apague os dados do sistema.

Este exemplo não redireciona stdout/stderr para arquivos, evitando logs locais
sem rotação; portanto, não mantém histórico desses erros. Para diagnosticar
uma falha, descarregue o agente e execute o comando manual da seção 3 para ver
a mensagem no Terminal. Se optar por guardar logs em arquivos, configure sua
rotação e retenção antes de deixá-los ativos continuamente.

## 5. Atualização, backup e restauração

1. Pare a execução manual ou descarregue o LaunchAgent.
2. Siga o [guia de backup e atualização](INSTALACAO.md#backup-e-atualização).
3. Inicie o sistema pelo mesmo método que utilizava e confira o `/health`.

Banco, chave de sessão e comprovantes ficam em `data`, salvo configuração
externa. Não use `data/local-test` como banco oficial por engano.

## Problemas comuns

- **Porta ocupada:** verifique `lsof -nP -iTCP:5000 -sTCP:LISTEN`. Pare a instância
  anterior do sistema ou escolha `--listen=127.0.0.1:5002` e abra a porta 5002.
  O serviço AirPlay também pode ocupar a porta 5000 em alguns Macs.
- **ModuleNotFoundError:** volte à pasta do projeto e reinstale pelo Python
  da `.venv`; usar o Python global não instala os pacotes no ambiente do sistema.
- **Erro de certificado no pip:** confira o passo `Install Certificates.command`.
- **Agente já carregado:** use `launchctl print`; não execute `bootstrap` duas
  vezes. Descarregue antes de alterar a configuração.
- **Página inacessível de outro computador:** o endereço 127.0.0.1 aceita apenas
  o próprio Mac. Veja [acesso pela rede](INSTALACAO.md#acesso-pela-rede).

Referências: [Waitress](https://docs.pylonsproject.org/projects/waitress/en/stable/runner.html),
[LaunchAgents da Apple](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)
e `man launchctl` no próprio macOS.
