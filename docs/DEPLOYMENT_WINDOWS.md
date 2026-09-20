# Instalação e atualização da versão 2 no Windows

Versão 2.0.0+build.1, branch `release/v2`, serviço `Emprestimo`.
O gerenciador e o bootstrap desta branch usam `release/v2`, sem publicar ou
incorporar mudanças na `main`.

## Nova instalação

1. Baixe o código de `release/v2` ou clone essa branch.
2. Execute `Gerenciar-Emprestimo.bat`. Ele localiza Python, solicita elevação
   administrativa e abre o gerenciador PowerShell incluído no projeto.
3. Escolha instalar, diretório, porta e acesso local/rede. O gerenciador clona
   a branch, cria `.venv`, instala dependências fixadas e configura Waitress
   como serviço Windows por meio de WinSW.
4. Acesse localmente a porta configurada e crie o administrador antes de liberar
   o acesso. Não existe conta inicial, senha padrão ou geração de exemplos.
5. Confira `/health`: o campo `version` deve ser `2.0.0+build.1`.

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
