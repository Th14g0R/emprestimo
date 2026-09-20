"""Comprovantes usam o mesmo cálculo e serviço de recebimento do administrativo."""
from datetime import date
import json
import sqlite3
from uuid import uuid4

from flask import abort, current_app, flash, g, redirect, render_template, request, url_for
from atrasos import calcular, assinatura, totais, snapshot
from recebimentos import carregar, validar_titulos, registrar, _check_preview, _insert


def novo_comprovante():
    import portal as portal
    db=portal.get_db()
    cid=int(g.portal_access['cliente_id'])
    portal.sync_receivable_titles(db)
    titles=db.execute('''SELECT t.*, e.data_emprestimo, e.cliente_id
        FROM titulos_receber t JOIN emprestimos e ON e.id=t.emprestimo_id
        WHERE e.cliente_id=? AND t.status IN ('PREVISTO','VENCIDO')
        AND NOT EXISTS(SELECT 1 FROM comprovantes_pagamento_itens i
            JOIN comprovantes_pagamento cp ON cp.id=i.comprovante_id
            WHERE i.titulo_receber_id=t.id AND cp.status='EM_ANALISE')
        ORDER BY t.data_vencimento,t.id''',(cid,)).fetchall()
    available={t['id'] for t in titles}
    form={'data_pagamento':request.form.get('data_pagamento',date.today().isoformat()),
          'observacao':request.form.get('observacao','')}
    planos=[]
    path=None
    try:
        if request.method=='POST':
            ids=sorted({portal.parse_int(x) for x in request.form.getlist('titulo_id') if portal.parse_int(x) is not None})
            if any(tid not in available for tid in ids):
                raise ValueError('Um título não está disponível ou já tem comprovante em análise.')
            rows=carregar(db,ids,cid)
            validar_titulos(db,rows)
            data=portal.parse_iso_date(form['data_pagamento'])
            if data is None or data>date.today():
                raise ValueError('Informe a data efetiva do pagamento, até hoje.')
            planos=[calcular(t,data) for t in rows]
            if request.form.get('acao')!='prever':
                _check_preview(planos)
                for p in planos:
                    supplied=request.form.get(f"valor_{p['titulo_id']}")
                    if supplied and portal.parse_money_to_centavos(supplied)!=p['valor_total_centavos']:
                        raise ValueError('O valor pago deve corresponder ao total integral com atraso.')
                storage=request.files.get('comprovante')
                if storage is None:
                    raise ValueError('Anexe o comprovante de transferência.')
                raw,ext,mime,original=portal.validate_file(storage)
                name=f'{uuid4().hex}{ext}'
                path=portal.PROOFS_DIR/name
                path.write_bytes(raw)
                pid=_insert(db,'comprovantes_pagamento',dict(cliente_id=cid,
                    cliente_acesso_id=g.portal_access['id'],data_pagamento=data.isoformat(),
                    valor_total_centavos=totais(planos)['valor_total_centavos'],arquivo_nome=name,
                    arquivo_original=original,mime_type=mime,tamanho_bytes=len(raw),
                    status='EM_ANALISE',observacao_cliente=form['observacao'].strip() or None))
                for p in planos:
                    _insert(db,'comprovantes_pagamento_itens',dict(comprovante_id=pid,
                        titulo_receber_id=p['titulo_id'],valor_centavos=p['valor_total_centavos'],**snapshot(p)))
                portal.registrar_auditoria(db,'comprovante_pagamento',pid,'ENVIADO_PORTAL',
                    json.dumps(dict(cliente_id=cid,itens=planos,**totais(planos)),ensure_ascii=False))
                db.commit()
                flash('Comprovante enviado com o detalhamento. Aguarde a análise.','success')
                return redirect(url_for('portal.proofs'))
    except ValueError as exc:
        flash(str(exc),'warning')
    except (sqlite3.DatabaseError,OSError):
        db.rollback()
        if path:
            path.unlink(missing_ok=True)
        current_app.logger.exception('Falha ao registrar comprovante')
        flash('O comprovante não foi registrado. Tente novamente.','danger')
    return render_template('portal/comprovante_form.html',titulos=titles,form=form,
        planos=planos,resumo_atraso=totais(planos),assinatura=assinatura(planos))


