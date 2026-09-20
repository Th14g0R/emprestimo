# Produção no Mac: baixar, instalar, importar v1 e atualizar

A partir de **2.1.0+build.2**, a branch `release/v2` inclui um gerenciador próprio
para macOS. Ele funciona fora do VS Code e não depende desta pasta de desenvolvimento.
O site mostra a versão no rodapé; a consulta de atualizações e a troca de versão
ficam no gerenciador local, com confirmação. Não há consultas ao GitHub a cada
acesso de cliente nem uma rota web que execute comandos de atualização.

## 1. Baixar manualmente

1. Abra [release/v2 no GitHub](https://github.com/Th14g0R/emprestimo/tree/release/v2).
2. Clique **Code → Download ZIP** e extraia o ZIP no Finder.
3. Instale Python 3.10+ (preferencialmente 3.14) e Git, conforme os pré-requisitos
   do [guia macOS](DEPLOYMENT_MACOS.md#1-preparar-python-e-git).
4. Abra o Terminal na pasta extraída. Pode digitar `cd `, arrastar a pasta do
   Finder para o Terminal e pressionar Enter. Então execute:

```sh
bash Gerenciar-Emprestimo.command
```

Não é necessário VS Code, ativar ambiente virtual ou instalar pacotes manualmente.
O `.command` localiza um Python compatível. Ele precisa de internet para clonar
`release/v2` e instalar as dependências fixadas; o ZIP é a entrada do gerenciador,
não uma instalação offline. A aplicação instalada depois funciona sem internet.

Para abrir com dois cliques nas próximas vezes, na pasta extraída:

```sh
chmod u+x Gerenciar-Emprestimo.command
```

Abra o arquivo pelo Finder/Terminal conforme as permissões do macOS. Se o sistema
bloquear a execução de um arquivo baixado, prefira o comando explícito no Terminal;
não desative globalmente as proteções do Mac.

## 2. Instalar a versão de produção

Escolha **1 — Instalar / atualizar**. O gerenciador baixa a versão publicada,
cria seu ambiente Python e testa a inicialização em um banco temporário. Só
então mostra o commit preparado e pede que digite **INSTALAR**.

Padrões desta instalação:

| Item | Caminho / comportamento |
| --- | --- |
| Código | `~/Applications/emprestimo-v2/releases/<commit>` |
| Versão ativa | `~/Applications/emprestimo-v2/current` (link para uma release) |
| Banco e comprovantes | `~/Library/Application Support/Emprestimo/data` |
| Backups | `~/Library/Application Support/Emprestimo/backups` |
| Logs | `~/Library/Application Support/Emprestimo/logs` |
| Serviço do usuário | `~/Library/LaunchAgents/br.com.emprestimo.v2.plist` |
| Endereço | **http://127.0.0.1:5002** |

A porta 5002 evita a 5000, que pode estar ocupada pelo sistema no Mac. Se a porta
escolhida estiver ocupada, o gerenciador interrompe o início; não encerra outro
programa. A instalação local aceita apenas `localhost`/`127.0.0.1` e usa HTTP local.
Para publicar em rede/HTTPS, faça uma configuração específica de serviço/proxy;
este gerenciador não reaproveita variáveis do ambiente de desenvolvimento.

A execução usa **Waitress**, com quatro threads, sem debug/reloader. O LaunchAgent
inicia após o login do seu usuário e continua sem Terminal/VS Code aberto. Ele
para no logout; suspensão ou desligamento do Mac também impedem acesso. Não é
um serviço de máquina que inicia antes do login.

Se você pretende importar a v1, **não cadastre clientes ou movimentos na base
nova**. Não é necessário criar um administrador novo: os usuários virão da v1.
Se não tem base anterior, abra o endereço e crie o primeiro administrador.

### Se já seguiu o guia manual anterior

Se o gerenciador encontrar um LaunchAgent com o mesmo nome apontando para outra
pasta, ele não o substitui silenciosamente. Pare a instância anterior, faça backup
dos seus dados e guarde o plist antigo fora de `~/Library/LaunchAgents` antes de
usar o gerenciador. A importação usa uma cópia desse banco; não copie uma `.venv`.
A pasta `current` precisa ser um link criado pelo gerenciador, não um diretório
com uma instalação manual.

## 3. Trazer a base da v1

1. Pare a aplicação v1 na máquina de origem e guarde **uma cópia de toda a pasta
   de dados** em local seguro. Não copie só o `.db` de um sistema ainda aberto.
2. Transfira a cópia para o Mac. Ao lado do banco devem ficar `.secret_key` e a
   pasta `comprovantes`, quando existirem. Não é necessário transferir o ambiente
   Python nem executar a v1 no Mac.
3. No gerenciador v2, escolha **6 — Importar base v1 em instalação vazia** e
   informe o caminho completo de `emprestimos.db`. Você pode arrastar o arquivo
   para conferir seu caminho no Finder; o campo aceita o caminho, não um comando.
4. Confirme **ORIGEM PARADA**. O gerenciador copia o banco pela API SQLite e
   copia os comprovantes/chave para uma pasta temporária privada.
5. A ferramenta `verificar_banco.py` migra uma cópia e confere integridade,
   vínculos e preservação dos valores financeiros. Leia todos os alertas:
   duplicidades históricas, saldos parciais e títulos ajustados sem discriminação
   de atraso exigem conferência. Arquivos de comprovantes ausentes não são
   recriados pelo banco.
6. Se a validação permitir e os alertas estiverem conferidos, digite **IMPORTAR**.
   O gerenciador para a v2, confirma novamente que ela não recebeu cadastros,
   guarda o estado anterior e ativa a cópia importada. A origem v1 é preservada.
7. Abra **http://127.0.0.1:5002** e entre com o usuário/senha que já utilizava.
   Verifique clientes, contratos, saldos, últimos recebimentos e comprovantes.

O importador não mescla bancos e não sobrescreve uma v2 com clientes, empréstimos
ou cartões. Se já começou a operar na v2, pare e planeje a migração dos dados;
não apague tabelas para contornar a proteção. Não opere simultaneamente nas duas
bases durante a troca: movimentos feitos depois da cópia não se transferem sozinhos.

### Conferência operacional antes de usar

- Compare a quantidade de clientes/contratos e os saldos com a v1.
- Confira alguns pagamentos antigos e abra seus comprovantes.
- Confira um título em atraso: original, dias, adicional e total.
- Confira o reagendamento e os próximos vencimentos em uma cópia de teste antes
  de lançar operações apenas para experimentar na base oficial.
- Faça um backup pelo menu e guarde outra cópia fora do Mac.

## 4. Verificar e instalar atualizações

Escolha **2 — Consultar atualizações no GitHub**. A comparação é por commit da
branch `release/v2`, portanto identifica também atualizações só de documentação.
Uma falha de rede é apresentada como falha de consulta, não como “atualizado”.
Nada é instalado por essa opção.

Quando houver atualização, escolha **1**:

1. A versão nova é preparada em outra pasta, com sua própria `.venv`.
2. O banco atual é validado em cópia com o código novo, sem alteração da base oficial.
3. O gerenciador pede **ATUALIZAR** depois de mostrar o resultado.
4. Após confirmar, ele para o serviço, faz backup de banco/chave/comprovantes e
   do código anterior, muda a versão ativa e inicia.
5. Acesse `/health` e confira login e dados. O rodapé identifica a versão da aplicação.

O gerenciador não usa `git reset --hard` nem apaga uma instalação antiga para
atualizar. Releases preparadas/canceladas são reutilizadas pelo commit quando
possível. Cada nova release precisa de espaço para código e dependências.
Não existe limpeza automática de backups ou releases antigos: acompanhe o espaço
e remova cópias somente depois de decidir quais versões precisa manter.

Pode abrir o gerenciador que acompanha a versão ativa:

```sh
bash "$HOME/Applications/emprestimo-v2/current/Gerenciar-Emprestimo.command"
```

Assim você também passa a usar melhorias futuras do próprio gerenciador.

## 5. Operação diária e diagnóstico

No menu: **3** inicia, **4** para, **5** faz backup e **7** mostra os caminhos e
commit instalado. Fazer backup para o serviço durante a cópia e volta a iniciá-lo
se ele estava em execução. Pare também instâncias manuais que usem o mesmo banco.

Para consultar diretamente, sem passar pelo menu:

```sh
bash "$HOME/Applications/emprestimo-v2/current/Gerenciar-Emprestimo.command" verificar
bash "$HOME/Applications/emprestimo-v2/current/Gerenciar-Emprestimo.command" status
```

O log `aplicacao.log` tem rotação de 5 MiB, com três arquivos anteriores (cerca
de 20 MiB no conjunto, mais eventual linha que ultrapasse o limite). Não há logs
por visita nem verificação periódica de atualização consumindo recursos.

```sh
tail -n 80 "$HOME/Library/Application Support/Emprestimo/logs/aplicacao.log"
```

Se a ativação falhar, o gerenciador informa o backup. Não considere a atualização
concluída nem comece a operar antes de corrigir o problema. Não existe rollback
automático que possa apagar movimentações feitas depois da troca.

## 6. Recuperação e caminhos personalizados

Um backup contém `data`, `codigo.zip` e `manifesto.json` com commit e SHA-256 do
banco quando existe uma base. As releases anteriores também ficam no disco.
Pare o serviço e guarde o estado atual antes de restaurar. Restaure código e dados
do mesmo backup em uma pasta nova, recrie o ambiente Python e aponte o serviço
para essa instalação conforme o [guia manual](DEPLOYMENT_MACOS.md). Não misture
um banco restaurado com WAL/SHM da instalação atual. O gerenciador não oferece
sobrescrita automática de uma base usada para executar restauração.

Parâmetros opcionais, definidos já na primeira instalação:

```sh
bash Gerenciar-Emprestimo.command --install-dir "/caminho/codigo" --state-dir "/caminho/estado" --port 5002
```

Use sempre os mesmos parâmetros nas próximas execuções. Código e estado precisam
ser pastas separadas. Os valores ficam em `gerenciador.json` dentro de `state-dir`.
Não altere esse arquivo para mover uma instalação em execução.

## O que esta validação garante

O procedimento pode ser repetido em outros Macs compatíveis e a ferramenta
verifica cada banco fornecido. Os testes automatizados usam bases sintéticas e
estrutura legada; isso **não garante que qualquer banco v1 desconhecido esteja
íntegro ou sem divergências**. Para afirmar que a sua base foi validada, é
necessário executar a conferência nela e realizar a checagem operacional acima.

## Correção do caminho antigo (2.1.1+build.3)

O diretório físico padrão é `~/Applications`, mesmo que o Finder traduza o nome
para “Aplicativos”. Esse é o diretório de aplicações do usuário; `/Applications`
sem `~` é o diretório compartilhado do sistema e não é usado pelo gerenciador.

Se instalou uma versão anterior em `~/Aplicativos`, baixe o gerenciador atualizado
pela branch `release/v2` e escolha **8 — Corrigir caminho antigo**, ou execute
na pasta recém-extraída:

```sh
bash Gerenciar-Emprestimo.command migrar-caminho
```

Ele prepara uma release e um ambiente Python novos em `~/Applications`, pede
confirmação, para o serviço, faz backup e atualiza o LaunchAgent e o registro da
instalação. O banco permanece em `~/Library/Application Support/Emprestimo/data`.
Não basta mover a pasta pelo Finder: o serviço e o ambiente virtual têm caminhos
que precisam ser ajustados.

A cópia antiga fica dentro do backup após a validação do novo serviço. A pasta
`~/Aplicativos` só é removida se não contiver outros arquivos do usuário.
Se `~/Applications/emprestimo-v2` já contém uma instalação manual, a migração
interrompe sem sobrescrevê-la: primeiro pare essa instância e preserve a pasta
inteira em backup. Não mescle bancos de instalações diferentes.
