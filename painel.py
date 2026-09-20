"""Consultas do painel: principal, receita de juros e cartões separados."""
from datetime import date, timedelta


def dashboard_data(db):
    today = date.today()
    end = today + timedelta(days=7)
    overdue = db.execute("""
        SELECT COALESCE(SUM(valor_previsto_centavos),0) AS valor, COUNT(*) AS quantidade
        FROM titulos_receber WHERE status IN ('PREVISTO','VENCIDO') AND data_vencimento < ?
    """, (today.isoformat(),)).fetchone()
    upcoming = db.execute("""
        SELECT COALESCE(SUM(valor_previsto_centavos),0) AS valor
        FROM titulos_receber WHERE status IN ('PREVISTO','VENCIDO')
        AND data_vencimento BETWEEN ? AND ?
    """, (today.isoformat(), end.isoformat())).fetchone()
    cards = db.execute("""
        SELECT COALESCE(SUM(CASE WHEN status IN ('PENDENTE','VENCIDO')
            THEN valor_centavos ELSE 0 END),0) AS aberto,
        COALESCE(SUM(CASE WHEN status='PAGO' AND substr(data_pagamento,1,7)=?
            THEN valor_centavos ELSE 0 END),0) AS recebido
        FROM parcelas_cartao
    """, (today.strftime('%Y-%m'),)).fetchone()
    pending_proofs = db.execute("SELECT COUNT(*) FROM comprovantes_pagamento WHERE status='EM_ANALISE'").fetchone()[0]
    pending_access = db.execute("SELECT COUNT(*) FROM clientes_acessos WHERE status='PENDENTE'").fetchone()[0]
    first_year, first_month = divmod(today.year * 12 + today.month - 1 - 5, 12)
    next_year, next_month = divmod(today.year * 12 + today.month, 12)
    history_start = date(first_year, first_month + 1, 1).isoformat()
    history_end = date(next_year, next_month + 1, 1).isoformat()
    history = dict(db.execute("""SELECT substr(data_movimento,1,7),SUM(valor_centavos)
        FROM movimentacoes_emprestimo WHERE tipo='JUROS'
        AND data_movimento >= ? AND data_movimento < ?
        GROUP BY substr(data_movimento,1,7)""", (history_start, history_end)).fetchall())
    months = []
    for offset in range(5, -1, -1):
        month_index = today.year * 12 + today.month - 1 - offset
        year, month = divmod(month_index, 12)
        key = f'{year:04d}-{month+1:02d}'
        months.append({'mes': key, 'valor': history.get(key, 0)})
    maximum = max((m['valor'] for m in months), default=0)
    for m in months:
        m['altura'] = m['valor'] * 100 // maximum if maximum else 0
    historical = db.execute("""SELECT COUNT(*) FROM (
        SELECT emprestimo_id,competencia FROM movimentacoes_emprestimo
        WHERE tipo='JUROS' GROUP BY emprestimo_id,competencia HAVING COUNT(*)>1
    )""").fetchone()[0]
    historical += db.execute("""SELECT COUNT(*) FROM titulos_receber
        WHERE natureza='SALDO_JUROS' AND status IN ('PREVISTO','VENCIDO')""").fetchone()[0]
    return dict(conflitos_historicos=historical,vencido=overdue['valor'],titulos_vencidos=overdue['quantidade'],
                proximos=upcoming['valor'],inicio=today.isoformat(),fim=end.isoformat(),
                cartoes_aberto=cards['aberto'],cartoes_recebido=cards['recebido'],
                comprovantes_pendentes=pending_proofs,acessos_pendentes=pending_access,
                meses=months)