def detalhe_comprovante(pid):
    import portal as portal
    r=portal._admin_required()
    if r:return r
    db=portal.get_db()
    cp=db.execute('''SELECT cp.*,c.nome AS cliente_nome FROM comprovantes_pagamento cp
        JOIN clientes c ON c.id=cp.cliente_id WHERE cp.id=?''',(pid,)).fetchone()
    if cp is None:abort(404)
    items=db.execute('''SELECT i.*,t.emprestimo_id,t.competencia
        FROM comprovantes_pagamento_itens i JOIN titulos_receber t ON t.id=i.titulo_receber_id
        WHERE i.comprovante_id=? ORDER BY i.titulo_receber_id''',(pid,)).fetchall()
    planos=[]
    if cp['status']=='EM_ANALISE':
        try:
            rows=carregar(db,[i['titulo_receber_id'] for i in items],cp['cliente_id'])
            planos=[calcular(t,date.fromisoformat(cp['data_pagamento'])) for t in rows]
        except ValueError as exc:
            flash(str(exc),'warning')
    else:
        planos=[dict(snapshot(i),titulo_id=i['titulo_receber_id'],emprestimo_id=i['emprestimo_id'],
                     competencia=i['competencia'],valor_total_centavos=i['valor_centavos'])
                for i in items if i['valor_base_centavos'] is not None]
    return render_template('portal_admin/comprovante_detalhe.html',comprovante=cp,itens=items,
        contas_cliente=portal.get_client_accounts(cp['cliente_id']),contas_proprias=portal.get_own_accounts(),
        planos=planos,resumo_atraso=totais(planos),assinatura=assinatura(planos),
        divergencia=bool(planos and totais(planos)['valor_total_centavos']!=cp['valor_total_centavos']))


def confirmar_comprovante(pid):
    import portal as portal
    r=portal._admin_required()
    if r:return r
    db=portal.get_db()
    cp=db.execute('SELECT * FROM comprovantes_pagamento WHERE id=?',(pid,)).fetchone()
    if cp is None:abort(404)
    try:
        if cp['status']!='EM_ANALISE':
            raise ValueError('Este comprovante já foi analisado.')
        if not portal.validar_senha_usuario_atual(request.form.get('senha_confirmacao')):
            raise ValueError('Senha de confirmação inválida.')
        items=db.execute('SELECT * FROM comprovantes_pagamento_itens WHERE comprovante_id=? ORDER BY titulo_receber_id',(pid,)).fetchall()
        rows=carregar(db,[i['titulo_receber_id'] for i in items],cp['cliente_id'])
        data=date.fromisoformat(cp['data_pagamento'])
        planos=[calcular(t,data) for t in rows]
        _check_preview(planos)
        expected={p['titulo_id']:p['valor_total_centavos'] for p in planos}
        if (any(expected[i['titulo_receber_id']]!=i['valor_centavos'] for i in items)
                or totais(planos)['valor_total_centavos']!=cp['valor_total_centavos']):
            raise ValueError('O comprovante diverge do total com atraso. Confira com o cliente antes da baixa; nenhum valor foi alterado.')
        obs=request.form.get('observacao_admin','').strip()
        payid,_=registrar(db,rows,data,portal.parse_int(request.form.get('conta_origem_id')),
            portal.parse_int(request.form.get('conta_destino_id')),f'Comprovante portal #{pid}. {obs}',agrupado=True)
        db.execute("""UPDATE comprovantes_pagamento SET status='CONFIRMADO',observacao_admin=?,
            pagamento_integrado_id=?,analisado_at=CURRENT_TIMESTAMP,analisado_por_usuario_id=?
            WHERE id=?""",(obs or None,payid,g.usuario['id'],pid))
        portal.registrar_auditoria(db,'comprovante_pagamento',pid,'CONFIRMADO_E_BAIXADO',
            json.dumps(dict(pagamento_integrado_id=payid,itens=planos),ensure_ascii=False))
        db.commit()
        flash('Comprovante confirmado e recebimento detalhado registrado.','success')
    except ValueError as exc:
        db.rollback()
        flash(str(exc),'warning')
    except sqlite3.DatabaseError:
        db.rollback()
        current_app.logger.exception('Falha ao confirmar comprovante')
        flash('A baixa não foi concluída. Nenhuma movimentação foi confirmada.','danger')
    return redirect(url_for('portal.admin_proof',pid=pid))
