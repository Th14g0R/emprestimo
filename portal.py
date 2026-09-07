from __future__ import annotations

import json
from io import BytesIO
import re
import secrets
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from PIL import Image, ImageOps, UnidentifiedImageError

from app import (
    DATA_DIR, aplicar_recebimento_titulo,
    format_money, get_account_snapshots, get_client_accounts, get_db,
    get_own_accounts, only_digits, parse_int, parse_iso_date,
    parse_money_to_centavos, posicao_emprestimos_cliente,
    registrar_auditoria, resumo_financeiro_cliente, sync_receivable_titles,
    validate_cpf, validate_money_flow_accounts, validar_senha_usuario_atual,
    refresh_overdue_card_installments,
)

bp = Blueprint("portal", __name__)
PROOFS_DIR = (DATA_DIR / "comprovantes").resolve()
MAX_PROOF_INPUT_BYTES = 6 * 1024 * 1024
MAX_PROOF_STORED_BYTES = 3 * 1024 * 1024
MAX_IMAGE_DIMENSION = 1800
MAX_IMAGE_PIXELS = 20_000_000


def init_schema() -> None:
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS clientes_acessos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER NOT NULL UNIQUE,
        email TEXT NOT NULL COLLATE NOCASE UNIQUE,
        telefone_informado TEXT,
        senha_hash TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDENTE' CHECK (status IN ('PENDENTE','ATIVO','REJEITADO','BLOQUEADO')),
        contato_validado INTEGER NOT NULL DEFAULT 0 CHECK (contato_validado IN (0,1)),
        tentativas_falhas INTEGER NOT NULL DEFAULT 0,
        bloqueado_ate TEXT,
        ultimo_login_at TEXT,
        solicitado_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        aprovado_at TEXT,
        aprovado_por_usuario_id INTEGER,
        observacao_admin TEXT,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON UPDATE CASCADE ON DELETE RESTRICT,
        FOREIGN KEY (aprovado_por_usuario_id) REFERENCES usuarios(id) ON UPDATE CASCADE ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS comprovantes_pagamento (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER NOT NULL,
        cliente_acesso_id INTEGER NOT NULL,
        data_pagamento TEXT NOT NULL,
        valor_total_centavos INTEGER NOT NULL CHECK (valor_total_centavos > 0),
        arquivo_nome TEXT NOT NULL UNIQUE,
        arquivo_original TEXT NOT NULL,
        mime_type TEXT NOT NULL,
        tamanho_bytes INTEGER NOT NULL CHECK (tamanho_bytes > 0),
        status TEXT NOT NULL DEFAULT 'EM_ANALISE' CHECK (status IN ('EM_ANALISE','CONFIRMADO','REJEITADO')),
        observacao_cliente TEXT,
        observacao_admin TEXT,
        pagamento_integrado_id INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        analisado_at TEXT,
        analisado_por_usuario_id INTEGER,
        FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON UPDATE CASCADE ON DELETE RESTRICT,
        FOREIGN KEY (cliente_acesso_id) REFERENCES clientes_acessos(id) ON UPDATE CASCADE ON DELETE RESTRICT,
        FOREIGN KEY (pagamento_integrado_id) REFERENCES pagamentos_integrados(id) ON UPDATE CASCADE ON DELETE SET NULL,
        FOREIGN KEY (analisado_por_usuario_id) REFERENCES usuarios(id) ON UPDATE CASCADE ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS comprovantes_pagamento_itens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        comprovante_id INTEGER NOT NULL,
        titulo_receber_id INTEGER NOT NULL,
        valor_centavos INTEGER NOT NULL CHECK (valor_centavos > 0),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (comprovante_id) REFERENCES comprovantes_pagamento(id) ON UPDATE CASCADE ON DELETE CASCADE,
        FOREIGN KEY (titulo_receber_id) REFERENCES titulos_receber(id) ON UPDATE CASCADE ON DELETE RESTRICT,
        UNIQUE (comprovante_id, titulo_receber_id)
    );
    CREATE INDEX IF NOT EXISTS idx_clientes_acessos_status ON clientes_acessos(status);
    CREATE INDEX IF NOT EXISTS idx_comprovantes_status ON comprovantes_pagamento(status);
    CREATE INDEX IF NOT EXISTS idx_comprovantes_cliente ON comprovantes_pagamento(cliente_id);
    CREATE INDEX IF NOT EXISTS idx_comprovantes_itens_titulo ON comprovantes_pagamento_itens(titulo_receber_id);
    """)
    db.commit()


def proof_status(value: str | None) -> str:
    return {"EM_ANALISE":"Pg. em análise","CONFIRMADO":"Confirmado","REJEITADO":"Rejeitado"}.get(str(value or '').upper(), value or '-')


def access_status(value: str | None) -> str:
    return {
        "PENDENTE": "Pendente",
        "ATIVO": "Ativo",
        "REJEITADO": "Rejeitado",
        "BLOQUEADO": "Inativo",
    }.get(str(value or "").upper(), value or "-")


def portal_required(view):
    from functools import wraps
    @wraps(view)
    def wrapped(*args, **kwargs):
        if getattr(g, 'portal_access', None) is None:
            flash('Faça login para acessar sua área.', 'warning')
            return redirect(url_for('portal.login'))
        return view(*args, **kwargs)
    return wrapped


def find_client_by_cpf(cpf: str):
    digits=only_digits(cpf)
    rows=get_db().execute("SELECT id,nome,cpf,email,telefone,ativo FROM clientes WHERE cpf IS NOT NULL AND trim(cpf)<>''").fetchall()
    matches=[r for r in rows if only_digits(r['cpf'])==digits]
    return matches[0] if len(matches)==1 else None


def valid_email(v: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]{1,80}@[^@\s]{1,120}\.[^@\s]{2,30}", v.strip()))


def contact_matches(c, email, phone):
    return bool((c['email'] and str(c['email']).strip().lower()==email.lower()) or (c['telefone'] and only_digits(c['telefone'])==only_digits(phone)))


def _image_to_compact_jpeg(data: bytes) -> bytes:
    try:
        with Image.open(BytesIO(data), formats=("JPEG", "PNG")) as image:
            width, height = image.size
            if width <= 0 or height <= 0:
                raise ValueError("A imagem enviada é inválida.")
            if width * height > MAX_IMAGE_PIXELS:
                raise ValueError(
                    "A imagem possui resolução excessiva. Envie uma imagem "
                    "com até aproximadamente 20 megapixels."
                )

            image.load()
            image = ImageOps.exif_transpose(image)
            image.thumbnail(
                (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION),
                Image.Resampling.LANCZOS,
            )

            if image.mode in {"RGBA", "LA"}:
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")

            for quality in (82, 74, 66):
                buffer = BytesIO()
                image.save(
                    buffer,
                    format="JPEG",
                    quality=quality,
                    optimize=True,
                    progressive=True,
                )
                optimized = buffer.getvalue()
                if len(optimized) <= MAX_PROOF_STORED_BYTES:
                    return optimized

            image.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            image.save(
                buffer,
                format="JPEG",
                quality=66,
                optimize=True,
                progressive=True,
            )
            optimized = buffer.getvalue()
            if len(optimized) > MAX_PROOF_STORED_BYTES:
                raise ValueError(
                    "Mesmo após otimização, a imagem ficou maior que 3 MB. "
                    "Reduza a resolução e tente novamente."
                )
            return optimized
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("A imagem enviada não pôde ser validada.") from exc


def validate_file(storage):
    original = Path(storage.filename or '').name.strip()[:180]
    if not original:
        raise ValueError('Selecione o comprovante.')

    suffix = Path(original).suffix.lower()
    if suffix not in {'.pdf', '.png', '.jpg', '.jpeg'}:
        raise ValueError(
            'Formato não permitido. Envie somente PDF, PNG, JPG ou JPEG.'
        )

    data = storage.read(MAX_PROOF_INPUT_BYTES + 1)
    if not data:
        raise ValueError('O comprovante está vazio.')
    if len(data) > MAX_PROOF_INPUT_BYTES:
        raise ValueError(
            'O arquivo enviado deve ter no máximo 6 MB antes da otimização.'
        )

    if data.startswith(b'%PDF-'):
        if suffix != '.pdf':
            raise ValueError('A extensão não corresponde ao conteúdo do arquivo.')
        if len(data) > MAX_PROOF_STORED_BYTES:
            raise ValueError('Comprovantes PDF devem ter no máximo 3 MB.')
        return data, '.pdf', 'application/pdf', original

    is_png = data.startswith(b'\x89PNG\r\n\x1a\n')
    is_jpeg = data[:3] == b'\xff\xd8\xff'
    if not (is_png or is_jpeg):
        raise ValueError(
            'O conteúdo do arquivo não é uma imagem PNG/JPEG nem um PDF válido.'
        )

    expected_group = '.png' if is_png else '.jpg'
    suffix_group = '.jpg' if suffix in {'.jpg', '.jpeg'} else suffix
    if suffix_group != expected_group:
        raise ValueError('A extensão não corresponde ao conteúdo do arquivo.')

    optimized = _image_to_compact_jpeg(data)
    optimized_name = f"{Path(original).stem[:160] or 'comprovante'}.jpg"
    return optimized, '.jpg', 'image/jpeg', optimized_name


def card_summaries(client_id):
    db=get_db(); refresh_overdue_card_installments(db)
    return db.execute("""
        SELECT cc.id,cc.descricao,cc.ativo,
               COALESCE(cc.dia_vencimento, CAST(strftime('%d', MIN(pc.vencimento)) AS INTEGER)) dia_vencimento,
               COALESCE(SUM(pc.valor_centavos),0) total_emprestado_centavos,
               COUNT(pc.id) parcelas_totais,
               COALESCE(SUM(CASE WHEN pc.status='PAGO' THEN 1 ELSE 0 END),0) parcelas_pagas,
               COALESCE(SUM(CASE WHEN pc.status IN ('PENDENTE','VENCIDO') THEN pc.valor_centavos ELSE 0 END),0) valor_em_aberto_centavos
          FROM cartoes_credito cc
          LEFT JOIN lancamentos_cartao lc ON lc.cartao_credito_id=cc.id
          LEFT JOIN parcelas_cartao pc ON pc.lancamento_cartao_id=lc.id
         WHERE cc.cliente_id=? GROUP BY cc.id ORDER BY cc.ativo DESC,cc.id DESC
    """,(client_id,)).fetchall()


@bp.before_app_request
def load_portal_user():
    g.portal_access=None
    aid=session.get('cliente_acesso_id')
    if aid is None: return
    row=get_db().execute("""SELECT ca.id,ca.cliente_id,ca.email,ca.status,c.nome cliente_nome,c.ativo cliente_ativo FROM clientes_acessos ca JOIN clientes c ON c.id=ca.cliente_id WHERE ca.id=?""",(aid,)).fetchone()
    if row is None or row['status']!='ATIVO' or not row['cliente_ativo']:
        session.pop('cliente_acesso_id',None); return
    g.portal_access=row


@bp.after_app_request
def security_headers(response):
    response.headers.setdefault('X-Content-Type-Options','nosniff')
    response.headers.setdefault('X-Frame-Options','SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy','same-origin')
    response.headers.setdefault('Permissions-Policy','camera=(), microphone=(), geolocation=()')
    response.headers.setdefault('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; font-src 'self' data:; frame-ancestors 'self'; base-uri 'self'; form-action 'self'")
    if getattr(g,'usuario',None) is not None or getattr(g,'portal_access',None) is not None:
        response.headers['Cache-Control']='no-store, no-cache, must-revalidate, private'
    if request.is_secure:
        response.headers.setdefault('Strict-Transport-Security','max-age=31536000; includeSubDomains')
    return response


@bp.app_context_processor
def portal_context():
    alerts={'accesses':0,'proofs':0,'total':0}
    if getattr(g,'usuario',None) is not None:
        db=get_db(); alerts['accesses']=db.execute("SELECT COUNT(*) FROM clientes_acessos WHERE status='PENDENTE'").fetchone()[0]; alerts['proofs']=db.execute("SELECT COUNT(*) FROM comprovantes_pagamento WHERE status='EM_ANALISE'").fetchone()[0]; alerts['total']=alerts['accesses']+alerts['proofs']
    return {'portal_alerts':alerts}


@bp.app_template_filter('comprovante_status')
def filter_proof_status(v): return proof_status(v)


@bp.app_template_filter('acesso_status')
def filter_access_status(v): return access_status(v)


@bp.route('/portal/cadastro',methods=['GET','POST'])
def register():
    form = {
        'cpf': request.form.get('cpf', ''),
        'email': request.form.get('email', ''),
        'telefone': request.form.get('telefone', ''),
    }

    if request.method == 'POST':
        cpf = only_digits(form['cpf'])
        email = form['email'].strip().lower()
        phone = only_digits(form['telefone'])
        password = request.form.get('senha', '')
        confirm = request.form.get('confirmar_senha', '')
        errors = []

        if not validate_cpf(cpf):
            errors.append('Informe um CPF válido.')
        if not valid_email(email):
            errors.append('Informe um e-mail válido.')
        if len(password) < 10:
            errors.append('A senha deve ter pelo menos 10 caracteres.')
        if password != confirm:
            errors.append('A confirmação da senha não confere.')

        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('portal/cadastro.html', form=form)

        db = get_db()
        client = find_client_by_cpf(cpf)

        if client is None or not client['ativo']:
            flash(
                'Não foi possível realizar a solicitação porque não há um '
                'cliente ativo com este CPF cadastrado. Confira o CPF ou '
                'entre em contato com o responsável pelo cadastro.',
                'warning',
            )
            return render_template('portal/cadastro.html', form=form), 400

        existing_client = db.execute(
            'SELECT id,status,email FROM clientes_acessos WHERE cliente_id=? LIMIT 1',
            (client['id'],),
        ).fetchone()
        existing_email = db.execute(
            'SELECT id,cliente_id,status FROM clientes_acessos WHERE lower(email)=lower(?) LIMIT 1',
            (email,),
        ).fetchone()

        if (
            existing_email is not None
            and int(existing_email['cliente_id']) != int(client['id'])
        ):
            flash(
                'Este e-mail já está associado a outro acesso. Use outro '
                'e-mail ou procure o administrador.',
                'warning',
            )
            return render_template('portal/cadastro.html', form=form), 409

        matched = int(contact_matches(client, email, phone))

        try:
            if existing_client is None:
                cur = db.execute(
                    """
                    INSERT INTO clientes_acessos(
                        cliente_id,email,telefone_informado,senha_hash,
                        status,contato_validado
                    ) VALUES(?,?,?,?,'PENDENTE',?)
                    """,
                    (
                        client['id'],
                        email,
                        phone or None,
                        generate_password_hash(password),
                        matched,
                    ),
                )
                access_id = int(cur.lastrowid)
                message = (
                    'Solicitação enviada. O acesso ficará pendente até a '
                    'aprovação do administrador.'
                )
            elif existing_client['status'] in {'PENDENTE', 'REJEITADO'}:
                access_id = int(existing_client['id'])
                db.execute(
                    """
                    UPDATE clientes_acessos
                       SET email=?, telefone_informado=?, senha_hash=?,
                           status='PENDENTE', contato_validado=?,
                           tentativas_falhas=0, bloqueado_ate=NULL,
                           observacao_admin=NULL,
                           solicitado_at=CURRENT_TIMESTAMP,
                           updated_at=CURRENT_TIMESTAMP
                     WHERE id=?
                    """,
                    (
                        email,
                        phone or None,
                        generate_password_hash(password),
                        matched,
                        access_id,
                    ),
                )
                message = (
                    'Solicitação atualizada. O acesso ficará pendente até a '
                    'aprovação do administrador.'
                )
            elif existing_client['status'] == 'ATIVO':
                db.rollback()
                flash(
                    'Este cliente já possui acesso ativo. Use a tela de login '
                    'ou procure o administrador para redefinir a senha.',
                    'info',
                )
                return redirect(url_for('portal.login'))
            else:
                db.rollback()
                flash(
                    'Este cliente possui um acesso inativo. Procure o '
                    'administrador para reativação.',
                    'warning',
                )
                return redirect(url_for('portal.login'))

            registrar_auditoria(
                db,
                'cliente_acesso',
                access_id,
                'SOLICITADO',
                json.dumps(
                    {
                        'cliente_id': int(client['id']),
                        'contato_validado': bool(matched),
                    },
                    ensure_ascii=False,
                ),
            )
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            current_app.logger.exception(
                'Conflito ao registrar solicitação de acesso do cliente'
            )
            flash(
                'Não foi possível registrar a solicitação com estes dados. '
                'Verifique o e-mail ou procure o administrador.',
                'danger',
            )
            return render_template('portal/cadastro.html', form=form), 409

        flash(message, 'success')
        return redirect(url_for('portal.login'))

    return render_template('portal/cadastro.html', form=form)

@bp.route('/portal/login',methods=['GET','POST'])
def login():
    email=request.form.get('email','').strip().lower()
    if request.method=='POST':
        password=request.form.get('senha',''); db=get_db(); row=db.execute("SELECT ca.*,c.nome cliente_nome,c.ativo cliente_ativo FROM clientes_acessos ca JOIN clientes c ON c.id=ca.cliente_id WHERE lower(ca.email)=lower(?) LIMIT 1",(email,)).fetchone(); now=datetime.now(); blocked=False
        if row is not None and row['bloqueado_ate']:
            try: blocked=datetime.fromisoformat(row['bloqueado_ate'])>now
            except ValueError: blocked=False
        ok=bool(row and row['cliente_ativo'] and not blocked and check_password_hash(row['senha_hash'],password))
        if not ok:
            if row is not None and not blocked:
                fails=int(row['tentativas_falhas'] or 0)+1; until=None
                if fails>=5: until=(now+timedelta(minutes=15)).isoformat(timespec='seconds'); fails=0
                db.execute("UPDATE clientes_acessos SET tentativas_falhas=?,bloqueado_ate=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(fails,until,row['id'])); db.commit()
            flash('E-mail ou senha inválidos. Se houver bloqueio temporário, aguarde alguns minutos e tente novamente.','danger'); return render_template('portal/login.html',email=email),401
        if row['status']!='ATIVO':
            flash('Seu acesso está aguardando aprovação do administrador.' if row['status']=='PENDENTE' else 'Este acesso não está disponível.','warning'); return render_template('portal/login.html',email=email),403
        csrf=session.get('csrf_token'); admin=session.get('usuario_id'); session.clear();
        if csrf: session['csrf_token']=csrf
        if admin: session['usuario_id']=admin
        session['cliente_acesso_id']=row['id']; session.permanent=True
        db.execute("UPDATE clientes_acessos SET tentativas_falhas=0,bloqueado_ate=NULL,ultimo_login_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=?",(row['id'],)); db.commit(); return redirect(url_for('portal.dashboard'))
    return render_template('portal/login.html',email=email)


@bp.post('/portal/logout')
@portal_required
def logout(): session.pop('cliente_acesso_id',None); flash('Sessão encerrada.','success'); return redirect(url_for('portal.login'))


@bp.get('/portal')
@portal_required
def dashboard():
    db=get_db(); cid=int(g.portal_access['cliente_id']); sync_receivable_titles(db); resumo=resumo_financeiro_cliente(db,cid); loans=posicao_emprestimos_cliente(db,cid); cards=card_summaries(cid); titles=db.execute("SELECT t.id,t.competencia,t.data_vencimento,t.valor_previsto_centavos,t.status,t.natureza,e.id emprestimo_id,e.descricao emprestimo_descricao FROM titulos_receber t JOIN emprestimos e ON e.id=t.emprestimo_id WHERE e.cliente_id=? AND t.status IN ('PREVISTO','VENCIDO') ORDER BY t.data_vencimento,e.id,t.id",(cid,)).fetchall(); proofs=db.execute("SELECT id,data_pagamento,valor_total_centavos,status,created_at FROM comprovantes_pagamento WHERE cliente_id=? ORDER BY created_at DESC,id DESC LIMIT 10",(cid,)).fetchall(); return render_template('portal/dashboard.html',resumo=resumo,emprestimos=loans,cartoes=cards,titulos=titles,comprovantes=proofs)


@bp.get('/portal/comprovantes')
@portal_required
def proofs():
    rows=get_db().execute("SELECT id,data_pagamento,valor_total_centavos,status,observacao_cliente,observacao_admin,created_at,analisado_at FROM comprovantes_pagamento WHERE cliente_id=? ORDER BY created_at DESC,id DESC",(g.portal_access['cliente_id'],)).fetchall(); return render_template('portal/comprovantes_lista.html',comprovantes=rows)


@bp.route('/portal/comprovantes/novo',methods=['GET','POST'])
@portal_required
def new_proof():
    db=get_db(); cid=int(g.portal_access['cliente_id']); sync_receivable_titles(db); titles=db.execute("""SELECT t.id,t.competencia,t.data_vencimento,t.valor_previsto_centavos,t.natureza,t.status,e.id emprestimo_id,e.descricao emprestimo_descricao FROM titulos_receber t JOIN emprestimos e ON e.id=t.emprestimo_id WHERE e.cliente_id=? AND t.status IN ('PREVISTO','VENCIDO') AND NOT EXISTS(SELECT 1 FROM comprovantes_pagamento_itens cpi JOIN comprovantes_pagamento cp ON cp.id=cpi.comprovante_id WHERE cpi.titulo_receber_id=t.id AND cp.status='EM_ANALISE') ORDER BY t.data_vencimento,e.id,t.id""",(cid,)).fetchall(); available={int(t['id']):t for t in titles}; form={'data_pagamento':request.form.get('data_pagamento',date.today().isoformat()),'observacao':request.form.get('observacao','')}; lines={i:request.form.get(f'valor_{i}',format_money(available[i]['valor_previsto_centavos']).replace('R$ ','')) for i in available}
    if request.method=='POST':
        selected=[]
        for v in request.form.getlist('titulo_id'):
            x=parse_int(v)
            if x is not None and x not in selected: selected.append(x)
        paydate=parse_iso_date(form['data_pagamento']); errors=[]; items=[]; keys=set()
        if not selected: errors.append('Selecione pelo menos um título.')
        if paydate is None: errors.append('Informe a data do pagamento.')
        elif paydate>date.today(): errors.append('A data do pagamento não pode estar no futuro.')
        for tid in selected:
            t=available.get(tid)
            if t is None: errors.append(f'O título #{tid} não está disponível.'); continue
            key=(int(t['emprestimo_id']),str(t['competencia']))
            if key in keys: errors.append('Selecione apenas um documento por empréstimo e competência.'); continue
            keys.add(key); val=parse_money_to_centavos(request.form.get(f'valor_{tid}','')); saldo=int(t['valor_previsto_centavos'])
            if val is None or val<=0: errors.append(f'Informe o valor pago no título #{tid}.')
            elif val>saldo: errors.append(f'O valor do título #{tid} não pode superar {format_money(saldo)}.')
            else: items.append({'titulo_id':tid,'valor_centavos':int(val)})
        storage=request.files.get('comprovante'); fileinfo=None
        if storage is None: errors.append('Anexe o comprovante de transferência.')
        else:
            try: fileinfo=validate_file(storage)
            except ValueError as exc: errors.append(str(exc))
        if errors:
            for e in errors: flash(e,'danger')
        else:
            data,ext,mime,original=fileinfo; total=sum(i['valor_centavos'] for i in items); name=f'{uuid4().hex}{ext}'; path=PROOFS_DIR/name
            try:
                path.write_bytes(data); cur=db.execute("INSERT INTO comprovantes_pagamento(cliente_id,cliente_acesso_id,data_pagamento,valor_total_centavos,arquivo_nome,arquivo_original,mime_type,tamanho_bytes,status,observacao_cliente) VALUES(?,?,?,?,?,?,?,?,'EM_ANALISE',?)",(cid,g.portal_access['id'],paydate.isoformat(),total,name,original,mime,len(data),(form['observacao'].strip() or None))); pid=int(cur.lastrowid)
                for i in items: db.execute("INSERT INTO comprovantes_pagamento_itens(comprovante_id,titulo_receber_id,valor_centavos) VALUES(?,?,?)",(pid,i['titulo_id'],i['valor_centavos']))
                registrar_auditoria(db,'comprovante_pagamento',pid,'ENVIADO_PORTAL',json.dumps({'cliente_id':cid,'valor_total_centavos':total,'itens':items},ensure_ascii=False)); db.commit()
            except Exception:
                db.rollback()
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
                current_app.logger.exception('Erro ao registrar comprovante do portal')
                flash('Não foi possível registrar o comprovante. Nenhuma baixa foi realizada.','danger')
            else:
                flash('Comprovante enviado. Status: Pg. em análise.','success')
                return redirect(url_for('portal.proofs'))
    return render_template('portal/comprovante_form.html',titulos=titles,linhas=lines,form=form)


@bp.get('/portal/comprovantes/<int:proof_id>/arquivo')
@portal_required
def client_file(proof_id):
    row=get_db().execute("SELECT arquivo_nome,arquivo_original,mime_type FROM comprovantes_pagamento WHERE id=? AND cliente_id=?",(proof_id,g.portal_access['cliente_id'])).fetchone();
    if row is None: abort(404)
    path=PROOFS_DIR/row['arquivo_nome'];
    if not path.is_file(): abort(404)
    return send_file(path,mimetype=row['mime_type'],as_attachment=True,download_name=row['arquivo_original'],conditional=True)


@bp.get('/acessos-clientes')
def admin_accesses():
    if getattr(g,'usuario',None) is None: return redirect(url_for('login'))
    rows=get_db().execute("""
        SELECT ca.id,ca.email,ca.telefone_informado,ca.status,
               ca.contato_validado,ca.solicitado_at,ca.aprovado_at,
               ca.ultimo_login_at,ca.observacao_admin,
               c.id cliente_id,c.nome cliente_nome,
               c.email email_cadastrado,c.telefone telefone_cadastrado
          FROM clientes_acessos ca
          JOIN clientes c ON c.id=ca.cliente_id
         ORDER BY CASE ca.status
                    WHEN 'PENDENTE' THEN 0
                    WHEN 'ATIVO' THEN 1
                    WHEN 'BLOQUEADO' THEN 2
                    ELSE 3
                  END,
                  ca.solicitado_at DESC
    """).fetchall()
    return render_template('portal_admin/acessos.html',acessos=rows)


def _admin_required():
    if getattr(g,'usuario',None) is None: return redirect(url_for('login'))
    return None


@bp.route('/acessos-clientes/<int:aid>/editar',methods=['GET','POST'])
def edit_access(aid):
    r = _admin_required()
    if r:
        return r

    db = get_db()
    access = db.execute(
        """
        SELECT ca.*, c.nome AS cliente_nome, c.email AS email_cadastrado,
               c.telefone AS telefone_cadastrado
          FROM clientes_acessos ca
          JOIN clientes c ON c.id=ca.cliente_id
         WHERE ca.id=?
        """,
        (aid,),
    ).fetchone()
    if access is None:
        abort(404)

    form = {
        'email': request.form.get('email', access['email']),
        'telefone': request.form.get(
            'telefone',
            access['telefone_informado'] or '',
        ),
        'status': request.form.get('status', access['status']),
        'observacao_admin': request.form.get(
            'observacao_admin',
            access['observacao_admin'] or '',
        ),
    }

    if request.method == 'POST':
        email = form['email'].strip().lower()
        phone = only_digits(form['telefone'])
        status = form['status'].strip().upper()
        observation = form['observacao_admin'].strip()
        new_password = request.form.get('nova_senha', '')
        confirm_password = request.form.get('confirmar_nova_senha', '')
        admin_password = request.form.get('senha_confirmacao', '')
        errors = []

        if not valid_email(email):
            errors.append('Informe um e-mail válido.')
        if status not in {'PENDENTE', 'ATIVO', 'BLOQUEADO'}:
            errors.append('Status de acesso inválido.')
        if new_password:
            if len(new_password) < 10:
                errors.append(
                    'A nova senha deve ter pelo menos 10 caracteres.'
                )
            if new_password != confirm_password:
                errors.append('A confirmação da nova senha não confere.')
        if not validar_senha_usuario_atual(admin_password):
            errors.append('Sua senha de confirmação é inválida.')

        conflicting = db.execute(
            """
            SELECT id,cliente_id
              FROM clientes_acessos
             WHERE lower(email)=lower(?) AND id<>?
             LIMIT 1
            """,
            (email, aid),
        ).fetchone()
        if conflicting is not None:
            errors.append('Este e-mail já está associado a outro acesso.')

        if errors:
            for error in errors:
                flash(error, 'danger')
        else:
            before = {
                'email': access['email'],
                'telefone_informado': access['telefone_informado'],
                'status': access['status'],
                'contato_validado': bool(access['contato_validado']),
                'observacao_admin': access['observacao_admin'],
            }
            matched = int(
                bool(
                    access['email_cadastrado']
                    and str(access['email_cadastrado']).strip().lower()
                    == email
                )
                or bool(
                    access['telefone_cadastrado']
                    and only_digits(access['telefone_cadastrado']) == phone
                )
            )
            password_hash = (
                generate_password_hash(new_password)
                if new_password
                else access['senha_hash']
            )

            approved_at = access['aprovado_at']
            approved_by = access['aprovado_por_usuario_id']
            if status == 'ATIVO' and access['status'] != 'ATIVO':
                approved_at = datetime.now().isoformat(
                    sep=' ',
                    timespec='seconds',
                )
                approved_by = g.usuario['id']

            try:
                db.execute(
                    """
                    UPDATE clientes_acessos
                       SET email=?, telefone_informado=?, senha_hash=?,
                           status=?, contato_validado=?,
                           observacao_admin=?, aprovado_at=?,
                           aprovado_por_usuario_id=?,
                           tentativas_falhas=0, bloqueado_ate=NULL,
                           updated_at=CURRENT_TIMESTAMP
                     WHERE id=?
                    """,
                    (
                        email,
                        phone or None,
                        password_hash,
                        status,
                        matched,
                        observation or None,
                        approved_at,
                        approved_by,
                        aid,
                    ),
                )
                registrar_auditoria(
                    db,
                    'cliente_acesso',
                    aid,
                    'ALTERADO_ADMIN',
                    json.dumps(
                        {
                            'antes': before,
                            'depois': {
                                'email': email,
                                'telefone_informado': phone or None,
                                'status': status,
                                'contato_validado': bool(matched),
                                'observacao_admin': observation or None,
                            },
                            'senha_alterada': bool(new_password),
                        },
                        ensure_ascii=False,
                    ),
                )
                db.commit()
            except sqlite3.IntegrityError:
                db.rollback()
                flash(
                    'Não foi possível salvar. Verifique se o e-mail já está '
                    'associado a outro acesso.',
                    'danger',
                )
            else:
                flash('Cadastro de acesso atualizado.', 'success')
                return redirect(url_for('portal.admin_accesses'))

    return render_template(
        'portal_admin/acesso_editar.html',
        acesso=access,
        form=form,
    )


@bp.post('/acessos-clientes/<int:aid>/aprovar')
def approve_access(aid):
    r=_admin_required();
    if r: return r
    if not validar_senha_usuario_atual(request.form.get('senha_confirmacao')): flash('Senha de confirmação inválida.','danger'); return redirect(url_for('portal.admin_accesses'))
    db=get_db(); row=db.execute('SELECT id,cliente_id,email FROM clientes_acessos WHERE id=?',(aid,)).fetchone();
    if row is None: abort(404)
    obs=request.form.get('observacao_admin','').strip() or None; db.execute("UPDATE clientes_acessos SET status='ATIVO',aprovado_at=CURRENT_TIMESTAMP,aprovado_por_usuario_id=?,observacao_admin=?,tentativas_falhas=0,bloqueado_ate=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=?",(g.usuario['id'],obs,aid)); registrar_auditoria(db,'cliente_acesso',aid,'APROVADO',json.dumps({'cliente_id':int(row['cliente_id']),'email':row['email']},ensure_ascii=False)); db.commit(); flash('Acesso aprovado.','success'); return redirect(url_for('portal.admin_accesses'))


@bp.post('/acessos-clientes/<int:aid>/rejeitar')
def reject_access(aid):
    r=_admin_required();
    if r: return r
    pwd=request.form.get('senha_confirmacao'); reason=request.form.get('observacao_admin','').strip(); errors=[]
    if not validar_senha_usuario_atual(pwd): errors.append('Senha de confirmação inválida.')
    if len(reason)<5: errors.append('Informe o motivo da rejeição.')
    if errors:
        [flash(e,'danger') for e in errors]; return redirect(url_for('portal.admin_accesses'))
    db=get_db(); row=db.execute('SELECT id,cliente_id FROM clientes_acessos WHERE id=?',(aid,)).fetchone();
    if row is None: abort(404)
    db.execute("UPDATE clientes_acessos SET status='REJEITADO',aprovado_at=NULL,aprovado_por_usuario_id=?,observacao_admin=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(g.usuario['id'],reason,aid)); registrar_auditoria(db,'cliente_acesso',aid,'REJEITADO',json.dumps({'cliente_id':int(row['cliente_id']),'motivo':reason},ensure_ascii=False)); db.commit(); flash('Solicitação rejeitada.','success'); return redirect(url_for('portal.admin_accesses'))


@bp.get('/comprovantes')
def admin_proofs():
    r=_admin_required();
    if r: return r
    status=request.args.get('status','em_analise'); sql="SELECT cp.id,cp.data_pagamento,cp.valor_total_centavos,cp.status,cp.created_at,c.id cliente_id,c.nome cliente_nome FROM comprovantes_pagamento cp JOIN clientes c ON c.id=cp.cliente_id WHERE 1=1"; params=[]
    if status=='em_analise': sql+=" AND cp.status='EM_ANALISE'"
    elif status=='confirmado': sql+=" AND cp.status='CONFIRMADO'"
    elif status=='rejeitado': sql+=" AND cp.status='REJEITADO'"
    elif status!='todos': status='em_analise'; sql+=" AND cp.status='EM_ANALISE'"
    sql+=' ORDER BY CASE cp.status WHEN \'EM_ANALISE\' THEN 0 WHEN \'CONFIRMADO\' THEN 1 ELSE 2 END,cp.created_at DESC,cp.id DESC'; rows=get_db().execute(sql,params).fetchall(); return render_template('portal_admin/comprovantes.html',comprovantes=rows,status=status)


@bp.get('/comprovantes/<int:pid>')
def admin_proof(pid):
    r=_admin_required();
    if r: return r
    db=get_db(); cp=db.execute("SELECT cp.*,c.nome cliente_nome FROM comprovantes_pagamento cp JOIN clientes c ON c.id=cp.cliente_id WHERE cp.id=?",(pid,)).fetchone();
    if cp is None: abort(404)
    items=db.execute("""SELECT cpi.titulo_receber_id,cpi.valor_centavos,t.competencia,t.data_vencimento,t.valor_previsto_centavos,t.status,t.natureza,e.id emprestimo_id,e.descricao emprestimo_descricao FROM comprovantes_pagamento_itens cpi JOIN titulos_receber t ON t.id=cpi.titulo_receber_id JOIN emprestimos e ON e.id=t.emprestimo_id WHERE cpi.comprovante_id=? ORDER BY t.data_vencimento,e.id,t.id""",(pid,)).fetchall(); return render_template('portal_admin/comprovante_detalhe.html',comprovante=cp,itens=items,contas_cliente=get_client_accounts(cp['cliente_id']),contas_proprias=get_own_accounts())


@bp.get('/comprovantes/<int:pid>/arquivo')
def admin_file(pid):
    r=_admin_required();
    if r: return r
    row=get_db().execute('SELECT arquivo_nome,arquivo_original,mime_type FROM comprovantes_pagamento WHERE id=?',(pid,)).fetchone();
    if row is None: abort(404)
    path=PROOFS_DIR/row['arquivo_nome'];
    if not path.is_file(): abort(404)
    return send_file(path,mimetype=row['mime_type'],as_attachment=True,download_name=row['arquivo_original'],conditional=True)


@bp.post('/comprovantes/<int:pid>/confirmar')
def confirm_proof(pid):
    r=_admin_required();
    if r: return r
    db=get_db(); cp=db.execute("SELECT cp.*,c.nome cliente_nome FROM comprovantes_pagamento cp JOIN clientes c ON c.id=cp.cliente_id WHERE cp.id=?",(pid,)).fetchone();
    if cp is None: abort(404)
    if cp['status']!='EM_ANALISE': flash('Este comprovante já foi analisado.','warning'); return redirect(url_for('portal.admin_proof',pid=pid))
    origin=parse_int(request.form.get('conta_origem_id')); dest=parse_int(request.form.get('conta_destino_id')); obs=request.form.get('observacao_admin','').strip(); errors=[]
    if not validar_senha_usuario_atual(request.form.get('senha_confirmacao')): errors.append('Senha de confirmação inválida.')
    errors.extend(validate_money_flow_accounts(cp['cliente_id'],origin,dest,is_loan_disbursement=False))
    items=db.execute("SELECT cpi.titulo_receber_id,cpi.valor_centavos,t.emprestimo_id,t.competencia,t.status,t.valor_previsto_centavos,t.saldo_base_centavos FROM comprovantes_pagamento_itens cpi JOIN titulos_receber t ON t.id=cpi.titulo_receber_id WHERE cpi.comprovante_id=? ORDER BY cpi.id",(pid,)).fetchall(); total=0; keys=set()
    for i in items:
        total+=int(i['valor_centavos']); key=(int(i['emprestimo_id']),str(i['competencia']))
        if key in keys:
            errors.append('Há mais de um título da mesma competência para o mesmo empréstimo.')
        else:
            keys.add(key)
        if i['status'] not in {'PREVISTO','VENCIDO'}: errors.append(f"O título #{i['titulo_receber_id']} não está mais em aberto.")
        if int(i['valor_centavos'])>int(i['valor_previsto_centavos']): errors.append(f"O valor do título #{i['titulo_receber_id']} supera o saldo atual.")
    if total!=int(cp['valor_total_centavos']): errors.append('A soma dos títulos não corresponde ao comprovante.')
    if errors:
        [flash(e,'danger') for e in errors]; return redirect(url_for('portal.admin_proof',pid=pid))
    ob,op,dbank,dp=get_account_snapshots(origin,dest)
    try:
        cur=db.execute("INSERT INTO pagamentos_integrados(cliente_id,data_pagamento,valor_total_centavos,conta_origem_id,conta_destino_id,origem_banco_snapshot,origem_pix_snapshot,destino_banco_snapshot,destino_pix_snapshot,observacao,usuario_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(cp['cliente_id'],cp['data_pagamento'],cp['valor_total_centavos'],origin,dest,ob,op,dbank,dp,f'Comprovante portal #{pid}'+(f' — {obs}' if obs else ''),g.usuario['id'])); payid=int(cur.lastrowid)
        for i in items:
            tid=int(i['titulo_receber_id']); val=int(i['valor_centavos']); curm=db.execute("""INSERT INTO movimentacoes_emprestimo(emprestimo_id,tipo,data_movimento,valor_centavos,observacao,competencia,usuario_id,saldo_antes_centavos,saldo_depois_centavos,conta_origem_id,conta_destino_id,origem_banco_snapshot,origem_pix_snapshot,destino_banco_snapshot,destino_pix_snapshot,pagamento_integrado_id,titulo_receber_id) VALUES(?,'JUROS',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(i['emprestimo_id'],cp['data_pagamento'],val,f'Comprovante portal #{pid}',i['competencia'],g.usuario['id'],i['saldo_base_centavos'],i['saldo_base_centavos'],origin,dest,ob,op,dbank,dp,payid,tid)); mid=int(curm.lastrowid)
            db.execute("INSERT INTO pagamentos_integrados_itens(pagamento_integrado_id,emprestimo_id,tipo,competencia,valor_centavos,saldo_base_centavos,movimentacao_id,titulo_receber_id,origem_item) VALUES(?,?,'JUROS',?,?,?,?,?,'TITULO')",(payid,i['emprestimo_id'],i['competencia'],val,i['saldo_base_centavos'],mid,tid)); aplicar_recebimento_titulo(db,titulo_id=tid,valor_recebido_centavos=val,movimentacao_id=mid,data_recebimento=date.fromisoformat(cp['data_pagamento']),observacao=f'Comprovante portal #{pid}')
        db.execute("UPDATE comprovantes_pagamento SET status='CONFIRMADO',observacao_admin=?,pagamento_integrado_id=?,analisado_at=CURRENT_TIMESTAMP,analisado_por_usuario_id=? WHERE id=?",(obs or None,payid,g.usuario['id'],pid)); registrar_auditoria(db,'comprovante_pagamento',pid,'CONFIRMADO_E_BAIXADO',json.dumps({'pagamento_integrado_id':payid,'valor_total_centavos':total},ensure_ascii=False)); db.commit(); flash('Comprovante confirmado e títulos baixados.','success')
    except Exception:
        db.rollback()
        current_app.logger.exception('Erro ao confirmar comprovante do cliente')
        flash('A baixa não foi concluída. Nenhuma movimentação foi confirmada.','danger')
    return redirect(url_for('portal.admin_proof',pid=pid))


