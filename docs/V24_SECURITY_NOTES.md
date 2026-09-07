# V24 — Notas de segurança

## Enumeração de CPF

A V23 usava mensagem genérica. A V24, por requisito de negócio, informa quando não há cliente ativo para o CPF. Isso melhora UX, mas permite testar se um CPF está cadastrado. Antes de publicar o portal na internet, adicionar rate limiting e preferencialmente CAPTCHA.

## E-mail duplicado

Foi corrigido o fluxo que consultava `cliente_id OR email`. Agora um e-mail já vinculado a outro cliente é detectado explicitamente e nunca reaproveita o ID de acesso de terceiro.

## Senhas

Alteração de credenciais pelo administrador exige a senha atual do administrador, nova senha do cliente com 10+ caracteres e usa `generate_password_hash`. A auditoria registra apenas se a senha foi alterada, nunca a senha/hash.

## Upload

O `accept` do navegador é apenas UX. A validação real é no servidor, com allow-list, assinatura do arquivo, Pillow para imagens, nome UUID e diretório privado fora de `static`.
