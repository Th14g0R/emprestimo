# Pagamentos integrados

## Problema resolvido

Um cliente pode fazer uma única transferência bancária que quita juros de
vários empréstimos.

Exemplo:

- empréstimo #1: R$ 10.000 a 8% → juros R$ 800;
- empréstimo #2: R$ 5.000 a 8% → juros R$ 400;
- empréstimo #3: R$ 10.000 a 8% → juros R$ 800;
- transferência bancária única: R$ 2.000.

## Modelagem

O sistema cria um `pagamentos_integrados` (cabeçalho) com:

- cliente;
- data;
- total recebido;
- conta de origem;
- conta de destino;
- snapshots de banco/PIX;
- usuário;
- observação.

Os rateios ficam em `pagamentos_integrados_itens`.

Cada item cria uma movimentação real `JUROS` em
`movimentacoes_emprestimo`.

Portanto o histórico individual continua correto:

- empréstimo #1 → JUROS R$ 800 → Pagamento integrado #N;
- empréstimo #2 → JUROS R$ 400 → Pagamento integrado #N;
- empréstimo #3 → JUROS R$ 800 → Pagamento integrado #N.

O pagamento-pai não entra nos somatórios financeiros de movimentações. Os
R$ 2.000 são contabilizados apenas pela soma dos três movimentos-filhos,
evitando duplicidade.

## Regras

- somente empréstimos do mesmo cliente;
- mínimo de dois empréstimos;
- soma dos rateios deve ser exatamente igual ao pagamento recebido;
- uma competência de juros não pode ser duplicada por empréstimo;
- juros continua integral;
- para lançamento histórico o saldo-base é reconstruído pelas movimentações
  de principal anteriores à data do pagamento;
- banco/PIX é único no pagamento e copiado como snapshot para cada movimento;
- gravação é atômica: pagamento, itens e movimentos usam um único commit;
- se qualquer item falhar, rollback de tudo.

## Correção e exclusão

Uma movimentação pertencente a pagamento integrado não pode ser alterada ou
excluída isoladamente, pois quebraria o fechamento do pagamento.

A tela da movimentação aponta para o pagamento integrado.

A exclusão do pagamento integrado:

- exige senha do usuário logado;
- exige motivo;
- remove todos os movimentos-filhos juntos;
- reabre títulos da agenda quando aplicável;
- grava snapshot completo na auditoria.
