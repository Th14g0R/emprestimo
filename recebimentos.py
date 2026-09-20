"""Recebimentos individuais e agrupados com detalhamento de atraso."""
from datetime import date
import json
import sqlite3

from flask import abort, flash, g, redirect, render_template, request, url_for

from atrasos import calcular, assinatura, totais, gravar_calculo, snapshot
from money import MAX_CENTAVOS


def carregar(db, ids, cliente_id=None):
    result = []
    for tid in sorted(set(ids)):
        row = db.execute('''SELECT t.*, e.cliente_id, e.data_emprestimo,
            e.saldo_atual_centavos, c.nome AS cliente_nome
            FROM titulos_receber t JOIN emprestimos e ON e.id=t.emprestimo_id
            JOIN clientes c ON c.id=e.cliente_id WHERE t.id=?''', (tid,)).fetchone()
        if row is None or (cliente_id is not None and row['cliente_id'] != cliente_id):
            raise ValueError('Um dos títulos não pertence ao cliente selecionado.')
        result.append(row)
    return result


def validar_titulos(db, titulos):
    keys = set()
    for t in titulos:
        if t['status'] not in {'PREVISTO','VENCIDO'}:
            raise ValueError(f"O título #{t['id']} não está mais em aberto.")
        if t['natureza'] != 'JUROS':
            raise ValueError('Saldos parciais antigos precisam de conferência antes da baixa.')
        key = (t['emprestimo_id'], t['competencia'])
        if key in keys or db.execute("""SELECT 1 FROM movimentacoes_emprestimo
            WHERE emprestimo_id=? AND competencia=? AND tipo='JUROS'""", key).fetchone():
            raise ValueError('Já há juros para o empréstimo e competência selecionados.')
        keys.add(key)
    if not titulos:
        raise ValueError('Selecione pelo menos um título.')
    if len({t['cliente_id'] for t in titulos}) != 1:
        raise ValueError('Um pagamento deve pertencer a um único cliente.')


def _insert(db, table, values):
    # table e nomes de colunas são constantes internas, nunca entradas HTTP.
    columns = ','.join(values)
    markers = ','.join('?' for _ in values)
    return db.execute(f'INSERT INTO {table} ({columns}) VALUES ({markers})', tuple(values.values())).lastrowid


def registrar(db, titulos, data_pagamento, origem, destino, observacao='', *, agrupado=False):
    """O chamador fornece uma transação BEGIN IMMEDIATE já aberta."""
    import app as core
    validar_titulos(db, titulos)
    errors = core.validate_money_flow_accounts(titulos[0]['cliente_id'],origem,destino,is_loan_disbursement=False)
    if errors:
        raise ValueError(' '.join(errors))
    planos = [calcular(t,data_pagamento) for t in titulos]
    if totais(planos)['valor_total_centavos'] > MAX_CENTAVOS:
        raise ValueError('A soma do pagamento supera o limite suportado.')
    ob,op,dbank,dp = core.get_account_snapshots(origem,destino)
    bank = dict(conta_origem_id=origem,conta_destino_id=destino,
                origem_banco_snapshot=ob,origem_pix_snapshot=op,
                destino_banco_snapshot=dbank,destino_pix_snapshot=dp)
    payid = None
    if agrupado:
        payid = _insert(db,'pagamentos_integrados',dict(
            cliente_id=titulos[0]['cliente_id'],data_pagamento=data_pagamento.isoformat(),
            valor_total_centavos=totais(planos)['valor_total_centavos'],
            observacao=observacao or None,usuario_id=g.usuario['id'],**bank))
    for t,p in zip(titulos,planos):
        gravar_calculo(db,t['id'],p)
        mid = _insert(db,'movimentacoes_emprestimo',dict(
            emprestimo_id=t['emprestimo_id'],tipo='JUROS',data_movimento=data_pagamento.isoformat(),
            valor_centavos=p['valor_total_centavos'],competencia=t['competencia'],
            usuario_id=g.usuario['id'],saldo_antes_centavos=t['saldo_atual_centavos'],
            saldo_depois_centavos=t['saldo_atual_centavos'],observacao=observacao or None,
            titulo_receber_id=t['id'],pagamento_integrado_id=payid,**bank,**snapshot(p)))
        if payid:
            _insert(db,'pagamentos_integrados_itens',dict(
                pagamento_integrado_id=payid,emprestimo_id=t['emprestimo_id'],tipo='JUROS',
                competencia=t['competencia'],valor_centavos=p['valor_total_centavos'],
                saldo_base_centavos=t['saldo_base_centavos'],movimentacao_id=mid,
                titulo_receber_id=t['id'],origem_item='TITULO',**snapshot(p)))
        core.aplicar_recebimento_titulo(db,titulo_id=t['id'],
            valor_recebido_centavos=p['valor_total_centavos'],movimentacao_id=mid,
            data_recebimento=data_pagamento,observacao=observacao)
        core.registrar_auditoria(db,'titulo_receber',t['id'],'RECEBIDO',json.dumps(
            dict(p,movimentacao_id=mid,pagamento_integrado_id=payid),ensure_ascii=False))
    if payid:
        core.registrar_auditoria(db,'pagamento_integrado',payid,'CRIADO',
            json.dumps(dict(itens=planos,**totais(planos)),ensure_ascii=False))
    return payid, planos


