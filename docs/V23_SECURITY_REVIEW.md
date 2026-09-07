# V23 — Revisão de segurança

## Fortalecido
- cookie HttpOnly/SameSite já existente; sessão autenticada limitada a 8h; Secure quando HTTPS está habilitado;
- headers `nosniff`, `SAMEORIGIN`, `Referrer-Policy`, `Permissions-Policy`, CSP básica e HSTS em HTTPS;
- páginas autenticadas com `Cache-Control: no-store`;
- portal depende de senha + aprovação; CPF sozinho não libera acesso;
- bloqueio temporário após falhas repetidas no login do portal;
- upload com allow-list, assinatura, limite 5 MB, UUID e armazenamento fora do webroot;
- comprovante não dá baixa automaticamente.

## Riscos remanescentes
### Alto
1. **Não expor Waitress/porta 5000 diretamente na internet.** Use HTTPS + reverse proxy, `EMPRESTIMO_HTTPS=1`, `EMPRESTIMO_TRUSTED_HOSTS` e `EMPRESTIMO_BEHIND_PROXY=1` somente com proxy confiável.
2. **Login administrativo ainda sem MFA e rate limiter dedicado.** Para acesso público, adicionar MFA/TOTP e limitação de tentativas no proxy/aplicação.

### Médio
3. PDFs não passam por antivírus/CDR. Para ambiente público, adicionar scanner antimalware.
4. Backups SQLite contêm dados pessoais/financeiros: restringir ACL, criptografar e definir retenção.
5. Revisar logs para evitar CPF, PIX, senhas ou conteúdo de comprovante.
6. Formalizar aviso de privacidade, finalidade/base legal, retenção dos comprovantes e processo de incidente LGPD.
7. SQLite é adequado a baixo volume; crescimento/concorrência podem exigir PostgreSQL e armazenamento de objetos.
