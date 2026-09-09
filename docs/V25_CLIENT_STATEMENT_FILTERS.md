# V25 — Extrato do cliente com filtros

## Nova rota

```text
/portal/extrato
```

A rota não aceita `cliente_id` por query string. O cliente é sempre resolvido a
partir da sessão autenticada e aprovada.

## Navegação

O portal passa a ter:

```text
Minha posição
Extrato
Comprovantes
```

Na página `Minha posição` também existe o botão `Ver extrato`.

## Filtros

### Situação dos títulos

- Todos;
- Em aberto;
- Pendentes / a vencer;
- Atrasados;
- Pagos;
- Pagos parcialmente;
- Contratos liquidados.

### Período

- Mês atual;
- Ano atual;
- Escolher ano;
- Período personalizado;
- Histórico completo.

### Contrato

É possível restringir o extrato a um único empréstimo do cliente.

### Movimento

- Todos;
- Juros pagos;
- Abatimentos;
- Quitações;
- Empréstimos recebidos.

## Títulos

Mostra:

- vencimento;
- contrato;
- competência;
- natureza do documento;
- valor;
- valor recebido;
- saldo em aberto;
- situação;
- data do recebimento.

Títulos `PARCIAL` não são novamente contabilizados como saldo em aberto porque o
saldo residual é representado pelo documento `SALDO_JUROS` criado pelo sistema.

## Histórico de movimentações

Mostra:

- data efetiva;
- contrato;
- tipo de movimento;
- competência;
- valor;
- saldo principal após a movimentação;
- indicação de pagamento consolidado;
- indicação de comprovante confirmado.

Não são exibidos:

- contas bancárias internas;
- chaves PIX;
- observações administrativas;
- usuário administrativo;
- dados de outros clientes.

## Resumo

Cards:

- total pago no período;
- juros pagos;
- principal pago;
- em aberto;
- atrasado;
- crédito recebido.

## Impressão

A tela pode ser impressa/salva em PDF. O formulário de filtros e os controles
administrativos não são impressos.
