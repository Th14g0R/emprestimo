# Regras financeiras

Este documento consolida as regras obrigatórias de `AGENTS.md`.

- Cada empréstimo pertence a um cliente e possui saldo independente.
- Todo movimento de empréstimo deve conter `emprestimo_id`.
- EMPRESTIMO constitui o principal. JUROS não altera o principal.
- JUROS é integral por competência mensal. Não criar mais de um lançamento
  JUROS para o mesmo empréstimo e competência.
- ABATIMENTO reduz somente o principal do contrato selecionado e deve ser
  menor que o saldo; QUITACAO corresponde ao saldo restante e encerra o contrato.
- Contratos com saldo principal positivo permanecem ativos.
- Dinheiro é representado por centavos inteiros; cálculos usam Decimal.
- Desembolso: conta própria → conta do cliente. Recebimento: fluxo inverso.
  Movimentos conservam snapshots de banco e PIX.
- Correções financeiras exigem a senha do usuário logado e auditoria.
- Migrações preservam registros existentes. Não apagar nem consolidar
  automaticamente movimentos históricos divergentes.
- Validação de saldo e gravação devem ocorrer na mesma transação, incluindo
  todos os itens de um pagamento. Falha implica rollback.

## Divergência histórica

A versão recebida remove a unicidade de JUROS para permitir recebimentos
parciais. Essa implementação divergia da regra acima. A revisão local impede novos
pagamentos parciais e novas duplicidades sem apagar histórico. Uma mudança
da regra exige decisão explícita; não se deve apagar histórico para impor unicidade.

## Atraso e reagendamento (regra explicitada pelo usuário)

- Adicional = valor original do juro mensal × dias corridos de atraso ÷ 30.
  Usa Decimal e arredondamento HALF_UP apenas no adicional final em centavos.
- Principal não é alterado. Não há capitalização do adicional de atraso.
- Reagendar novamente recalcula desde a mesma data-base e sobre o mesmo valor
  original; não soma o adicional antigo novamente.
- O recebimento calcula até a data efetiva do pagamento, mesmo que tenha havido
  reagendamento. Cada título do grupo tem seu próprio vencimento e atraso.
- Títulos selecionados são recalculados. Com a opção de atualizar próximos,
  títulos futuros não selecionados mudam apenas de dia, conservam o valor e
  passam a usar esse novo vencimento como base; o dia do contrato é atualizado.
- Valor original, data-base, dias, adicional e data de cálculo são conservados
  no título e como snapshot na movimentação e nos itens de pagamento.
- Recebimentos anteriores à atualização não recebem cobranças retroativas.
