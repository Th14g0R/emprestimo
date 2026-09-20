"""Reagendamento com juros simples e propagação do dia sem capitalização."""
import calendar
from datetime import date
import json
import sqlite3

from atrasos import calcular, assinatura, totais, gravar_calculo


def planejar(titulos, *, nova_data=None, dia=None, proporcional=True):
    # proporcional é mantido por compatibilidade de chamada; o adicional agora
    # faz parte da regra obrigatória, não de uma opção oculta no formulário.
    if bool(nova_data) == bool(dia):
        raise ValueError('Informe uma data única OU um dia mensal.')
    if dia is not None and not 1 <= dia <= 31:
        raise ValueError('O dia mensal deve estar entre 1 e 31.')
    resultado=[]
    for row in sorted(titulos,key=lambda t:(t['data_vencimento'],t['id'])):
        t=dict(row)
        t.pop('updated_at',None)
        t.pop('created_at',None)
        if t['status'] not in {'PREVISTO','VENCIDO'} or t['natureza']!='JUROS':
            raise ValueError('Selecione somente títulos de juros em aberto, sem saldos parciais.')
        antiga=date.fromisoformat(t['data_vencimento'])
        nova=nova_data or antiga.replace(day=min(dia,calendar.monthrange(antiga.year,antiga.month)[1]))
        p=calcular(t,nova)
        resultado.append(dict(titulo=t,nova_data=nova.isoformat(),somente_dia=False,
                              dias=p['dias_atraso'],adicional=p['juros_atraso_centavos'],
                              valor=p['valor_total_centavos'],calculo=p))
    if not resultado:
        raise ValueError('Selecione pelo menos um título.')
    return resultado


def incluir_futuros(db, plano, dia):
    selected={p['titulo']['id'] for p in plano}
    limits={}
    for p in plano:
        eid=p['titulo']['emprestimo_id']
        limits[eid]=max(limits.get(eid,date.today().isoformat()),p['titulo']['data_vencimento'])
    following=[]
    for eid,limit in limits.items():
        rows=db.execute('''SELECT t.*, e.data_emprestimo, c.nome AS cliente_nome
            FROM titulos_receber t JOIN emprestimos e ON e.id=t.emprestimo_id
            JOIN clientes c ON c.id=e.cliente_id
            WHERE t.emprestimo_id=? AND t.status IN ('PREVISTO','VENCIDO')
            AND t.data_vencimento>? ORDER BY t.data_vencimento,t.id''',(eid,limit)).fetchall()
        for row in rows:
            if row['id'] in selected:
                continue
            t=dict(row)
            t.pop('updated_at',None)
            t.pop('created_at',None)
            if t['natureza']!='JUROS' or t['juros_atraso_centavos']:
                raise ValueError(f"O título futuro #{t['id']} possui saldo ou adicional próprio. Selecione-o para conferir separadamente.")
            antiga=date.fromisoformat(t['data_vencimento'])
            nova=antiga.replace(day=min(dia,calendar.monthrange(antiga.year,antiga.month)[1]))
            base=int(t['valor_previsto_centavos'])
            p=calcular(dict(t,valor_base_centavos=base,data_base_atraso=nova.isoformat()),nova)
            following.append(dict(titulo=t,nova_data=nova.isoformat(),somente_dia=True,
                                  dias=0,adicional=0,valor=base,calculo=p))
    return plano+following


def reagendar():
    from flask import flash, redirect, render_template, request, url_for
    import app as core
    db=core.get_db()
    plano=[]
    erro=None
    ids=sorted(set(request.form.getlist('titulo_id')))
    automatic=request.headers.get('X-Receivable-Preview')=='1'
    dia_futuro=None
    try:
        if automatic and request.form.get('acao')!='prever':
            raise ValueError('A prévia automática não permite salvar alterações.')
        if not ids or len(ids)>500 or any(not i.isdigit() for i in ids):
            raise ValueError('Selecione entre 1 e 500 títulos válidos.')
        titles=[core.get_titulo_receber_or_404(int(i)) for i in ids]
        if request.form.get('acao') in {'prever','salvar'}:
            raw_date=request.form.get('nova_data','').strip()
            raw_day=request.form.get('dia','').strip()
            new=core.parse_iso_date(raw_date)
            day=core.parse_int(raw_day)
            if raw_date and new is None or raw_day and day is None:
                raise ValueError('Informe uma data ou dia válido.')
            plano=planejar(titles,nova_data=new,dia=day)
            if request.form.get('futuros')=='1':
                dia_futuro=day or new.day
                plano=incluir_futuros(db,plano,dia_futuro)
            # Inclui a opção de propagação na confirmação, mesmo sem futuros existentes.
            token=assinatura(dict(plano=plano,dia_futuro=dia_futuro))
            if request.form.get('acao')=='salvar':
                if not core.validar_senha_usuario_atual(request.form.get('senha_confirmacao','')):
                    raise ValueError('A senha do usuário logado é inválida.')
                motivo=request.form.get('motivo','').strip()
                if len(motivo)<5:
                    raise ValueError('Informe um motivo com pelo menos 5 caracteres.')
                if request.form.get('assinatura')!=token:
                    raise ValueError('A seleção, as datas ou os valores mudaram. Gere e confira uma nova prévia.')
                for p in plano:
                    t=p['titulo']
                    gravar_calculo(db,t['id'],p['calculo'],novo_vencimento=p['nova_data'])
                    db.execute('UPDATE titulos_receber SET status=? WHERE id=?',
                               (core.status_aberto_por_vencimento(p['nova_data']),t['id']))
                    after=db.execute('SELECT * FROM titulos_receber WHERE id=?',(t['id'],)).fetchone()
                    core.registrar_auditoria(db,'titulo_receber',t['id'],
                        'DIA_FUTURO_ALTERADO' if p['somente_dia'] else 'REAGENDADO',
                        json.dumps(dict(motivo=motivo,antes=core.titulo_receber_para_auditoria(t),
                            depois=core.titulo_receber_para_auditoria(after),calculo=p['calculo'],base_dias=30),ensure_ascii=False))
                if dia_futuro:
                    for eid in {t['emprestimo_id'] for t in titles}:
                        antes=db.execute('SELECT dia_vencimento FROM emprestimos WHERE id=?',(eid,)).fetchone()[0]
                        db.execute('UPDATE emprestimos SET dia_vencimento=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(dia_futuro,eid))
                        core.registrar_auditoria(db,'emprestimo',eid,'VENCIMENTO_ALTERADO',
                            json.dumps(dict(motivo=motivo,antes=antes,depois=dia_futuro)))
                db.commit()
                flash('Reagendamento confirmado. Adicionais detalhados; principal e valores dos próximos títulos preservados.','success')
                return redirect(url_for('titulos_receber_lista'))
    except (ValueError,sqlite3.DatabaseError) as exc:
        db.rollback()
        erro=str(exc)
        if not automatic:
            flash(erro,'danger')
    token=assinatura(dict(plano=plano,dia_futuro=dia_futuro))
    selected=[p['calculo'] for p in plano if not p['somente_dia']]
    context=dict(plano=plano,resumo_atraso=totais(selected),dia_futuro=dia_futuro)
    if automatic:
        return dict(html=render_template('receber/_previa.html',**context),assinatura=token if plano else '',erro=erro)
    return render_template('receber/lote.html',ids=ids,assinatura=token,**context)
