# V17 — Correção do HTTP 500 e sincronização exata da instalação

## Erro do pagamento integrado

O item manual carregava `data_vencimento` como `datetime.date`. Na auditoria,
`json.dumps()` recebia esse objeto e lançava:

```text
TypeError: Object of type date is not JSON serializable
```

A exceção acontecia antes do `commit` e não era capturada pelo bloco anterior,
por isso Flask devolvia HTTP 500.

A V17:

- converte date/datetime para ISO na auditoria;
- executa rollback para qualquer exceção inesperada;
- registra o traceback no log do serviço;
- retorna mensagem controlada na própria tela.

## Divergência entre C:\TEMP e C:\ProgramData

O gerenciador antigo comparava apenas os commits. Se `HEAD == origin/main`, ele
não executava `git reset --hard`. Portanto uma cópia manual de `app.py` podia
deixar a pasta instalada diferente mesmo com o mesmo commit.

A V17 verifica também o working tree e o hash Git de `app.py`.

Ao atualizar:

1. `git fetch`;
2. compara commit local/remoto;
3. verifica alterações locais;
4. cria backup de `data`;
5. `git reset --hard origin/main`;
6. `git clean -fd`;
7. valida hash de `app.py`;
8. repara/reinicia o serviço;
9. valida novamente os arquivos;
10. consulta `/health`.

## Nova opção do gerenciador

```text
5 - Verificar versão/arquivos instalados
```

Mostra commit, alterações locais, hash de `app.py` e a versão efetivamente
carregada pelo serviço.

## Health

```json
{
  "status": "ok",
  "database": "ok",
  "version": "17.0-integrated-partial-runtime-fix"
}
```
