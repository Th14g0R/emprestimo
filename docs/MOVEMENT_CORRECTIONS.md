# Correção e exclusão de movimentações

Toda alteração ou exclusão exige sessão autenticada, CSRF válido, senha do usuário atualmente logado e motivo obrigatório. A operação é registrada em `auditoria`.

- `EMPRESTIMO`: banco/PIX/observação podem ser corrigidos; valor e data do contrato ficam bloqueados; a movimentação inicial não pode ser excluída isoladamente.
- `JUROS`: data, competência, banco/PIX e observação podem ser corrigidos; valor não é editável porque o juro deve ser integral.
- `ABATIMENTO`: data, valor, banco/PIX e observação podem ser corrigidos; o contrato é recalculado e revalidado.
- `QUITACAO`: data, banco/PIX e observação podem ser corrigidos; valor permanece igual ao saldo integral.

Após alteração/exclusão, o saldo é reconstituído cronologicamente. Se a correção tornar juros, abatimentos ou quitação posteriores inconsistentes, a transação é revertida e nada é gravado.
