"""Juros simples de atraso sobre o juro mensal, nunca sobre o principal."""
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json

from money import MAX_CENTAVOS


def calcular(titulo, data_pagamento):
    t = dict(titulo)
    if not isinstance(data_pagamento, date):
        raise ValueError('Informe uma data válida para calcular o atraso.')
    if t.get('data_emprestimo') and data_pagamento < date.fromisoformat(t['data_emprestimo']):
        raise ValueError('A data de pagamento não pode anteceder o empréstimo.')
    base = t.get('valor_base_centavos')
    if base is None:
        base = int(t['valor_previsto_centavos'])
        if t.get('ajuste_manual') and t.get('saldo_base_centavos') is not None and t.get('taxa_juros_mensal') is not None:
            mensal = int((Decimal(t['saldo_base_centavos']) * Decimal(str(t['taxa_juros_mensal']))
                          / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            if mensal != base:
                raise ValueError(f"O título #{t.get('id')} tem ajuste antigo sem discriminação. "
                                 "Confira o juro original e o vencimento na correção do título "
                                 "antes de calcular novo atraso; o valor antigo foi preservado.")
    vencimento = t.get('data_base_atraso') or t['data_vencimento']
    dias = max(0, (data_pagamento - date.fromisoformat(vencimento)).days)
    adicional = int((Decimal(base) * Decimal(dias) / Decimal(30)).quantize(
        Decimal('1'), rounding=ROUND_HALF_UP))
    total = int(base) + adicional
    if base < 0 or total > MAX_CENTAVOS:
        raise ValueError('Valor fora do limite suportado.')
    return dict(titulo_id=t.get('id'), emprestimo_id=t['emprestimo_id'],
                competencia=t.get('competencia'), cliente_nome=t.get('cliente_nome'),
                valor_base_centavos=int(base), data_base_atraso=vencimento,
                vencimento_anterior=t['data_vencimento'], dias_atraso=dias,
                juros_atraso_centavos=adicional, valor_total_centavos=total,
                data_calculo_atraso=data_pagamento.isoformat())


def assinatura(itens):
    return sha256(json.dumps(itens, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def totais(itens):
    result = {key: sum(i[key] for i in itens) for key in
              ('valor_base_centavos', 'juros_atraso_centavos', 'valor_total_centavos')}
    return result


def gravar_calculo(db, titulo_id, calculo, *, novo_vencimento=None):
    """Persiste uma previsão/baixa apenas dentro da transação do chamador."""
    db.execute('''UPDATE titulos_receber SET valor_base_centavos=?,
        data_base_atraso=?, dias_atraso=?, juros_atraso_centavos=?,
        data_calculo_atraso=?, valor_previsto_centavos=?,
        data_vencimento=COALESCE(?,data_vencimento), ajuste_manual=1,
        updated_at=CURRENT_TIMESTAMP WHERE id=? AND status IN ('PREVISTO','VENCIDO')''',
        (calculo['valor_base_centavos'],calculo['data_base_atraso'],calculo['dias_atraso'],
         calculo['juros_atraso_centavos'],calculo['data_calculo_atraso'],
         calculo['valor_total_centavos'],novo_vencimento,titulo_id))


def snapshot(calculo):
    return {k: calculo[k] for k in ('valor_base_centavos','data_base_atraso',
            'dias_atraso','juros_atraso_centavos','data_calculo_atraso')}
