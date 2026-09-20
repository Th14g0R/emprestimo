"""Transações de escrita abrangem validação, saldo, movimento e auditoria."""
import sqlite3
from functools import wraps

from flask import g, make_response, request


class Connection(sqlite3.Connection):
    defer_commit = False

    def commit(self):
        if not self.defer_commit:
            super().commit()


def register_atomic_writes(app, get_db, refresh=None):
    """Serializa POSTs antes de qualquer leitura de negócio.

    Os commits legados ficam adiados até o retorno da rota. Rollback continua
    imediato. BEGIN IMMEDIATE impede que dois operadores validem saldo antigo.
    """
    for endpoint, view in list(app.view_functions.items()):
        app.view_functions[endpoint] = _wrap(view, get_db, refresh)


def _wrap(view, get_db, refresh):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if request.method != 'POST':
            return view(*args, **kwargs)
        db = get_db()
        try:
            db.execute('BEGIN IMMEDIATE')
        except sqlite3.OperationalError:
            response = make_response('Sistema ocupado. Aguarde e tente novamente.', 503)
            response.headers['Retry-After'] = '5'
            return response
        db.defer_commit = True
        try:
            response = make_response(view(*args, **kwargs))
            if response.status_code < 400 and getattr(g, 'usuario', None) and refresh:
                refresh(db)
            db.defer_commit = False
            if response.status_code < 400 or request.endpoint in {'login', 'portal.login'}:
                db.commit()
            else:
                db.rollback()
            return response
        except BaseException:
            db.rollback()
            raise
        finally:
            db.defer_commit = False
    return wrapped


def serialized_update(function):
    """Protege rotinas legadas de sincronização chamadas fora de um POST."""
    @wraps(function)
    def wrapped(db, *args, **kwargs):
        if db.in_transaction:
            return function(db, *args, **kwargs)
        db.execute('BEGIN IMMEDIATE')
        previous = db.defer_commit
        db.defer_commit = True
        try:
            result = function(db, *args, **kwargs)
            db.defer_commit = previous
            db.commit()
            return result
        except BaseException:
            db.rollback()
            raise
        finally:
            db.defer_commit = previous
    return wrapped
