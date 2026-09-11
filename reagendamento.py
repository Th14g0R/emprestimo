"""Planejamento de alterações de vencimento, sem efeitos no principal."""
import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP


def planejar(titulos, *, nova_data=None, dia=None, proporcional=False):
    if bool(nova_data) == bool(dia):
        raise ValueError("Informe uma data única OU um dia mensal.")
    if dia is not None and not 1 <= dia <= 31:
        raise ValueError("O dia mensal deve estar entre 1 e 31.")
    resultado, primeiros = [], set()
    for t in sorted(titulos, key=lambda t: (t['data_vencimento'], t['id'])):
        if t['status'] not in {'PREVISTO', 'VENCIDO'} or t['natureza'] != 'JUROS':
            raise ValueError("Selecione somente títulos de juros em aberto, sem saldos parciais.")
        antiga = date.fromisoformat(t['data_vencimento'])
        nova = nova_data or antiga.replace(day=min(dia, calendar.monthrange(antiga.year, antiga.month)[1]))
        if nova < date.fromisoformat(t['data_emprestimo']):
            raise ValueError("O vencimento não pode anteceder o empréstimo.")
        dias = (nova - antiga).days
        adicional = 0
        if proporcional and t['emprestimo_id'] not in primeiros:
            if dias <= 0:
                raise ValueError("O ajuste proporcional exige adiamento do primeiro título de cada empréstimo.")
            mensal = (Decimal(t['saldo_base_centavos']) * Decimal(str(t['taxa_juros_mensal'])) / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            adicional = int((mensal * dias / 30).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        primeiros.add(t['emprestimo_id'])
        resultado.append(dict(titulo=dict(t), nova_data=nova.isoformat(), dias=dias,
                              adicional=adicional, valor=t['valor_previsto_centavos'] + adicional))
    if not resultado:
        raise ValueError("Selecione pelo menos um título.")
    return resultado
