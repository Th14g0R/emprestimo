"""Limite persistente de solicitações públicas por endereço remoto."""
import hashlib
import hmac
import time

from flask import request


def register_public_limits(app, get_db):
    with app.app_context():
        get_db().execute('''CREATE TABLE IF NOT EXISTS limites_publicos (
            chave TEXT PRIMARY KEY, inicio INTEGER NOT NULL, tentativas INTEGER NOT NULL
        )''')
        get_db().commit()

    @app.before_request
    def limit_public_posts():
        if request.method != 'POST' or request.endpoint not in {'portal.register','login','portal.login'}:
            return None
        now = int(time.time())
        limit = 10 if request.endpoint == 'portal.register' else 30
        window = 900
        identity = f'{request.endpoint}:{request.remote_addr or "unknown"}'
        key = hmac.new(app.secret_key.encode(), identity.encode(), hashlib.sha256).hexdigest()
        db = get_db()
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('DELETE FROM limites_publicos WHERE inicio <= ?', (now-window,))
            row = db.execute('SELECT inicio,tentativas FROM limites_publicos WHERE chave=?', (key,)).fetchone()
            if row and row['tentativas'] >= limit:
                db.commit()
                return 'Muitas tentativas. Aguarde alguns minutos e tente novamente.', 429, {'Retry-After': str(max(1,window-(now-row['inicio'])))}
            db.execute('''INSERT INTO limites_publicos(chave,inicio,tentativas) VALUES(?,?,1)
                ON CONFLICT(chave) DO UPDATE SET tentativas=tentativas+1''', (key,now))
            db.commit()
        except BaseException:
            db.rollback()
            raise
        return None
