# HOTFIX V7 — Validação direta do Python

## Diagnóstico

O Python funciona manualmente tanto no CMD normal quanto no CMD elevado:

```text
python --version
Python 3.14.7
```

Logo, o problema não é instalação, PATH ou UAC. O falso negativo estava em
`Test-PythonCandidate`.

## Correção

A validação agora replica o teste real:

1. executa `<python> --version`;
2. aceita a versão se for Python >= 3.9;
3. executa `<python> -c "import sys; print(sys.executable)"`;
4. utiliza o executável retornado pelo próprio Python;
5. se `--version` funcionar, o Python é considerado válido mesmo que a consulta
   adicional do caminho real falhe.

O `Resolve-Python` testa explicitamente:

- caminho recebido pelo bootstrap;
- `python.exe`;
- `python`;
- `py.exe`;
- `py`;
- Registro e diretórios conhecidos.

O WinGet só é acionado se nenhum desses comandos realmente conseguir executar
Python.