def _form(core, cliente_id, date_name):
    own = core.get_own_accounts()
    accounts = core.get_client_accounts(cliente_id) if cliente_id else []
    data = dict(request.form)
    data.setdefault(date_name,date.today().isoformat())
    data.setdefault('conta_origem_id',accounts[0]['id'] if accounts else None)
    data.setdefault('conta_destino_id',own[0]['id'] if own else None)
    data.setdefault('observacao','')
    return data,accounts,own


def _check_preview(planos):
    # Clientes antigos sem adicional continuam compatíveis. Com adicional,
    # uma assinatura vincula a confirmação às datas e valores apresentados.
    if any(p['juros_atraso_centavos'] for p in planos) or request.form.get('acao') == 'confirmar':
        if request.form.get('assinatura') != assinatura(planos):
            raise ValueError('Confira o detalhamento atualizado e confirme novamente.')


def detalhe(titulo_id):
    import app as core
    db=core.get_db()
    core.sync_receivable_titles(db)
    titulo=core.get_titulo_receber_or_404(titulo_id)
    form,accounts,own=_form(core,titulo['cliente_id'],'data_recebimento')
    planos=[]
    data=core.parse_iso_date(form['data_recebimento'])
    try:
        if titulo['status'] in {'PREVISTO','VENCIDO'}:
            planos=[calcular(titulo,data)]
        elif titulo['valor_base_centavos'] is not None:
            planos=[dict(snapshot(titulo),titulo_id=titulo['id'],emprestimo_id=titulo['emprestimo_id'],
                competencia=titulo['competencia'],valor_total_centavos=titulo['valor_recebido_centavos'])]
        if request.method=='POST' and request.form.get('acao')!='prever':
            validar_titulos(db,[titulo])
            _check_preview(planos)
            supplied=request.form.get('valor_recebido')
            if supplied and core.parse_money_to_centavos(supplied)!=planos[0]['valor_total_centavos']:
                raise ValueError('O valor recebido deve corresponder ao total integral com atraso.')
            registrar(db,[titulo],data,core.parse_int(form['conta_origem_id']),
                      core.parse_int(form['conta_destino_id']),form['observacao'])
            db.commit()
            flash('Recebimento confirmado. O detalhamento do atraso foi registrado.','success')
            return redirect(url_for('titulos_receber_detalhe',titulo_id=titulo_id))
    except ValueError as exc:
        db.rollback()
        flash(str(exc),'warning')
    except sqlite3.DatabaseError:
        db.rollback()
        core.app.logger.exception('Erro ao receber título')
        flash('O recebimento não foi gravado. Atualize a página e confira o título.','danger')
    form['valor_recebido']=core.format_money(planos[0]['valor_total_centavos']).replace('R$ ','') if planos else ''
    return render_template('receber/detalhe.html',titulo=titulo,form=form,
        contas_cliente=accounts,contas_proprias=own,planos=planos,assinatura=assinatura(planos),
        resumo_atraso=totais(planos),titulos_saldo=db.execute(
            'SELECT * FROM titulos_receber WHERE titulo_origem_id=?',(titulo_id,)).fetchall())


