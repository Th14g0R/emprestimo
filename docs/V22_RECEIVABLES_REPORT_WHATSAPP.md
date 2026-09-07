# V22 — Relatório de contas a receber por cliente e WhatsApp

## Relatório

Rota:

```text
/receber/relatorio
```

Filtros:

- cliente;
- situação:
  - em aberto;
  - pendentes;
  - vencidos;
  - parciais;
  - pagos;
  - cancelados;
  - todos;
- vencimento inicial;
- vencimento final.

## LGPD / minimização

O cabeçalho do relatório exibe somente:

- nome do cliente;
- situação filtrada;
- período.

Não exibe:

- CPF;
- telefone;
- endereço;
- e-mail;
- dados bancários do cliente.

O telefone cadastrado só é usado internamente para montar o link `wa.me`.

## Totais

O relatório apresenta:

- quantidade de títulos;
- valor total dos títulos;
- valor recebido;
- saldo em aberto.

## Mensagem de cobrança

A mensagem é criada somente com títulos efetivamente em aberto
(`PREVISTO` / `VENCIDO`).

Conteúdo:

- nome do cliente;
- vencimento;
- natureza do título;
- competência;
- número do empréstimo;
- valor ainda devido;
- situação;
- total a receber;
- PIX opcional.

O texto é neutro e inclui orientação para desconsiderar caso o pagamento já
tenha sido realizado.

## PIX

Pode ser selecionada:

- uma chave PIX de conta própria já cadastrada;
- uma chave manual digitada apenas para aquela mensagem.

A chave manual não é salva no banco.

## WhatsApp

Utiliza o padrão oficial:

```text
https://wa.me/<numero>?text=<mensagem-url-encoded>
```

Se não houver telefone válido no cadastro:

```text
https://wa.me/?text=<mensagem-url-encoded>
```

e o WhatsApp permite escolher o contato.
