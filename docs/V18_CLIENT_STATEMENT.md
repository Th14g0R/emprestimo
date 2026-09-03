# V18 — Extrato financeiro por cliente

## Objetivo

Concentrar em uma única tela:

- todos os empréstimos do cliente;
- total histórico emprestado;
- principal ainda emprestado;
- juros/documentos em aberto;
- total a receber;
- conferência de meses sem pagamento;
- comparação competência x mês efetivo do pagamento;
- extrato cronológico de todas as movimentações.

## Rota

```text
/relatorios/clientes
```

Menu:

```text
Extrato
```

## Posição financeira

São exibidos quatro indicadores:

1. Total histórico emprestado.
2. Principal em aberto.
3. Juros/documentos PREVISTO/VENCIDO em aberto.
4. Total a receber = principal em aberto + juros em aberto.

## Conferência por competência

O relatório não depende somente de `titulos_receber`.

Para cada empréstimo e competência do período:

1. resolve o primeiro vencimento;
2. reconstrói o saldo principal histórico existente no vencimento;
3. calcula o juro esperado pela taxa contratada;
4. soma as movimentações JUROS cuja `competencia` corresponde ao mês;
5. classifica:
   - PAGO;
   - PARCIAL;
   - SEM PAGAMENTO;
   - A MAIOR.

Assim é possível encontrar mês antigo nunca lançado, mesmo sem título automático.

## Conferência por mês do pagamento

Em paralelo, agrupa as movimentações pela `data_movimento`:

- juros recebidos no mês;
- total recebido no mês;
- quantidade de recebimentos;
- situação do caixa.

Isso permite detectar, por exemplo:

```text
Competência 12/2025
paga em 06/01/2026
```

A competência fica paga, mas o recebimento aparece no caixa de janeiro/2026.

## Extrato

O extrato é ordenado cronologicamente e mostra:

- data;
- empréstimo;
- tipo;
- competência;
- mês efetivo do pagamento;
- entrada;
- saída;
- saldo principal consolidado do cliente após o lançamento;
- banco/PIX;
- pagamento integrado.

Movimentações JUROS cuja competência difere do mês de pagamento recebem o
indicador `Pago em outro mês`.

## Impressão

A tela possui:

```text
Imprimir / PDF
```

e CSS específico para impressão, permitindo usar a impressão do navegador para
salvar o extrato em PDF.
