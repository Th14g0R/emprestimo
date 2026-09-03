# V15 — Títulos em aberto + Pagamentos integrados + filtros por período

## Objetivo

Corrigir a integração entre a Agenda (`titulos_receber`) e os Pagamentos
Integrados.

A previsão de juros continua separada da movimentação realizada:

- `titulos_receber`: previsão / documento em aberto;
- `movimentacoes_emprestimo`: recebimento efetivamente realizado;
- `pagamentos_integrados`: transferência bancária única;
- `pagamentos_integrados_itens`: rateio da transferência por empréstimo.

## Pagamento integrado

Ao selecionar um cliente, a tela passa a mostrar duas fontes de rateio:

1. **Títulos em aberto**
   - status PREVISTO ou VENCIDO;
   - valor e competência vêm do título;
   - ao confirmar o pagamento, o título vira RECEBIDO;
   - é criada uma movimentação JUROS no empréstimo correspondente.

2. **Lançamentos manuais**
   - usados para juros retroativos que ainda não possuem título;
   - competência e valor são informados no momento do pagamento;
   - o saldo histórico é reconstruído e o juro integral é validado.

Se o usuário tentar criar manualmente uma competência que já possui título em
aberto, o sistema orienta a selecionar o título existente.

A soma dos itens precisa ser exatamente igual ao valor recebido.

## Rastreabilidade dos rateios

`pagamentos_integrados_itens` passa a possuir:

- `titulo_receber_id`: referência ao título usado, quando houver;
- `origem_item`: `TITULO` ou `MANUAL`.

Para bancos antigos, as colunas são adicionadas automaticamente por
`migrate_schema()`.

## Alteração e exclusão de título em aberto

Títulos PREVISTO/VENCIDO possuem:

- Alterar;
- Excluir.

Ambas as operações exigem:

- senha do usuário atualmente logado;
- motivo.

Alteração permite corrigir:

- competência;
- vencimento;
- valor previsto;
- observação.

O valor continua sujeito à regra de juro integral.

Quando um título futuro é alterado manualmente, `ajuste_manual=1` impede a
sincronização automática de sobrescrever a correção.

A exclusão operacional usa status `CANCELADO`, em vez de DELETE físico, para:

- impedir recriação automática da mesma previsão;
- preservar auditoria.

## Filtros por período

### A Receber

Novos filtros:

- Data inicial;
- Data final.

O período manual tem prioridade sobre os atalhos:

- Semana atual;
- Próxima semana;
- Mês atual;
- Próximo mês.

### Movimentações

O filtro mensal foi substituído visualmente por:

- Data inicial;
- Data final.

A rota continua aceitando `mes=AAAA-MM` para compatibilidade com links antigos.

## Tela de Movimentações

As 13 colunas anteriores foram agrupadas em 8:

1. Data;
2. Cliente / contrato;
3. Movimento / competência;
4. Valor;
5. Saldo (antes/depois);
6. Fluxo financeiro (origem/destino);
7. Detalhes (usuário/observação/integrado);
8. Ações.

PIX longos são truncados visualmente, mantendo o valor completo no atributo
`title`.

## Transação

Pagamento integrado, itens, movimentações e baixa dos títulos continuam sendo
gravados em uma única transação SQLite. Se qualquer etapa falhar, a aplicação
executa rollback e não deixa rateio parcial.
