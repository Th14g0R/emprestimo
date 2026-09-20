# Desenvolvimento e testes isolados

A versão 2 não inclui gerador de demonstração. Para trabalhar em um banco separado:

```sh
python -m pip install -r requirements.lock
python teste_local.py
```

Abra `http://127.0.0.1:5001` e crie o administrador. O inicializador força banco e
chave em `data/local-test`, independentemente dos caminhos de produção herdados.
Não importa nem cria clientes, contratos ou pagamentos. Dados locais existentes
são preservados.

```sh
python -m unittest discover -s tests -v
```

A suíte usa bancos temporários e fixtures sintéticas, sem depender de backups
privados. Não execute testes apontando variáveis de ambiente para dados reais.
Para conferir um banco antigo, use `scripts/verificar_banco.py`, que migra apenas
uma cópia temporária. Veja [restauração](JUROS_ATRASO_E_RESTAURACAO.md).

Em produção, use Waitress pelo [guia Windows](DEPLOYMENT_WINDOWS.md), sem o
servidor Flask de desenvolvimento. A versão 2 é publicada na branch `release/v2`.