@bp.post('/comprovantes/<int:pid>/rejeitar')
def reject_proof(pid):
    r=_admin_required();
    if r: return r
    reason=request.form.get('observacao_admin','').strip(); errors=[]
    if not validar_senha_usuario_atual(request.form.get('senha_confirmacao')): errors.append('Senha de confirmação inválida.')
    if len(reason)<5: errors.append('Informe o motivo da rejeição.')
    if errors:
        [flash(e,'danger') for e in errors]; return redirect(url_for('portal.admin_proof',pid=pid))
    db=get_db(); row=db.execute('SELECT id,status FROM comprovantes_pagamento WHERE id=?',(pid,)).fetchone();
    if row is None: abort(404)
    if row['status']!='EM_ANALISE': flash('Este comprovante já foi analisado.','warning'); return redirect(url_for('portal.admin_proof',pid=pid))
    db.execute("UPDATE comprovantes_pagamento SET status='REJEITADO',observacao_admin=?,analisado_at=CURRENT_TIMESTAMP,analisado_por_usuario_id=? WHERE id=?",(reason,g.usuario['id'],pid)); registrar_auditoria(db,'comprovante_pagamento',pid,'REJEITADO',json.dumps({'motivo':reason},ensure_ascii=False)); db.commit(); flash('Comprovante rejeitado.','success'); return redirect(url_for('portal.admin_proof',pid=pid))


def register_portal(app):
    PROOFS_DIR.mkdir(parents=True,exist_ok=True)
    with app.app_context(): init_schema()
    app.register_blueprint(bp)
