# Regras de Negócio Financeiras

Este documento é normativo para o projeto.

## 1. Independência dos empréstimos

Um cliente pode possuir vários empréstimos simultâneos. Cada contrato mantém saldo, taxa, movimentos e status próprios.

Nenhum pagamento deve ser lançado apenas contra o cliente; ele precisa indicar exatamente o empréstimo afetado.

## 2. Principal

`valor_original_centavos` representa o principal inicialmente emprestado.

`saldo_atual_centavos` representa somente o principal ainda não abatido.

## 3. Juros

O juro mensal é calculado sobre o saldo principal vigente para a competência.

Exemplo:

```text
Saldo: R$ 10.000,00
Taxa: 5%
Juros: R$ 500,00
Saldo após juros: R$ 10.000,00
```

Regras:

- juro não altera o saldo principal;
- o pagamento de juros deve ser integral;
- não fracionar o juro da mesma competência;
- no máximo um movimento `JUROS` por empréstimo/competência;
- após abatimento, o próximo juro usa o novo saldo.

## 4. Abatimento

Abatimento é pagamento parcial do principal.

Pode existir mais de um abatimento na mesma competência/mês.

Exemplo:

```text
Saldo inicial: R$ 10.000,00
Abatimento 1: R$ 300,00
Abatimento 2: R$ 700,00
Saldo final: R$ 9.000,00
```

## 5. Quitação

Quitação é o pagamento integral do saldo principal restante.

Ao quitar:

```text
saldo_atual_centavos = 0
status = QUITADO
```

Pagamento menor que o saldo é `ABATIMENTO`, não "quitação parcial".

## 6. Status

Em termos financeiros:

```text
saldo > 0  -> contrato em aberto
saldo = 0  -> contrato quitado
```

O campo de status deve permanecer coerente com o saldo.

## 7. Origem e destino bancário

Empréstimo:

```text
origem  = conta própria
destino = conta do cliente
```

Recebimentos de juros, abatimentos e quitação:

```text
origem  = conta do cliente
destino = conta própria
```

Toda movimentação deve preservar o `conta_origem_id` e `conta_destino_id`, além do snapshot dos dados bancários relevantes para que alterações posteriores no cadastro não reescrevam a história.

## 8. Dinheiro

Todos os valores monetários são persistidos como número inteiro de centavos.

```text
R$ 1.234,56 -> 123456
```

Para entrada/conversão, usar `Decimal` quando necessário. Não persistir valores financeiros em `float`.

## 9. Imutabilidade e correção

Movimentações financeiras já lançadas não devem ser editadas nem removidas por padrão.

Se existir no futuro uma função de correção:

1. exigir a senha do usuário atualmente logado;
2. validar a senha contra o hash armazenado;
3. registrar valor anterior e novo valor em auditoria;
4. registrar usuário, data/hora e motivo;
5. recalcular os efeitos no contrato dentro de uma transação;
6. nunca apagar silenciosamente o histórico original.
