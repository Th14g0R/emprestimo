# Agenda de recebimentos e projeção de juros

`movimentacoes_emprestimo` continua representando apenas fatos financeiros já realizados.
As previsões ficam separadas em `titulos_receber`.

## Status
- PREVISTO: futuro e ainda não recebido.
- VENCIDO: vencido e ainda não recebido.
- RECEBIDO: confirmado e vinculado a uma movimentação JUROS.
- CANCELADO: não deve mais ser cobrado.

## Geração automática
Ao abrir Dashboard ou A Receber, o sistema sincroniza títulos de juros do mês atual e dos dois meses seguintes, respeitando `data_primeiro_vencimento` e `dia_vencimento`.
Competências já lançadas manualmente não recebem um novo título aberto.

## Valor projetado
Enquanto PREVISTO, acompanha `saldo atual × taxa mensal`.
Depois de VENCIDO, o valor fica congelado para não mudar retroativamente por abatimentos posteriores.

## Confirmação
O usuário abre o título, confirma data, banco/conta de origem, banco/conta de destino e observação. O valor de juros permanece integral. Ao confirmar, é criada a movimentação real JUROS e o título passa a RECEBIDO.

## Indicadores
Dashboard e Agenda mostram semana atual, próxima semana, mês atual e próximo mês, com juros previstos, falta receber, juros recebidos e total recebido (juros + abatimentos + quitações).
