# V20 — Edição do nome do cartão

## Alteração

A entidade `cartoes_credito` mantém o campo SQLite `descricao` para preservar
compatibilidade com o banco existente.

Na interface o campo passa a ser apresentado como:

```text
Nome do cartão
```

## Fluxo

Na lista de cartões:

```text
Abrir
Editar
```

Na ficha do cartão:

```text
Editar cartão
```

A edição permite alterar somente o nome/identificação do cartão.

Não são alterados:

- cliente proprietário;
- lançamentos;
- parcelas;
- valores;
- vencimentos;
- pagamentos.

## Segurança e auditoria

A alteração exige:

- motivo;
- senha do usuário logado.

A auditoria registra o nome anterior e o novo nome.

Nenhuma migração de banco é necessária.