def novo():
    import app as core
    db=core.get_db()
    core.sync_receivable_titles(db)
    clientes=db.execute('SELECT id,nome FROM clientes ORDER BY nome COLLATE NOCASE').fetchall()
    cid=core.parse_int(request.form.get('cliente_id') if request.method=='POST' else request.args.get('cliente_id'))
    cliente=db.execute('SELECT id,nome FROM clientes WHERE id=?',(cid,)).fetchone()
    form,accounts,own=_form(core,cid,'data_pagamento')
    form['cliente_id']=cid
    selected=sorted({core.parse_int(x) for x in request.form.getlist('titulo_id') if core.parse_int(x) is not None})
    titles=db.execute('''SELECT t.*,e.descricao,e.data_emprestimo,e.cliente_id
        FROM titulos_receber t JOIN emprestimos e ON e.id=t.emprestimo_id
        WHERE e.cliente_id=? AND t.status IN ('PREVISTO','VENCIDO')
        ORDER BY t.data_vencimento,t.id''',(cid,)).fetchall()
    planos=[]
    try:
        if request.method=='POST':
            if cliente is None:
                raise ValueError('Selecione um cliente válido.')
            if request.form.getlist('emprestimo_manual_id'):
                raise ValueError('Para competência histórica, use Receber juros no contrato e confira a prévia.')
            rows=carregar(db,selected,cid)
            validar_titulos(db,rows)
            data=core.parse_iso_date(form['data_pagamento'])
            planos=[calcular(t,data) for t in rows]
            if request.form.get('acao')!='prever':
                _check_preview(planos)
                supplied=request.form.get('valor_total')
                if supplied and core.parse_money_to_centavos(supplied)!=totais(planos)['valor_total_centavos']:
                    raise ValueError('O total recebido deve corresponder à soma dos títulos com atraso.')
                for p in planos:
                    supplied=request.form.get(f"valor_titulo_{p['titulo_id']}")
                    if supplied and core.parse_money_to_centavos(supplied)!=p['valor_total_centavos']:
                        raise ValueError('Cada título deve ser recebido integralmente, incluindo o atraso.')
                payid,_=registrar(db,rows,data,core.parse_int(form['conta_origem_id']),
                    core.parse_int(form['conta_destino_id']),form['observacao'],agrupado=True)
                db.commit()
                flash('Pagamento registrado com o detalhamento individual dos títulos.','success')
                return redirect(url_for('pagamentos_integrados_detalhe',pagamento_id=payid))
    except ValueError as exc:
        db.rollback()
        flash(str(exc),'warning')
    except sqlite3.DatabaseError:
        db.rollback()
        core.app.logger.exception('Erro ao registrar recebimento agrupado')
        flash('O pagamento não foi gravado. Confira os títulos antes de tentar novamente.','danger')
    return render_template('pagamentos_integrados/form.html',clientes=clientes,cliente=cliente,
        form=form,titulos_abertos=titles,selected_title_ids=selected,contas_cliente=accounts,
        contas_proprias=own,planos=planos,resumo_atraso=totais(planos),assinatura=assinatura(planos))


def juros(emprestimo_id):
    """Entrada pelo contrato; usa o título existente ou constitui uma competência histórica."""
    import app as core
    db=core.get_db()
    loan=core.get_emprestimo_or_404(emprestimo_id)
    form,accounts,own=_form(core,loan['cliente_id'],'data_movimento')
    form.setdefault('competencia',date.today().strftime('%Y-%m'))
    planos=[]
    try:
        competencia=core.parse_competencia(form['competencia'])
        data=core.parse_iso_date(form['data_movimento'])
        if competencia is None or competencia < loan['data_emprestimo'][:7]:
            raise ValueError('Informe uma competência válida, a partir do mês do empréstimo.')
        if loan['saldo_atual_centavos']<=0:
            raise ValueError('Este empréstimo está quitado.')
        row=db.execute('''SELECT id FROM titulos_receber WHERE emprestimo_id=?
            AND competencia=? AND natureza='JUROS' ORDER BY id LIMIT 1''',(emprestimo_id,competencia)).fetchone()
        if row:
            titulo=core.get_titulo_receber_or_404(row['id'])
        else:
            saldo=core.saldo_principal_antes_da_data(db,emprestimo_id,data) if data else 0
            base=core.calcular_juros_centavos(saldo,loan['taxa_juros_mensal'])
            if base<=0:
                raise ValueError('A data e o saldo informados não geram juros.')
            due=core.due_date_for_competence(competencia,loan['dia_vencimento'] or date.fromisoformat(loan['data_emprestimo']).day)
            titulo=dict(id=None,emprestimo_id=emprestimo_id,cliente_id=loan['cliente_id'],
                competencia=competencia,data_vencimento=due.isoformat(),valor_previsto_centavos=base,
                saldo_base_centavos=saldo,taxa_juros_mensal=loan['taxa_juros_mensal'],status='PREVISTO',
                natureza='JUROS',data_emprestimo=loan['data_emprestimo'])
        planos=[calcular(titulo,data)]
        if request.method=='POST' and request.form.get('acao')!='prever':
            validar_titulos(db,[titulo])
            _check_preview(planos)
            if titulo['id'] is None:
                tid=_insert(db,'titulos_receber',{k:titulo[k] for k in
                    ('emprestimo_id','competencia','data_vencimento','valor_previsto_centavos',
                     'saldo_base_centavos','taxa_juros_mensal','status','natureza')})
                titulo=core.get_titulo_receber_or_404(tid)
            registrar(db,[titulo],data,core.parse_int(form['conta_origem_id']),
                core.parse_int(form['conta_destino_id']),form['observacao'])
            db.commit()
            flash('Juros recebidos com detalhamento de atraso. Principal preservado.','success')
            return redirect(url_for('titulos_receber_detalhe',titulo_id=titulo['id']))
    except ValueError as exc:
        db.rollback()
        flash(str(exc),'warning')
    except sqlite3.DatabaseError:
        db.rollback()
        core.app.logger.exception('Erro ao receber juros do contrato')
        flash('O recebimento não foi gravado. Confira a competência.','danger')
    return render_template('receber/juros.html',emprestimo=loan,form=form,
        contas_cliente=accounts,contas_proprias=own,planos=planos,
        resumo_atraso=totais(planos),assinatura=assinatura(planos))
