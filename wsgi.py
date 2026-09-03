"""Entrypoint WSGI para hospedagens e servidores web."""
from app import app

# Muitos provedores procuram uma variável chamada "application".
application = app
