# V16 — Recebimentos parciais de juros

## Correção do erro 500

Na V15, quando o valor manual informado era diferente do juro integral, o fluxo
entrava na mensagem de validação e chamava uma função inexistente:

```python
format_percent(...)
```

A função real do projeto é:

```python
format_percent_br(...)
```

Por isso, justamente ao informar R$ 200 em um juro integral de R$ 400, ocorria
`NameError` e a requisição terminava em HTTP 500.

A V16 corrige essa chamada e, além disso, muda a regra para permitir recebimento
parcial de juros.

## Regra financeira nova

O juro devido continua sendo calculado integralmente. O que passa a poder ser
parcial é o **recebimento**.

Exemplo:

- juro integral da competência: R$ 400;
- cliente paga agora: R$ 200;
- movimentação JUROS criada: R$ 200;
- documento original: `PARCIAL`;
- novo documento relacionado: `SALDO_JUROS` de R$ 200;
- mesma competência;
- mesmo vencimento.

Depois, ao receber os R$ 200 restantes, o documento de saldo é baixado com uma
segunda movimentação JUROS da mesma competência.

## Estrutura da cadeia

```text
Título #30
JUROS 01/2026
Valor: R$ 400
Status: PARCIAL
Recebido: R$ 200
        |
        +--> Título #31
             SALDO_JUROS 01/2026
             Valor: R$ 200
             Status: VENCIDO/PREVISTO
```

Se o saldo de R$ 200 for novamente pago apenas em R$ 100:

```text
#30 JUROS       R$ 400  PARCIAL (R$ 200 recebidos)
  |
  +-- #31 SALDO R$ 200  PARCIAL (R$ 100 recebidos)
        |
        +-- #32 SALDO R$ 100  VENCIDO/PREVISTO
```

## Pagamento integrado

A tela de pagamento integrado agora permite alterar o campo **Receber agora**
para um título aberto.

Para itens manuais/históricos, o sistema calcula o juro integral devido, mas
aceita um valor menor. Se o valor for menor, cria automaticamente a cadeia de
documentos descrita acima.

O valor não pode ser maior que o saldo devido do juro.

## Banco de dados

A antiga restrição que permitia apenas uma movimentação JUROS por
`emprestimo_id + competencia` foi removida, porque pagamentos parciais precisam
de mais de uma movimentação para a mesma competência.

O índice deixa de ser `UNIQUE` e passa a ser um índice comum para busca.

A tabela `titulos_receber` passa a aceitar múltiplos documentos da mesma
competência e recebe:

- `valor_recebido_centavos`;
- `titulo_origem_id`;
- `natureza` (`JUROS` / `SALDO_JUROS`);
- `sequencia`;
- status `PARCIAL`.

A migração reconstrói somente a tabela `titulos_receber`, preservando IDs e
dados existentes, e recria os índices necessários.

`movimentacoes_emprestimo` recebe `titulo_receber_id` para relacionar cada
recebimento ao documento efetivamente baixado.

## Exclusões

Uma movimentação/pagamento mais antigo não pode ser excluído se um documento de
saldo originado por ele já foi recebido depois. É necessário desfazer a cadeia
do recebimento mais recente para o mais antigo.

Isso evita quebrar a rastreabilidade financeira.

## Cenário validado

```text
Empréstimo #6
Principal histórico: R$ 5.000
Taxa: 8%
Juro 01/2026: R$ 400

06/01/2026 recebido: R$ 200
=> movimento JUROS R$ 200
=> título original PARCIAL
=> novo SALDO_JUROS R$ 200

17/01/2026 recebido: R$ 200
=> segundo movimento JUROS R$ 200
=> documento de saldo RECEBIDO

Total recebido na competência: R$ 400
```
