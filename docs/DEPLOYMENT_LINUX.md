# Instalação da versão 2 no Linux

Instalação real da branch `release/v2`, com Python, Waitress e SQLite.
Os comandos de pacotes abaixo são para Ubuntu/Debian. Outras distribuições
precisam dos pacotes equivalentes de Python 3.10+, pip, venv e Git.
O `.bat` e o gerenciador PowerShell do projeto são exclusivos do Windows.

## 1. Instalar os pré-requisitos

No Terminal do usuário que executará a aplicação:

```sh
sudo apt update
sudo apt install python3 python3-venv python3-pip git curl
python3 --version
git --version
```

Confirme Python **3.10 ou superior**. Se a distribuição fornece versão anterior,
use uma versão suportada da distribuição ou instale um Python compatível antes
de continuar. Não execute o sistema como root nem use `sudo pip`.

## 2. Baixar e instalar

O exemplo usa `~/emprestimo-v2`, em disco local:

```sh
cd "$HOME"
git clone --branch release/v2 --single-branch https://github.com/Th14g0R/emprestimo.git emprestimo-v2
cd emprestimo-v2
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
```

Crie a `.venv` neste Linux; ambientes virtuais não são transferíveis de outro
sistema. Não armazene o SQLite em compartilhamento de rede ou pasta sincronizada.
Se a pasta já contém a instalação, use as instruções de atualização.

## 3. Iniciar manualmente e criar o administrador

```sh
cd "$HOME/emprestimo-v2"
.venv/bin/waitress-serve --listen=127.0.0.1:5000 --threads=4 wsgi:application
```

No mesmo computador, abra **http://127.0.0.1:5000**. Crie o primeiro administrador
antes de liberar acesso externo. Não há senha padrão ou exemplos. Se restaurou
um banco, use um usuário existente nele.

O Terminal precisa permanecer aberto. Para parar, pressione **Control + C**.
Em outro Terminal, pode conferir `curl http://127.0.0.1:5000/health`.

Se o Linux está em um servidor remoto via SSH, `127.0.0.1` no navegador do seu
computador não aponta para ele. Para fazer o primeiro acesso sem expor a porta,
abra outro Terminal **no seu computador** e use, substituindo usuário e servidor:

```sh
ssh -L 5001:127.0.0.1:5000 usuario@servidor
```

Mantenha essa sessão aberta e acesse **http://127.0.0.1:5001** no navegador local.

## 4. Opcional: execução automática com systemd

Para distribuições com systemd, este exemplo instala um **serviço de usuário**.
Execute como o mesmo usuário que instalou o projeto. Não use `sudo` nos comandos
`systemctl --user`. Primeiro pare a execução manual com Control + C.

```sh
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/emprestimo.service" <<'UNIT'
[Unit]
Description=Controle de Emprestimos v2

[Service]
Type=simple
WorkingDirectory=%h/emprestimo-v2
ExecStart="%h/emprestimo-v2/.venv/bin/waitress-serve" --listen=127.0.0.1:5000 --threads=4 wsgi:application
Environment="EMPRESTIMO_DATA_DIR=%h/emprestimo-v2/data"
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=5
UMask=0077
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now emprestimo.service
systemctl --user status emprestimo.service
```

Se instalou em outro diretório, altere os três caminhos no arquivo. `%h` é a
pasta pessoal do usuário. Se já usa dados em diretório externo, altere também
`EMPRESTIMO_DATA_DIR`. A aplicação não lê `.env` automaticamente e o serviço
não depende dos `export` da sua sessão: configure as variáveis na unidade.

Para iniciar no boot e continuar após logout, habilite a permanência do
serviço desse usuário (pode exigir um administrador):

```sh
sudo loginctl enable-linger "$USER"
```

Sem essa configuração, não conte com execução independente da sessão do usuário.
Em servidor administrado por outra pessoa, solicite a configuração ao responsável.

Comandos de operação:

```sh
systemctl --user stop emprestimo.service
systemctl --user start emprestimo.service
systemctl --user restart emprestimo.service
journalctl --user -u emprestimo.service -n 100 --no-pager
```

Execute apenas o comando correspondente à ação desejada. Se mudar a unidade,
execute `systemctl --user daemon-reload` antes de reiniciar.

Os logs ficam no journal do sistema; a retenção e o espaço usado dependem da
configuração do journald. O exemplo não cria arquivos de log próprios. Confira
`journalctl --disk-usage` e ajuste a retenção com o administrador; não altere
limites globais de outros serviços sem avaliar o efeito.

Para desativar o início automático e parar:

```sh
systemctl --user disable --now emprestimo.service
```

Isso preserva o código e os dados. `disable-linger` afeta todos os serviços de
usuário; não o utilize sem conferir se há outros serviços que dependem dele.

## 5. Atualização e restauração

Pare o serviço antes de copiar dados ou atualizar. Siga o
[guia comum de backup e atualização](INSTALACAO.md#backup-e-atualização), depois
inicie com `systemctl --user start emprestimo.service` e confira o `/health`.

## Problemas comuns

- **externally-managed-environment:** use `.venv/bin/python -m pip`, não o pip global.
- **Permissão no SQLite:** código e `data` devem pertencer ao usuário do serviço;
  o SQLite também precisa criar WAL/SHM na pasta. Não resolva com `chmod 777`.
- **Porta ocupada:** use `ss -ltnp` para identificar o processo, ou escolha outra
  porta no `--listen`. Não mantenha a execução manual e o serviço na mesma porta.
- **Failed to connect to bus:** execute em uma sessão do próprio usuário com
  systemd disponível. O comando manual funciona sem systemd; um serviço de
  sistema exige configuração pelo administrador.
- **Acesso externo:** veja [rede e HTTPS](INSTALACAO.md#acesso-pela-rede).

Referências: [Waitress](https://docs.pylonsproject.org/projects/waitress/en/stable/runner.html),
[systemd](https://systemd.io/) e os manuais locais `man systemd.service`,
`man systemd.exec`, `man loginctl` e `man journald.conf`.
