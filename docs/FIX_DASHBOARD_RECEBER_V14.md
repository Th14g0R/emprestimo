# V14 — Correção Dashboard / A Receber

## Sintoma

As rotas:

- `/dashboard`
- `/receber`

retornavam HTTP 500 depois da inclusão da Agenda de Recebimentos.

## Causa

`get_receivable_periods()` retorna objetos `datetime.date` para:

- início da semana atual;
- fim da semana atual;
- próxima semana;
- mês atual;
- próximo mês.

Os templates aplicam o filtro:

```jinja2
{{ periodo['inicio']|date_br }}
```

O filtro antigo fazia:

```python
date.fromisoformat(value[:10])
```

Esse código funciona quando `value` é texto (`"2026-09-03"`), mas falha quando
`value` é um objeto `date`, pois `date` não suporta slicing.

Exceção:

```text
TypeError: 'datetime.date' object is not subscriptable
```

## Correção

`format_date_br()` agora aceita:

- `None`;
- `str`;
- `datetime.date`;
- `datetime.datetime`.

O banco SQLite, a agenda, os títulos e as movimentações não são alterados.

## Testes de regressão esperados

```text
"2026-09-03"                  -> 03/09/2026
date(2026, 9, 3)              -> 03/09/2026
datetime(2026, 9, 3, 12, 30)  -> 03/09/2026
None                          -> -
```
