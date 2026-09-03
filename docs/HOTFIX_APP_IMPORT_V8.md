# HOTFIX V8 — Validação de importação do app.py

## Sintoma

Após instalar todas as dependências, a validação mostrava:

```text
File "<string>", line 1
    import app; print(Aplicacao
                     ^
SyntaxError: '(' was never closed
```

## Causa

O instalador executava:

```powershell
python.exe -c 'import app; print("Aplicacao importada com sucesso")'
```

No Windows PowerShell 5.1, a passagem de argumentos para programas nativos usa
regras legadas. As aspas internas necessárias ao `print()` podiam ser removidas
antes de chegarem ao Python.

## Solução

A validação agora executa somente:

```text
python.exe -c "import app"
```

Conceitualmente, o `print()` nunca foi necessário. O retorno do próprio Python
é a validação:

- exit code 0: `app.py` importou corretamente;
- exit code diferente de 0: existe erro de sintaxe, importação, dependência ou
  inicialização.

Também são verificados previamente:

- `.venv\Scripts\python.exe`;
- `app.py`.

Isso elimina completamente as aspas internas do código Python usado nessa etapa.


## Recuperação de tentativa incompleta

Se a instalação anterior falhou depois do `git clone`, a pasta de destino já
contém arquivos. O instalador V8 reconhece uma tentativa do próprio projeto
somente quando encontra simultaneamente:

- `.git`;
- `app.py`;
- `requirements.txt`.

Nesse caso oferece remover a instalação incompleta e refazer o processo.

Se a pasta não tiver essa assinatura, não apaga nada e exige que o usuário
escolha outro destino.
