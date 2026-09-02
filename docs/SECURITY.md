# Segurança

## Dados que não podem ser publicados

- `data/emprestimos.db`;
- `data/.secret_key`;
- WAL/SHM do SQLite;
- backups;
- senhas, tokens e chaves privadas.

O repositório GitHub é público. Considere qualquer arquivo commitado nele como informação potencialmente pública.

## Senhas

Senhas de usuários são persistidas somente em formato de hash utilizando Werkzeug.

## Sessão

A assinatura da sessão Flask depende da `SECRET_KEY`. Em instalação normal ela é criada localmente em `data/.secret_key`, arquivo ignorado pelo Git.

## Operações financeiras

Movimentos financeiros devem ser imutáveis por padrão. Uma eventual rotina de correção precisa exigir novamente a senha do usuário logado e registrar auditoria completa.

## Serviço Windows

O gerenciador tenta executar o serviço sob `LocalService` e concede escrita apenas às pastas de runtime necessárias. Se o site for exposto à rede local, o firewall é liberado apenas para o perfil `Private`.

## Internet

A configuração atual é apropriada para máquina local/rede controlada. Antes de expor o sistema diretamente à Internet, implementar HTTPS, reverse proxy, política de senha, proteção adicional de sessão, cabeçalhos de segurança, rate limiting, backup e revisão de segurança.
