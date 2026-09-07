# V24 — Gestão de acessos e comprovantes consolidados

## Administração dos acessos

A tela `Portal > Acessos` passa a oferecer `Editar` para qualquer acesso.

É possível alterar:
- e-mail de login;
- telefone informado;
- situação: Ativo, Pendente ou Inativo;
- senha do cliente;
- observação administrativa.

A alteração exige a senha do administrador e é gravada na auditoria. O hash da senha do cliente nunca é gravado no detalhe da auditoria.

Internamente `BLOQUEADO` representa acesso inativado administrativamente, preservando a estrutura existente do banco.

## Cadastro público

Quando o CPF válido não corresponde a um cliente ativo, o portal informa explicitamente que o cadastro não foi encontrado. Isso melhora a experiência legítima, mas aumenta o risco de enumeração de CPFs. Para exposição pública, complementar com rate limiting/CAPTCHA.

## Ficha administrativa do cliente

A ficha mostra se existe cadastro no portal, status, e-mail de acesso, último login, se o contato confere e botão para gerenciar o acesso.

## Portal do cliente

Continua somente leitura. O cliente não pode editar cliente, empréstimo, título, cartão ou movimentação. A única ação financeira iniciada pelo cliente é o envio de comprovante para análise administrativa.

## Comprovante consolidado

O cliente pode selecionar vários títulos e enviar um único comprovante. A solicitação fica `Pg. em análise`. Apenas após confirmação do administrador são gerados pagamento integrado, movimentações e baixas.

## Upload

Aceitos somente PDF, PNG e JPEG. Executáveis, ZIP, RAR e demais extensões são recusados.

Imagens são validadas pelo Pillow, limitadas a aproximadamente 20 MP, corrigidas por orientação EXIF, reduzidas a no máximo 1800x1800, convertidas para JPEG otimizado e armazenadas com no máximo 3 MB.

PDF não é alterado e deve ter no máximo 3 MB.
