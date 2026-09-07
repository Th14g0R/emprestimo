# V23 — Portal do cliente

- Títulos do navegador seguem `Empréstimo | Tela`.
- Cartões na ficha do cliente mostram total, parcelas, pagas, vencimento e saldo.
- `/portal/cadastro` solicita CPF, e-mail, telefone e senha.
- CPF não autentica; o acesso fica `PENDENTE` até aprovação administrativa.
- O administrador revisa em `/acessos-clientes` e confirma com a própria senha.
- O cliente pode enviar comprovantes para títulos em aberto.
- Status: `Pg. em análise`, `Confirmado`, `Rejeitado`.
- O comprovante só gera baixa financeira após confirmação administrativa.
- Arquivos ficam em `data/comprovantes`, fora de `static`, com nome aleatório e validação PDF/PNG/JPEG.
