from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

APP_VERSION = "18.0-client-statement-report"


BASE_DIR = Path(__file__).resolve().parent

# Em Windows/local, o padrão continua sendo <projeto>/data.
# Em hospedagens com volume persistente, EMPRESTIMO_DATA_DIR permite apontar
# banco e chave para o diretório persistente fornecido pelo provedor.
DATA_DIR = Path(
    os.environ.get("EMPRESTIMO_DATA_DIR", str(BASE_DIR / "data"))
).expanduser().resolve()

DATABASE_PATH = Path(
    os.environ.get(
        "EMPRESTIMO_DATABASE",
        str(DATA_DIR / "emprestimos.db"),
    )
).expanduser().resolve()

SECRET_KEY_PATH = Path(
    os.environ.get(
        "EMPRESTIMO_SECRET_KEY_FILE",
        str(DATA_DIR / ".secret_key"),
    )
).expanduser().resolve()

F = TypeVar("F", bound=Callable[..., Any])
CENTAVOS = Decimal("100")
DUAS_CASAS = Decimal("0.01")



def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "sim", "on"}


def env_list(name: str) -> list[str]:
    value = os.environ.get(name, "")
    return [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ]


def create_app() -> Flask:
    app = Flask(__name__)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    app.config.update(
        DATABASE=str(DATABASE_PATH),
        SECRET_KEY=os.environ.get("SECRET_KEY") or load_or_create_secret_key(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Em hospedagem HTTPS configure EMPRESTIMO_HTTPS=1.
        SESSION_COOKIE_SECURE=env_bool("EMPRESTIMO_HTTPS", False),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )

    trusted_hosts = env_list("EMPRESTIMO_TRUSTED_HOSTS")
    if trusted_hosts:
        app.config["TRUSTED_HOSTS"] = trusted_hosts

    # Use somente quando houver exatamente um reverse proxy confiável
    # (Caddy/Nginx/Apache/provedor) na frente da aplicação.
    if env_bool("EMPRESTIMO_BEHIND_PROXY", False):
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=1,
            x_proto=1,
            x_host=1,
            x_port=1,
            x_prefix=1,
        )

    app.teardown_appcontext(close_db)

    with app.app_context():
        init_db()

    register_hooks(app)
    register_context_processors(app)
    register_template_filters(app)
    register_routes(app)

    return app


def load_or_create_secret_key() -> str:
    """Mantém a chave de sessão estável entre reinicializações da aplicação."""
    if SECRET_KEY_PATH.exists():
        key = SECRET_KEY_PATH.read_text(encoding="utf-8").strip()
        if key:
            return key

    key = secrets.token_hex(32)
    SECRET_KEY_PATH.write_text(key, encoding="utf-8")
    return key


def current_database_path() -> str:
    from flask import current_app

    return current_app.config["DATABASE"]


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        connection = sqlite3.connect(
            current_database_path(),
            timeout=10,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.execute("PRAGMA journal_mode = WAL;")
        connection.execute("PRAGMA busy_timeout = 5000;")
        g.db = connection

    return g.db


def close_db(error: BaseException | None = None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db() -> None:
    """Cria o schema caso ainda não exista. Não apaga dados existentes."""
    db = get_db()

    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            login TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT,
            email TEXT,
            cpf TEXT,
            endereco TEXT,
            cidade TEXT,
            estado TEXT,
            cep TEXT,
            observacoes TEXT,
            ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS contas_bancarias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo_titular TEXT NOT NULL CHECK (tipo_titular IN ('NOSSA', 'CLIENTE')),
            cliente_id INTEGER,
            banco TEXT NOT NULL,
            descricao TEXT,
            agencia TEXT,
            conta TEXT,
            tipo_conta TEXT,
            chave_pix TEXT,
            principal INTEGER NOT NULL DEFAULT 0 CHECK (principal IN (0, 1)),
            ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (
                (tipo_titular = 'NOSSA' AND cliente_id IS NULL)
                OR
                (tipo_titular = 'CLIENTE' AND cliente_id IS NOT NULL)
            ),
            FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON UPDATE CASCADE ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS emprestimos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            descricao TEXT,
            data_emprestimo TEXT NOT NULL,
            valor_original_centavos INTEGER NOT NULL CHECK (valor_original_centavos > 0),
            saldo_atual_centavos INTEGER NOT NULL CHECK (saldo_atual_centavos >= 0),
            taxa_juros_mensal REAL NOT NULL CHECK (taxa_juros_mensal >= 0),
            data_primeiro_vencimento TEXT,
            dia_vencimento INTEGER CHECK (dia_vencimento IS NULL OR dia_vencimento BETWEEN 1 AND 31),
            status TEXT NOT NULL DEFAULT 'ATIVO' CHECK (status IN ('ATIVO', 'QUITADO', 'VENCIDO')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON UPDATE CASCADE ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS movimentacoes_emprestimo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emprestimo_id INTEGER NOT NULL,
            tipo TEXT NOT NULL CHECK (tipo IN ('EMPRESTIMO', 'JUROS', 'ABATIMENTO', 'QUITACAO')),
            data_movimento TEXT NOT NULL,
            valor_centavos INTEGER NOT NULL CHECK (valor_centavos >= 0),
            conta_origem_id INTEGER,
            conta_destino_id INTEGER,
            origem_banco_snapshot TEXT,
            origem_pix_snapshot TEXT,
            destino_banco_snapshot TEXT,
            destino_pix_snapshot TEXT,
            observacao TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (emprestimo_id) REFERENCES emprestimos(id) ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (conta_origem_id) REFERENCES contas_bancarias(id) ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (conta_destino_id) REFERENCES contas_bancarias(id) ON UPDATE CASCADE ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS titulos_receber (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emprestimo_id INTEGER NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'JUROS' CHECK (tipo IN ('JUROS')),
            competencia TEXT NOT NULL,
            data_vencimento TEXT NOT NULL,
            valor_previsto_centavos INTEGER NOT NULL CHECK (valor_previsto_centavos >= 0),
            valor_recebido_centavos INTEGER NOT NULL DEFAULT 0 CHECK (valor_recebido_centavos >= 0),
            saldo_base_centavos INTEGER NOT NULL CHECK (saldo_base_centavos >= 0),
            taxa_juros_mensal REAL NOT NULL CHECK (taxa_juros_mensal >= 0),
            status TEXT NOT NULL DEFAULT 'PREVISTO'
                CHECK (status IN ('PREVISTO', 'VENCIDO', 'PARCIAL', 'RECEBIDO', 'CANCELADO')),
            movimentacao_id INTEGER,
            data_recebimento TEXT,
            observacao TEXT,
            ajuste_manual INTEGER NOT NULL DEFAULT 0
                CHECK (ajuste_manual IN (0, 1)),
            titulo_origem_id INTEGER,
            natureza TEXT NOT NULL DEFAULT 'JUROS'
                CHECK (natureza IN ('JUROS', 'SALDO_JUROS')),
            sequencia INTEGER NOT NULL DEFAULT 1 CHECK (sequencia >= 1),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (emprestimo_id) REFERENCES emprestimos(id) ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (movimentacao_id) REFERENCES movimentacoes_emprestimo(id) ON UPDATE CASCADE ON DELETE SET NULL,
            FOREIGN KEY (titulo_origem_id) REFERENCES titulos_receber(id) ON UPDATE CASCADE ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_titulos_receber_vencimento ON titulos_receber(data_vencimento);
        CREATE INDEX IF NOT EXISTS idx_titulos_receber_status ON titulos_receber(status);
        CREATE INDEX IF NOT EXISTS idx_titulos_receber_emprestimo ON titulos_receber(emprestimo_id);
        CREATE INDEX IF NOT EXISTS idx_titulos_receber_competencia ON titulos_receber(emprestimo_id, competencia);

        CREATE TABLE IF NOT EXISTS pagamentos_integrados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            data_pagamento TEXT NOT NULL,
            valor_total_centavos INTEGER NOT NULL
                CHECK (valor_total_centavos > 0),
            conta_origem_id INTEGER NOT NULL,
            conta_destino_id INTEGER NOT NULL,
            origem_banco_snapshot TEXT,
            origem_pix_snapshot TEXT,
            destino_banco_snapshot TEXT,
            destino_pix_snapshot TEXT,
            observacao TEXT,
            usuario_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cliente_id)
                REFERENCES clientes(id)
                ON UPDATE CASCADE
                ON DELETE RESTRICT,
            FOREIGN KEY (conta_origem_id)
                REFERENCES contas_bancarias(id)
                ON UPDATE CASCADE
                ON DELETE RESTRICT,
            FOREIGN KEY (conta_destino_id)
                REFERENCES contas_bancarias(id)
                ON UPDATE CASCADE
                ON DELETE RESTRICT,
            FOREIGN KEY (usuario_id)
                REFERENCES usuarios(id)
                ON UPDATE CASCADE
                ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS pagamentos_integrados_itens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pagamento_integrado_id INTEGER NOT NULL,
            emprestimo_id INTEGER NOT NULL,
            tipo TEXT NOT NULL DEFAULT 'JUROS'
                CHECK (tipo IN ('JUROS')),
            competencia TEXT NOT NULL,
            valor_centavos INTEGER NOT NULL
                CHECK (valor_centavos > 0),
            saldo_base_centavos INTEGER NOT NULL
                CHECK (saldo_base_centavos >= 0),
            movimentacao_id INTEGER NOT NULL UNIQUE,
            titulo_receber_id INTEGER,
            origem_item TEXT NOT NULL DEFAULT 'MANUAL'
                CHECK (origem_item IN ('MANUAL', 'TITULO')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (pagamento_integrado_id)
                REFERENCES pagamentos_integrados(id)
                ON UPDATE CASCADE
                ON DELETE CASCADE,
            FOREIGN KEY (emprestimo_id)
                REFERENCES emprestimos(id)
                ON UPDATE CASCADE
                ON DELETE RESTRICT,
            FOREIGN KEY (movimentacao_id)
                REFERENCES movimentacoes_emprestimo(id)
                ON UPDATE CASCADE
                ON DELETE RESTRICT,
            FOREIGN KEY (titulo_receber_id)
                REFERENCES titulos_receber(id)
                ON UPDATE CASCADE
                ON DELETE SET NULL,
            UNIQUE (pagamento_integrado_id, emprestimo_id, competencia)
        );

        CREATE INDEX IF NOT EXISTS idx_pagamentos_integrados_cliente
            ON pagamentos_integrados(cliente_id);

        CREATE INDEX IF NOT EXISTS idx_pagamentos_integrados_data
            ON pagamentos_integrados(data_pagamento);

        CREATE INDEX IF NOT EXISTS idx_pagamentos_integrados_itens_pagamento
            ON pagamentos_integrados_itens(pagamento_integrado_id);

        CREATE INDEX IF NOT EXISTS idx_pagamentos_integrados_itens_emprestimo
            ON pagamentos_integrados_itens(emprestimo_id);

        CREATE TABLE IF NOT EXISTS cartoes_credito (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            descricao TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON UPDATE CASCADE ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS lancamentos_cartao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cartao_credito_id INTEGER NOT NULL,
            descricao TEXT NOT NULL,
            valor_total_centavos INTEGER NOT NULL CHECK (valor_total_centavos > 0),
            quantidade_parcelas INTEGER NOT NULL CHECK (quantidade_parcelas > 0),
            data_compra TEXT NOT NULL,
            usuario_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cartao_credito_id) REFERENCES cartoes_credito(id) ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON UPDATE CASCADE ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS parcelas_cartao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lancamento_cartao_id INTEGER NOT NULL,
            numero_parcela INTEGER NOT NULL CHECK (numero_parcela > 0),
            valor_centavos INTEGER NOT NULL CHECK (valor_centavos >= 0),
            vencimento TEXT NOT NULL,
            data_pagamento TEXT,
            conta_origem_id INTEGER,
            conta_destino_id INTEGER,
            origem_banco_snapshot TEXT,
            origem_pix_snapshot TEXT,
            destino_banco_snapshot TEXT,
            destino_pix_snapshot TEXT,
            usuario_pagamento_id INTEGER,
            pagamento_observacao TEXT,
            status TEXT NOT NULL DEFAULT 'PENDENTE' CHECK (status IN ('PENDENTE', 'PAGO', 'VENCIDO', 'CANCELADO')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (lancamento_cartao_id) REFERENCES lancamentos_cartao(id) ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (conta_origem_id) REFERENCES contas_bancarias(id) ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (conta_destino_id) REFERENCES contas_bancarias(id) ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (usuario_pagamento_id) REFERENCES usuarios(id) ON UPDATE CASCADE ON DELETE SET NULL,
            UNIQUE (lancamento_cartao_id, numero_parcela)
        );

        CREATE INDEX IF NOT EXISTS idx_clientes_nome ON clientes(nome);
        CREATE INDEX IF NOT EXISTS idx_clientes_cpf ON clientes(cpf);
        CREATE INDEX IF NOT EXISTS idx_contas_cliente ON contas_bancarias(cliente_id);
        CREATE INDEX IF NOT EXISTS idx_contas_tipo_ativo ON contas_bancarias(tipo_titular, ativo);
        CREATE INDEX IF NOT EXISTS idx_emprestimos_cliente ON emprestimos(cliente_id);
        CREATE INDEX IF NOT EXISTS idx_emprestimos_status ON emprestimos(status);
        CREATE INDEX IF NOT EXISTS idx_emprestimos_data ON emprestimos(data_emprestimo);
        CREATE INDEX IF NOT EXISTS idx_movimentacoes_emprestimo ON movimentacoes_emprestimo(emprestimo_id);
        CREATE INDEX IF NOT EXISTS idx_movimentacoes_data ON movimentacoes_emprestimo(data_movimento);
        CREATE INDEX IF NOT EXISTS idx_cartoes_cliente ON cartoes_credito(cliente_id);
        CREATE INDEX IF NOT EXISTS idx_lancamentos_cartao ON lancamentos_cartao(cartao_credito_id);
        CREATE INDEX IF NOT EXISTS idx_parcelas_vencimento ON parcelas_cartao(vencimento);
        CREATE INDEX IF NOT EXISTS idx_parcelas_status ON parcelas_cartao(status);

        CREATE TABLE IF NOT EXISTS auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            entidade TEXT NOT NULL,
            entidade_id INTEGER,
            acao TEXT NOT NULL,
            detalhes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON UPDATE CASCADE ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_auditoria_entidade
            ON auditoria(entidade, entidade_id);

        CREATE INDEX IF NOT EXISTS idx_auditoria_created_at
            ON auditoria(created_at);
        """
    )

    migrate_schema(db)
    db.commit()


def table_columns(db: sqlite3.Connection, table_name: str) -> set[str]:
    return {row["name"] for row in db.execute(f"PRAGMA table_info({table_name})").fetchall()}


def add_column_if_missing(
    db: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    if column_name not in table_columns(db, table_name):
        db.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )


def migrate_titulos_receber_v16(db: sqlite3.Connection) -> None:
    """
    V16: permite vários documentos de juros da mesma competência.

    Isto é necessário para recebimentos parciais: o documento original fica
    marcado como PARCIAL e é criado um novo documento SALDO_JUROS, relacionado
    ao anterior, com o valor que ainda falta receber.

    A tabela antiga possuía UNIQUE (emprestimo_id, tipo, competencia) e o CHECK
    de status não aceitava PARCIAL; por isso esta migração precisa reconstruir
    a tabela preservando os IDs e os dados existentes.
    """
    row = db.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'titulos_receber'"
    ).fetchone()
    if row is None:
        return

    columns = table_columns(db, "titulos_receber")
    table_sql = (row["sql"] or "").upper()
    needs_rebuild = (
        "titulo_origem_id" not in columns
        or "valor_recebido_centavos" not in columns
        or "natureza" not in columns
        or "sequencia" not in columns
        or "PARCIAL" not in table_sql
        or "UNIQUE (EMPRESTIMO_ID, TIPO, COMPETENCIA)" in table_sql
    )
    if not needs_rebuild:
        return

    db.commit()
    foreign_keys_enabled = int(db.execute("PRAGMA foreign_keys").fetchone()[0])
    db.execute("PRAGMA foreign_keys = OFF")

    try:
        db.execute("BEGIN")
        db.execute("DROP TABLE IF EXISTS titulos_receber_v16")
        db.execute(
            """
            CREATE TABLE titulos_receber_v16 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                emprestimo_id INTEGER NOT NULL,
                tipo TEXT NOT NULL DEFAULT 'JUROS' CHECK (tipo IN ('JUROS')),
                competencia TEXT NOT NULL,
                data_vencimento TEXT NOT NULL,
                valor_previsto_centavos INTEGER NOT NULL CHECK (valor_previsto_centavos >= 0),
                valor_recebido_centavos INTEGER NOT NULL DEFAULT 0 CHECK (valor_recebido_centavos >= 0),
                saldo_base_centavos INTEGER NOT NULL CHECK (saldo_base_centavos >= 0),
                taxa_juros_mensal REAL NOT NULL CHECK (taxa_juros_mensal >= 0),
                status TEXT NOT NULL DEFAULT 'PREVISTO'
                    CHECK (status IN ('PREVISTO', 'VENCIDO', 'PARCIAL', 'RECEBIDO', 'CANCELADO')),
                movimentacao_id INTEGER,
                data_recebimento TEXT,
                observacao TEXT,
                ajuste_manual INTEGER NOT NULL DEFAULT 0 CHECK (ajuste_manual IN (0, 1)),
                titulo_origem_id INTEGER,
                natureza TEXT NOT NULL DEFAULT 'JUROS'
                    CHECK (natureza IN ('JUROS', 'SALDO_JUROS')),
                sequencia INTEGER NOT NULL DEFAULT 1 CHECK (sequencia >= 1),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (emprestimo_id) REFERENCES emprestimos(id) ON UPDATE CASCADE ON DELETE RESTRICT,
                FOREIGN KEY (movimentacao_id) REFERENCES movimentacoes_emprestimo(id) ON UPDATE CASCADE ON DELETE SET NULL,
                FOREIGN KEY (titulo_origem_id) REFERENCES titulos_receber_v16(id) ON UPDATE CASCADE ON DELETE RESTRICT
            )
            """
        )

        ajuste_expr = "ajuste_manual" if "ajuste_manual" in columns else "0"
        recebido_expr = (
            "valor_recebido_centavos"
            if "valor_recebido_centavos" in columns
            else "CASE WHEN status = 'RECEBIDO' THEN valor_previsto_centavos ELSE 0 END"
        )
        origem_expr = "titulo_origem_id" if "titulo_origem_id" in columns else "NULL"
        natureza_expr = "natureza" if "natureza" in columns else "'JUROS'"
        sequencia_expr = "sequencia" if "sequencia" in columns else "1"

        db.execute(
            f"""
            INSERT INTO titulos_receber_v16 (
                id, emprestimo_id, tipo, competencia, data_vencimento,
                valor_previsto_centavos, valor_recebido_centavos,
                saldo_base_centavos, taxa_juros_mensal, status,
                movimentacao_id, data_recebimento, observacao, ajuste_manual,
                titulo_origem_id, natureza, sequencia, created_at, updated_at
            )
            SELECT
                id, emprestimo_id, tipo, competencia, data_vencimento,
                valor_previsto_centavos, {recebido_expr},
                saldo_base_centavos, taxa_juros_mensal, status,
                movimentacao_id, data_recebimento, observacao, {ajuste_expr},
                {origem_expr}, {natureza_expr}, {sequencia_expr}, created_at, updated_at
              FROM titulos_receber
            """
        )

        db.execute("DROP TABLE titulos_receber")
        db.execute("ALTER TABLE titulos_receber_v16 RENAME TO titulos_receber")
        db.execute("CREATE INDEX IF NOT EXISTS idx_titulos_receber_vencimento ON titulos_receber(data_vencimento)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_titulos_receber_status ON titulos_receber(status)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_titulos_receber_emprestimo ON titulos_receber(emprestimo_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_titulos_receber_competencia ON titulos_receber(emprestimo_id, competencia)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_titulos_receber_origem ON titulos_receber(titulo_origem_id)")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute(f"PRAGMA foreign_keys = {1 if foreign_keys_enabled else 0}")


def migrate_schema(db: sqlite3.Connection) -> None:
    """Aplica pequenas evoluções de schema sem apagar o banco existente."""
    migrate_titulos_receber_v16(db)
    add_column_if_missing(db, "movimentacoes_emprestimo", "competencia", "TEXT")
    add_column_if_missing(db, "movimentacoes_emprestimo", "usuario_id", "INTEGER")
    add_column_if_missing(
        db,
        "movimentacoes_emprestimo",
        "saldo_antes_centavos",
        "INTEGER",
    )
    add_column_if_missing(
        db,
        "movimentacoes_emprestimo",
        "saldo_depois_centavos",
        "INTEGER",
    )

    add_column_if_missing(db, "movimentacoes_emprestimo", "conta_origem_id", "INTEGER")
    add_column_if_missing(db, "movimentacoes_emprestimo", "conta_destino_id", "INTEGER")
    add_column_if_missing(db, "movimentacoes_emprestimo", "origem_banco_snapshot", "TEXT")
    add_column_if_missing(db, "movimentacoes_emprestimo", "origem_pix_snapshot", "TEXT")
    add_column_if_missing(db, "movimentacoes_emprestimo", "destino_banco_snapshot", "TEXT")
    add_column_if_missing(db, "movimentacoes_emprestimo", "destino_pix_snapshot", "TEXT")
    add_column_if_missing(db, "movimentacoes_emprestimo", "updated_at", "TEXT")
    add_column_if_missing(db, "movimentacoes_emprestimo", "usuario_ultima_alteracao_id", "INTEGER")
    add_column_if_missing(db, "movimentacoes_emprestimo", "pagamento_integrado_id", "INTEGER")
    add_column_if_missing(db, "movimentacoes_emprestimo", "titulo_receber_id", "INTEGER")
    add_column_if_missing(db, "titulos_receber", "ajuste_manual", "INTEGER NOT NULL DEFAULT 0")
    add_column_if_missing(db, "titulos_receber", "valor_recebido_centavos", "INTEGER NOT NULL DEFAULT 0")
    add_column_if_missing(db, "titulos_receber", "titulo_origem_id", "INTEGER")
    add_column_if_missing(db, "titulos_receber", "natureza", "TEXT NOT NULL DEFAULT 'JUROS'")
    add_column_if_missing(db, "titulos_receber", "sequencia", "INTEGER NOT NULL DEFAULT 1")
    add_column_if_missing(db, "pagamentos_integrados_itens", "titulo_receber_id", "INTEGER")
    add_column_if_missing(
        db,
        "pagamentos_integrados_itens",
        "origem_item",
        "TEXT NOT NULL DEFAULT 'MANUAL'",
    )
    add_column_if_missing(db, "lancamentos_cartao", "usuario_id", "INTEGER")
    add_column_if_missing(db, "parcelas_cartao", "conta_origem_id", "INTEGER")
    add_column_if_missing(db, "parcelas_cartao", "conta_destino_id", "INTEGER")
    add_column_if_missing(db, "parcelas_cartao", "origem_banco_snapshot", "TEXT")
    add_column_if_missing(db, "parcelas_cartao", "origem_pix_snapshot", "TEXT")
    add_column_if_missing(db, "parcelas_cartao", "destino_banco_snapshot", "TEXT")
    add_column_if_missing(db, "parcelas_cartao", "destino_pix_snapshot", "TEXT")
    add_column_if_missing(db, "parcelas_cartao", "usuario_pagamento_id", "INTEGER")
    add_column_if_missing(db, "parcelas_cartao", "pagamento_observacao", "TEXT")

    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_movimentacoes_pagamento_integrado ON movimentacoes_emprestimo(pagamento_integrado_id)"
    )

    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_pagamentos_integrados_itens_titulo ON pagamentos_integrados_itens(titulo_receber_id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_titulos_receber_origem ON titulos_receber(titulo_origem_id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_titulos_receber_competencia ON titulos_receber(emprestimo_id, competencia)"
    )


    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_movimentacoes_conta_origem ON movimentacoes_emprestimo(conta_origem_id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_movimentacoes_conta_destino ON movimentacoes_emprestimo(conta_destino_id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_parcelas_conta_origem ON parcelas_cartao(conta_origem_id)"
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_parcelas_conta_destino ON parcelas_cartao(conta_destino_id)"
    )

    # Até a V15 existia um índice UNIQUE por empréstimo/competência.
    # Recebimentos parciais precisam permitir várias movimentações JUROS para
    # a mesma competência, cada uma vinculada ao documento que foi baixado.
    db.execute("DROP INDEX IF EXISTS uq_juros_emprestimo_competencia")
    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_juros_emprestimo_competencia
            ON movimentacoes_emprestimo(emprestimo_id, competencia)
         WHERE tipo = 'JUROS'
           AND competencia IS NOT NULL
        """
    )
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_movimentacoes_titulo_receber "
        "ON movimentacoes_emprestimo(titulo_receber_id)"
    )

    # Retrocompatibilidade: vincula movimentos antigos aos títulos que já
    # armazenavam movimentacao_id.
    db.execute(
        """
        UPDATE movimentacoes_emprestimo
           SET titulo_receber_id = (
               SELECT t.id
                 FROM titulos_receber t
                WHERE t.movimentacao_id = movimentacoes_emprestimo.id
                LIMIT 1
           )
         WHERE titulo_receber_id IS NULL
           AND EXISTS (
               SELECT 1
                 FROM titulos_receber t
                WHERE t.movimentacao_id = movimentacoes_emprestimo.id
           )
        """
    )

    db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_movimentacoes_tipo_competencia
            ON movimentacoes_emprestimo(tipo, competencia)
        """
    )


def registrar_auditoria(
    db: sqlite3.Connection,
    entidade: str,
    entidade_id: int | None,
    acao: str,
    detalhes: str | None = None,
) -> None:
    usuario_id = g.usuario["id"] if getattr(g, "usuario", None) is not None else None
    db.execute(
        """
        INSERT INTO auditoria (usuario_id, entidade, entidade_id, acao, detalhes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (usuario_id, entidade, entidade_id, acao, detalhes),
    )


def calcular_juros_centavos(saldo_centavos: int, taxa_percentual: Any) -> int:
    taxa = Decimal(str(taxa_percentual))
    juros = (
        Decimal(saldo_centavos) * taxa / Decimal("100")
    ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(juros)


def parse_competencia(value: str | None) -> str | None:
    clean = (value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}", clean):
        return None

    try:
        year_text, month_text = clean.split("-")
        month = int(month_text)
        year = int(year_text)
    except ValueError:
        return None

    if year < 1900 or month < 1 or month > 12:
        return None

    return clean


def format_competencia_br(value: str | None) -> str:
    if not value or not re.fullmatch(r"\d{4}-\d{2}", value):
        return "-"
    year, month = value.split("-")
    return f"{month}/{year}"


def register_hooks(app: Flask) -> None:
    @app.before_request
    def load_logged_user() -> None:
        user_id = session.get("usuario_id")
        g.usuario = None

        if user_id is not None:
            g.usuario = get_db().execute(
                "SELECT id, nome, login, ativo FROM usuarios WHERE id = ?",
                (user_id,),
            ).fetchone()

            if g.usuario is None or not g.usuario["ativo"]:
                session.clear()
                g.usuario = None

    @app.before_request
    def enforce_initial_setup() -> Any:
        if request.endpoint in {"static", "health", "configuracao_inicial"}:
            return None

        if not has_any_user():
            return redirect(url_for("configuracao_inicial"))

        return None

    @app.before_request
    def protect_post_requests() -> None:
        if request.method != "POST":
            return

        sent_token = request.form.get("csrf_token", "")
        session_token = session.get("csrf_token", "")

        if not sent_token or not session_token or not secrets.compare_digest(sent_token, session_token):
            abort(400, description="Token de segurança inválido. Atualize a página e tente novamente.")


def register_context_processors(app: Flask) -> None:
    @app.context_processor
    def inject_helpers() -> dict[str, Any]:
        return {
            "csrf_token": get_csrf_token,
        }


def register_template_filters(app: Flask) -> None:
    app.add_template_filter(format_money, "money")
    app.add_template_filter(format_date_br, "date_br")
    app.add_template_filter(format_percent_br, "percent_br")
    app.add_template_filter(format_competencia_br, "competencia_br")


def get_csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def has_any_user() -> bool:
    row = get_db().execute("SELECT 1 FROM usuarios LIMIT 1").fetchone()
    return row is not None


def login_required(view: F) -> F:
    @wraps(view)
    def wrapped_view(*args: Any, **kwargs: Any) -> Any:
        if g.usuario is None:
            flash("Faça login para acessar o sistema.", "warning")
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped_view  # type: ignore[return-value]


def only_digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def normalize_optional(value: str | None) -> str | None:
    clean = (value or "").strip()
    return clean or None


def parse_iso_date(value: str | None) -> date | None:
    clean = (value or "").strip()
    if not clean:
        return None

    try:
        return date.fromisoformat(clean)
    except ValueError:
        return None


def parse_money_to_centavos(value: str | None) -> int | None:
    """Converte valores como 1234,56 / 1.234,56 / 1234.56 em centavos."""
    raw = (value or "").strip().replace("R$", "").replace(" ", "")
    if not raw:
        return None

    raw = re.sub(r"[^0-9,.-]", "", raw)

    if "," in raw and "." in raw:
        # Entrada no padrão brasileiro: 1.234,56
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")
    elif raw.count(".") == 1:
        integer_part, decimal_part = raw.split(".")
        if len(decimal_part) == 3 and integer_part not in {"0", "-0"}:
            # Interpreta 1.234 como mil duzentos e trinta e quatro.
            raw = integer_part + decimal_part

    try:
        amount = Decimal(raw)
    except InvalidOperation:
        return None

    if not amount.is_finite():
        return None

    amount = amount.quantize(DUAS_CASAS, rounding=ROUND_HALF_UP)
    return int(amount * CENTAVOS)


def parse_percent(value: str | None) -> Decimal | None:
    raw = (value or "").strip().replace("%", "").replace(" ", "")
    if not raw:
        return None

    raw = raw.replace(",", ".")

    try:
        percent = Decimal(raw)
    except InvalidOperation:
        return None

    if not percent.is_finite():
        return None

    return percent


def format_money(value: int | None) -> str:
    centavos = int(value or 0)
    sinal = "-" if centavos < 0 else ""
    centavos = abs(centavos)
    reais = centavos // 100
    cents = centavos % 100
    reais_fmt = f"{reais:,}".replace(",", ".")
    return f"{sinal}R$ {reais_fmt},{cents:02d}"


def format_date_br(value: Any) -> str:
    """
    Formata datas para dd/mm/aaaa.

    O filtro é usado tanto com valores TEXT vindos do SQLite quanto com
    objetos date/datetime criados pela aplicação (por exemplo, os períodos
    da Agenda / A Receber).
    """
    if value is None or value == "":
        return "-"

    if isinstance(value, datetime):
        return value.date().strftime("%d/%m/%Y")

    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")

    text = str(value).strip()
    if not text:
        return "-"

    try:
        return date.fromisoformat(text[:10]).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return text


def format_percent_br(value: Any) -> str:
    if value is None:
        return "-"

    try:
        decimal_value = Decimal(str(value))
    except InvalidOperation:
        return str(value)

    text = format(decimal_value.normalize(), "f")
    return text.replace(".", ",") + "%"


def validate_cpf(cpf: str) -> bool:
    """Valida CPF pelos dígitos verificadores. CPF vazio é aceito por ser opcional."""
    if not cpf:
        return True

    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False

    numbers = [int(digit) for digit in cpf]

    first_sum = sum(numbers[index] * (10 - index) for index in range(9))
    first_digit = (first_sum * 10) % 11
    if first_digit == 10:
        first_digit = 0

    if first_digit != numbers[9]:
        return False

    second_sum = sum(numbers[index] * (11 - index) for index in range(10))
    second_digit = (second_sum * 10) % 11
    if second_digit == 10:
        second_digit = 0

    return second_digit == numbers[10]


def parse_int(value: str | None) -> int | None:
    try:
        return int((value or "").strip())
    except (TypeError, ValueError):
        return None


def add_months_iso(base_date: date, months: int) -> date:
    """Soma meses preservando o dia quando possível e ajustando ao último dia do mês."""
    month_index = (base_date.month - 1) + months
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base_date.day, monthrange(year, month)[1])
    return date(year, month, day)



def first_day_of_month(value: date) -> date:
    return value.replace(day=1)


def last_day_of_month(value: date) -> date:
    return value.replace(day=monthrange(value.year, value.month)[1])


def competencia_date(value: date) -> str:
    return value.strftime("%Y-%m")


def due_date_for_competence(competencia: str, dia_vencimento: int) -> date:
    year_text, month_text = competencia.split("-")
    year = int(year_text)
    month = int(month_text)
    day = min(int(dia_vencimento), monthrange(year, month)[1])
    return date(year, month, day)


def get_receivable_periods(reference: date | None = None) -> dict[str, dict[str, Any]]:
    today = reference or date.today()
    current_week_start = today - timedelta(days=today.weekday())
    current_week_end = current_week_start + timedelta(days=6)
    next_week_start = current_week_end + timedelta(days=1)
    next_week_end = next_week_start + timedelta(days=6)
    current_month_start = first_day_of_month(today)
    current_month_end = last_day_of_month(today)
    next_month_start = add_months_iso(current_month_start, 1)
    next_month_end = last_day_of_month(next_month_start)

    return {
        "semana_atual": {"titulo": "Semana atual", "inicio": current_week_start, "fim": current_week_end},
        "proxima_semana": {"titulo": "Próxima semana", "inicio": next_week_start, "fim": next_week_end},
        "mes_atual": {"titulo": "Mês atual", "inicio": current_month_start, "fim": current_month_end},
        "proximo_mes": {"titulo": "Próximo mês", "inicio": next_month_start, "fim": next_month_end},
    }


def receivable_period_summary(
    db: sqlite3.Connection,
    start_date: date,
    end_date: date,
) -> dict[str, int]:
    start_iso = start_date.isoformat()
    end_iso = end_date.isoformat()

    titulo = db.execute(
        """
        SELECT
            COALESCE(SUM(
                CASE
                    WHEN titulo_origem_id IS NULL AND status <> 'CANCELADO'
                    THEN valor_previsto_centavos
                    ELSE 0
                END
            ), 0) AS previsto_centavos,
            COALESCE(SUM(
                CASE
                    WHEN status IN ('PREVISTO', 'VENCIDO')
                    THEN valor_previsto_centavos
                    ELSE 0
                END
            ), 0) AS pendente_centavos,
            COALESCE(SUM(
                CASE
                    WHEN status IN ('PARCIAL', 'RECEBIDO')
                    THEN valor_recebido_centavos
                    ELSE 0
                END
            ), 0) AS titulos_recebidos_centavos,
            COALESCE(SUM(
                CASE WHEN status IN ('PREVISTO', 'VENCIDO') THEN 1 ELSE 0 END
            ), 0) AS titulos_pendentes
          FROM titulos_receber
         WHERE data_vencimento BETWEEN ? AND ?
        """,
        (start_iso, end_iso),
    ).fetchone()

    movimentos = db.execute(
        """
        SELECT
            COALESCE(SUM(CASE WHEN tipo = 'JUROS' THEN valor_centavos ELSE 0 END), 0) AS juros_recebidos_centavos,
            COALESCE(SUM(CASE WHEN tipo IN ('JUROS', 'ABATIMENTO', 'QUITACAO') THEN valor_centavos ELSE 0 END), 0) AS total_recebido_centavos
          FROM movimentacoes_emprestimo
         WHERE data_movimento BETWEEN ? AND ?
        """,
        (start_iso, end_iso),
    ).fetchone()

    return {
        "previsto_centavos": int(titulo["previsto_centavos"] or 0),
        "pendente_centavos": int(titulo["pendente_centavos"] or 0),
        "titulos_recebidos_centavos": int(titulo["titulos_recebidos_centavos"] or 0),
        "titulos_pendentes": int(titulo["titulos_pendentes"] or 0),
        "juros_recebidos_centavos": int(movimentos["juros_recebidos_centavos"] or 0),
        "total_recebido_centavos": int(movimentos["total_recebido_centavos"] or 0),
    }


def sync_receivable_titles(db: sqlite3.Connection, months_ahead: int = 2) -> None:
    """
    Sincroniza somente previsões automáticas.

    Documentos ajustados manualmente e documentos SALDO_JUROS não são
    reconciliados por uma busca genérica de competência, pois uma mesma
    competência pode possuir várias movimentações quando houve pagamentos
    parciais.
    """
    today = date.today()
    current_month = first_day_of_month(today)

    existing_titles = db.execute(
        """
        SELECT id, emprestimo_id, competencia, data_vencimento, status,
               movimentacao_id, ajuste_manual, titulo_origem_id, natureza
          FROM titulos_receber
         WHERE tipo = 'JUROS'
        """
    ).fetchall()

    for titulo in existing_titles:
        due = date.fromisoformat(titulo["data_vencimento"])

        if titulo["status"] in {"CANCELADO", "PARCIAL"}:
            continue

        if titulo["status"] == "RECEBIDO":
            # Um título recebido permanece histórico. Se a movimentação foi
            # excluída por uma operação de correção, a rotina de exclusão é
            # responsável por reabrir o documento correspondente.
            continue

        expected_status = "VENCIDO" if due < today else "PREVISTO"

        # Saldos parciais e ajustes manuais têm vida própria. Apenas atualiza
        # PREVISTO/VENCIDO conforme a data.
        if (
            titulo["titulo_origem_id"] is not None
            or int(titulo["ajuste_manual"] or 0)
            or titulo["natureza"] == "SALDO_JUROS"
        ):
            if titulo["status"] != expected_status:
                db.execute(
                    "UPDATE titulos_receber SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (expected_status, titulo["id"]),
                )
            continue

        # Compatibilidade com lançamentos antigos: só vincula automaticamente
        # quando há exatamente uma movimentação sem título para a competência.
        movements = db.execute(
            """
            SELECT id, data_movimento, titulo_receber_id
              FROM movimentacoes_emprestimo
             WHERE emprestimo_id = ?
               AND tipo = 'JUROS'
               AND competencia = ?
             ORDER BY id
            """,
            (titulo["emprestimo_id"], titulo["competencia"]),
        ).fetchall()

        linked = next(
            (m for m in movements if m["titulo_receber_id"] == titulo["id"]),
            None,
        )
        if linked is None and len(movements) == 1 and movements[0]["titulo_receber_id"] is None:
            linked = movements[0]

        if linked is not None:
            db.execute(
                """
                UPDATE titulos_receber
                   SET status = 'RECEBIDO',
                       valor_recebido_centavos = valor_previsto_centavos,
                       movimentacao_id = ?,
                       data_recebimento = ?,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE id = ?
                """,
                (linked["id"], linked["data_movimento"], titulo["id"]),
            )
            if linked["titulo_receber_id"] is None:
                db.execute(
                    "UPDATE movimentacoes_emprestimo SET titulo_receber_id = ? WHERE id = ?",
                    (titulo["id"], linked["id"]),
                )
            continue

        if titulo["status"] != expected_status:
            db.execute(
                "UPDATE titulos_receber SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (expected_status, titulo["id"]),
            )

    loans = db.execute(
        """
        SELECT id, cliente_id, data_emprestimo, data_primeiro_vencimento,
               dia_vencimento, saldo_atual_centavos, taxa_juros_mensal, status
          FROM emprestimos
         WHERE saldo_atual_centavos > 0
           AND status IN ('ATIVO', 'VENCIDO')
           AND taxa_juros_mensal > 0
        """
    ).fetchall()

    for emprestimo in loans:
        loan_date = date.fromisoformat(emprestimo["data_emprestimo"])
        if emprestimo["data_primeiro_vencimento"]:
            first_due = date.fromisoformat(emprestimo["data_primeiro_vencimento"])
        else:
            base_due = add_months_iso(loan_date, 1)
            due_day = int(emprestimo["dia_vencimento"] or base_due.day)
            first_due = base_due.replace(
                day=min(due_day, monthrange(base_due.year, base_due.month)[1])
            )

        due_day = int(emprestimo["dia_vencimento"] or first_due.day)

        for month_offset in range(months_ahead + 1):
            period_date = add_months_iso(current_month, month_offset)
            competencia = competencia_date(period_date)
            due = due_date_for_competence(competencia, due_day)
            if due < first_due:
                continue

            # Qualquer documento já existente para esta competência (inclusive
            # CANCELADO/PARCIAL/SALDO) impede a recriação automática.
            titulo = db.execute(
                """
                SELECT id, status, data_vencimento, ajuste_manual,
                       titulo_origem_id, natureza
                  FROM titulos_receber
                 WHERE emprestimo_id = ?
                   AND tipo = 'JUROS'
                   AND competencia = ?
                 ORDER BY sequencia DESC, id DESC
                 LIMIT 1
                """,
                (emprestimo["id"], competencia),
            ).fetchone()

            movements_count = int(
                db.execute(
                    """
                    SELECT COUNT(*) AS qtd
                      FROM movimentacoes_emprestimo
                     WHERE emprestimo_id = ?
                       AND tipo = 'JUROS'
                       AND competencia = ?
                    """,
                    (emprestimo["id"], competencia),
                ).fetchone()["qtd"]
            )

            if titulo is None and movements_count > 0:
                # Lançamento histórico/manual já realizado sem título.
                continue

            amount = calcular_juros_centavos(
                emprestimo["saldo_atual_centavos"],
                emprestimo["taxa_juros_mensal"],
            )
            if amount <= 0:
                continue

            if titulo is None:
                status = "VENCIDO" if due < today else "PREVISTO"
                db.execute(
                    """
                    INSERT INTO titulos_receber (
                        emprestimo_id, tipo, competencia, data_vencimento,
                        valor_previsto_centavos, valor_recebido_centavos,
                        saldo_base_centavos, taxa_juros_mensal, status,
                        natureza, sequencia
                    ) VALUES (?, 'JUROS', ?, ?, ?, 0, ?, ?, ?, 'JUROS', 1)
                    """,
                    (
                        emprestimo["id"], competencia, due.isoformat(), amount,
                        emprestimo["saldo_atual_centavos"],
                        emprestimo["taxa_juros_mensal"], status,
                    ),
                )
            elif (
                titulo["status"] == "PREVISTO"
                and not int(titulo["ajuste_manual"] or 0)
                and titulo["titulo_origem_id"] is None
                and titulo["natureza"] == "JUROS"
                and date.fromisoformat(titulo["data_vencimento"]) >= today
            ):
                db.execute(
                    """
                    UPDATE titulos_receber
                       SET data_vencimento = ?, valor_previsto_centavos = ?,
                           saldo_base_centavos = ?, taxa_juros_mensal = ?,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE id = ?
                    """,
                    (
                        due.isoformat(), amount,
                        emprestimo["saldo_atual_centavos"],
                        emprestimo["taxa_juros_mensal"], titulo["id"],
                    ),
                )

    db.execute(
        """
        UPDATE titulos_receber
           SET status = 'CANCELADO', updated_at = CURRENT_TIMESTAMP
         WHERE status = 'PREVISTO'
           AND data_vencimento > ?
           AND emprestimo_id IN (
                SELECT id FROM emprestimos
                 WHERE status = 'QUITADO' OR saldo_atual_centavos <= 0
           )
        """,
        (today.isoformat(),),
    )
    db.commit()


def split_centavos(total_centavos: int, quantidade: int) -> list[int]:
    """Rateia centavos sem perder nem criar valor."""
    base, resto = divmod(total_centavos, quantidade)
    return [base + (1 if index < resto else 0) for index in range(quantidade)]


def get_own_accounts(only_active: bool = True) -> list[sqlite3.Row]:
    sql = """
        SELECT id, banco, descricao, agencia, conta, tipo_conta, chave_pix, principal, ativo
          FROM contas_bancarias
         WHERE tipo_titular = 'NOSSA'
    """
    if only_active:
        sql += " AND ativo = 1"
    sql += " ORDER BY principal DESC, banco COLLATE NOCASE, id"
    return get_db().execute(sql).fetchall()


def get_client_accounts(cliente_id: int, only_active: bool = True) -> list[sqlite3.Row]:
    sql = """
        SELECT id, banco, descricao, agencia, conta, tipo_conta, chave_pix, principal, ativo
          FROM contas_bancarias
         WHERE tipo_titular = 'CLIENTE'
           AND cliente_id = ?
    """
    if only_active:
        sql += " AND ativo = 1"
    sql += " ORDER BY principal DESC, banco COLLATE NOCASE, id"
    return get_db().execute(sql, (cliente_id,)).fetchall()


def get_account(account_id: int | None) -> sqlite3.Row | None:
    if account_id is None:
        return None
    return get_db().execute(
        """
        SELECT cb.*, c.nome AS cliente_nome
          FROM contas_bancarias cb
          LEFT JOIN clientes c ON c.id = cb.cliente_id
         WHERE cb.id = ?
        """,
        (account_id,),
    ).fetchone()


def get_account_snapshots(conta_origem_id: int | None, conta_destino_id: int | None) -> tuple[str | None, str | None, str | None, str | None]:
    origem = get_account(conta_origem_id)
    destino = get_account(conta_destino_id)
    return (
        origem["banco"] if origem else None,
        origem["chave_pix"] if origem else None,
        destino["banco"] if destino else None,
        destino["chave_pix"] if destino else None,
    )


def validate_money_flow_accounts(
    cliente_id: int,
    conta_origem_id: int | None,
    conta_destino_id: int | None,
    *,
    is_loan_disbursement: bool,
) -> list[str]:
    errors: list[str] = []
    origem = get_account(conta_origem_id)
    destino = get_account(conta_destino_id)

    if origem is None or not origem["ativo"]:
        errors.append("Selecione uma conta de origem ativa.")
    if destino is None or not destino["ativo"]:
        errors.append("Selecione uma conta de destino ativa.")
    if errors:
        return errors

    if conta_origem_id == conta_destino_id:
        errors.append("A conta de origem e a conta de destino devem ser diferentes.")

    if is_loan_disbursement:
        if origem["tipo_titular"] != "NOSSA":
            errors.append("No empréstimo, a conta de origem deve ser uma conta própria.")
        if destino["tipo_titular"] != "CLIENTE" or destino["cliente_id"] != cliente_id:
            errors.append("No empréstimo, a conta de destino deve pertencer ao cliente do contrato.")
    else:
        if origem["tipo_titular"] != "CLIENTE" or origem["cliente_id"] != cliente_id:
            errors.append("No recebimento, a conta de origem deve pertencer ao cliente do contrato.")
        if destino["tipo_titular"] != "NOSSA":
            errors.append("No recebimento, a conta de destino deve ser uma conta própria.")

    return errors


def saldo_principal_antes_da_data(
    db: sqlite3.Connection,
    emprestimo_id: int,
    data_referencia: date,
) -> int:
    """
    Retorna o principal existente no início da data informada.

    Para lançamento histórico de juros, abatimentos/quitações ocorridos em
    datas anteriores reduzem a base. Movimentos do mesmo dia não são aplicados,
    pois o fluxo usual é cobrar o juro sobre o saldo trazido para o dia.
    """
    emprestimo = db.execute(
        """
        SELECT valor_original_centavos, data_emprestimo
          FROM emprestimos
         WHERE id = ?
        """,
        (emprestimo_id,),
    ).fetchone()

    if emprestimo is None:
        raise ValueError("Empréstimo não encontrado.")

    if data_referencia < date.fromisoformat(emprestimo["data_emprestimo"]):
        raise ValueError("A data do pagamento não pode ser anterior ao empréstimo.")

    saldo = int(emprestimo["valor_original_centavos"])

    movimentos = db.execute(
        """
        SELECT tipo, valor_centavos
          FROM movimentacoes_emprestimo
         WHERE emprestimo_id = ?
           AND data_movimento < ?
           AND tipo IN ('ABATIMENTO', 'QUITACAO')
         ORDER BY data_movimento, id
        """,
        (emprestimo_id, data_referencia.isoformat()),
    ).fetchall()

    for movimento in movimentos:
        if movimento["tipo"] == "ABATIMENTO":
            saldo -= int(movimento["valor_centavos"])
        elif movimento["tipo"] == "QUITACAO":
            saldo = 0

        if saldo <= 0:
            return 0

    return saldo


def get_titulo_receber_or_404(titulo_id: int) -> sqlite3.Row:
    titulo = get_db().execute(
        """
        SELECT t.*,
               e.cliente_id,
               e.data_emprestimo,
               e.saldo_atual_centavos,
               e.taxa_juros_mensal AS taxa_atual,
               e.status AS emprestimo_status,
               c.nome AS cliente_nome
          FROM titulos_receber t
          JOIN emprestimos e ON e.id = t.emprestimo_id
          JOIN clientes c ON c.id = e.cliente_id
         WHERE t.id = ?
        """,
        (titulo_id,),
    ).fetchone()

    if titulo is None:
        abort(404)

    return titulo


def titulo_receber_para_auditoria(
    row: sqlite3.Row | dict[str, Any],
) -> dict[str, Any]:
    keys = (
        "id",
        "emprestimo_id",
        "tipo",
        "competencia",
        "data_vencimento",
        "valor_previsto_centavos",
        "saldo_base_centavos",
        "taxa_juros_mensal",
        "status",
        "movimentacao_id",
        "data_recebimento",
        "observacao",
        "ajuste_manual",
        "valor_recebido_centavos",
        "titulo_origem_id",
        "natureza",
        "sequencia",
    )
    return {key: row[key] for key in keys if key in row.keys()}


def status_aberto_por_vencimento(data_vencimento: str | date) -> str:
    due = (
        data_vencimento
        if isinstance(data_vencimento, date)
        else date.fromisoformat(str(data_vencimento)[:10])
    )
    return "VENCIDO" if due < date.today() else "PREVISTO"


def criar_titulo_saldo_juros(
    db: sqlite3.Connection,
    titulo_origem_id: int,
    valor_saldo_centavos: int,
    *,
    observacao: str | None = None,
) -> int:
    """Cria o próximo documento de saldo para um juro recebido parcialmente."""
    origem = db.execute(
        "SELECT * FROM titulos_receber WHERE id = ?",
        (titulo_origem_id,),
    ).fetchone()
    if origem is None:
        raise ValueError("Título de origem não encontrado.")
    if valor_saldo_centavos <= 0:
        raise ValueError("O saldo residual deve ser maior que zero.")

    status = status_aberto_por_vencimento(origem["data_vencimento"])
    sequencia = int(origem["sequencia"] or 1) + 1
    texto = observacao or (
        f"Saldo remanescente do título #{titulo_origem_id} após recebimento parcial."
    )

    cursor = db.execute(
        """
        INSERT INTO titulos_receber (
            emprestimo_id, tipo, competencia, data_vencimento,
            valor_previsto_centavos, valor_recebido_centavos,
            saldo_base_centavos, taxa_juros_mensal, status,
            observacao, ajuste_manual, titulo_origem_id,
            natureza, sequencia
        ) VALUES (?, 'JUROS', ?, ?, ?, 0, ?, ?, ?, ?, 1, ?, 'SALDO_JUROS', ?)
        """,
        (
            origem["emprestimo_id"],
            origem["competencia"],
            origem["data_vencimento"],
            valor_saldo_centavos,
            origem["saldo_base_centavos"],
            origem["taxa_juros_mensal"],
            status,
            texto,
            titulo_origem_id,
            sequencia,
        ),
    )
    return int(cursor.lastrowid)


def aplicar_recebimento_titulo(
    db: sqlite3.Connection,
    *,
    titulo_id: int,
    valor_recebido_centavos: int,
    movimentacao_id: int,
    data_recebimento: date,
    observacao: str | None = None,
) -> int | None:
    """
    Baixa integralmente um título ou o marca como PARCIAL e cria o documento
    residual. Retorna o id do novo saldo quando houver pagamento parcial.
    """
    titulo = db.execute(
        "SELECT * FROM titulos_receber WHERE id = ?",
        (titulo_id,),
    ).fetchone()
    if titulo is None:
        raise ValueError("Título a receber não encontrado.")
    if titulo["status"] not in {"PREVISTO", "VENCIDO"}:
        raise ValueError("O título selecionado não está mais em aberto.")

    valor_documento = int(titulo["valor_previsto_centavos"])
    if valor_recebido_centavos <= 0:
        raise ValueError("O valor recebido deve ser maior que zero.")
    if valor_recebido_centavos > valor_documento:
        raise ValueError(
            f"O recebimento não pode ser maior que {format_money(valor_documento)}."
        )

    if valor_recebido_centavos == valor_documento:
        db.execute(
            """
            UPDATE titulos_receber
               SET status = 'RECEBIDO',
                   valor_recebido_centavos = ?,
                   movimentacao_id = ?,
                   data_recebimento = ?,
                   observacao = COALESCE(?, observacao),
                   updated_at = CURRENT_TIMESTAMP
             WHERE id = ?
            """,
            (
                valor_recebido_centavos,
                movimentacao_id,
                data_recebimento.isoformat(),
                normalize_optional(observacao),
                titulo_id,
            ),
        )
        return None

    saldo = valor_documento - valor_recebido_centavos
    db.execute(
        """
        UPDATE titulos_receber
           SET status = 'PARCIAL',
               valor_recebido_centavos = ?,
               movimentacao_id = ?,
               data_recebimento = ?,
               observacao = COALESCE(?, observacao),
               ajuste_manual = 1,
               updated_at = CURRENT_TIMESTAMP
         WHERE id = ?
        """,
        (
            valor_recebido_centavos,
            movimentacao_id,
            data_recebimento.isoformat(),
            normalize_optional(observacao),
            titulo_id,
        ),
    )

    return criar_titulo_saldo_juros(
        db,
        titulo_id,
        saldo,
        observacao=(
            f"Saldo de {format_money(saldo)} originado do título #{titulo_id}. "
            f"Recebido parcialmente: {format_money(valor_recebido_centavos)}."
        ),
    )


def criar_titulo_manual_parcial(
    db: sqlite3.Connection,
    *,
    emprestimo_id: int,
    competencia: str,
    data_vencimento: date,
    valor_integral_centavos: int,
    saldo_base_centavos: int,
    taxa_juros_mensal: Any,
) -> int:
    """Cria o documento original quando um juro histórico nasce de pagamento parcial."""
    cursor = db.execute(
        """
        INSERT INTO titulos_receber (
            emprestimo_id, tipo, competencia, data_vencimento,
            valor_previsto_centavos, valor_recebido_centavos,
            saldo_base_centavos, taxa_juros_mensal, status,
            observacao, ajuste_manual, natureza, sequencia
        ) VALUES (?, 'JUROS', ?, ?, ?, 0, ?, ?, ?, ?, 1, 'JUROS', 1)
        """,
        (
            emprestimo_id,
            competencia,
            data_vencimento.isoformat(),
            valor_integral_centavos,
            saldo_base_centavos,
            taxa_juros_mensal,
            status_aberto_por_vencimento(data_vencimento),
            "Documento criado a partir de recebimento histórico parcial.",
        ),
    )
    return int(cursor.lastrowid)


def get_pagamento_integrado_or_404(pagamento_id: int) -> sqlite3.Row:
    pagamento = get_db().execute(
        """
        SELECT p.*,
               c.nome AS cliente_nome,
               u.nome AS usuario_nome,
               COALESCE(p.origem_banco_snapshot, co.banco) AS origem_banco,
               COALESCE(p.origem_pix_snapshot, co.chave_pix) AS origem_pix,
               COALESCE(p.destino_banco_snapshot, cd.banco) AS destino_banco,
               COALESCE(p.destino_pix_snapshot, cd.chave_pix) AS destino_pix
          FROM pagamentos_integrados p
          JOIN clientes c ON c.id = p.cliente_id
          LEFT JOIN usuarios u ON u.id = p.usuario_id
          LEFT JOIN contas_bancarias co ON co.id = p.conta_origem_id
          LEFT JOIN contas_bancarias cd ON cd.id = p.conta_destino_id
         WHERE p.id = ?
        """,
        (pagamento_id,),
    ).fetchone()

    if pagamento is None:
        abort(404)

    return pagamento


def get_movimentacao_or_404(movimentacao_id: int) -> sqlite3.Row:
    row = get_db().execute(
        """
        SELECT m.*,
               e.cliente_id,
               e.data_emprestimo,
               e.valor_original_centavos,
               e.taxa_juros_mensal,
               e.status AS emprestimo_status,
               c.nome AS cliente_nome
          FROM movimentacoes_emprestimo m
          JOIN emprestimos e ON e.id = m.emprestimo_id
          JOIN clientes c ON c.id = e.cliente_id
         WHERE m.id = ?
        """,
        (movimentacao_id,),
    ).fetchone()

    if row is None:
        abort(404)

    return row


def validar_senha_usuario_atual(senha: str | None) -> bool:
    """Confirma a senha do usuário atualmente autenticado."""
    if g.usuario is None or not senha:
        return False

    row = get_db().execute(
        """
        SELECT senha_hash, ativo
          FROM usuarios
         WHERE id = ?
        """,
        (g.usuario["id"],),
    ).fetchone()

    return bool(
        row
        and row["ativo"]
        and check_password_hash(row["senha_hash"], senha)
    )


def movimentacao_para_auditoria(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "emprestimo_id",
        "tipo",
        "data_movimento",
        "competencia",
        "valor_centavos",
        "conta_origem_id",
        "conta_destino_id",
        "origem_banco_snapshot",
        "origem_pix_snapshot",
        "destino_banco_snapshot",
        "destino_pix_snapshot",
        "observacao",
        "saldo_antes_centavos",
        "saldo_depois_centavos",
        "usuario_id",
    )
    return {key: row[key] for key in keys if key in row.keys()}


def recalcular_emprestimo_por_movimentacoes(
    db: sqlite3.Connection,
    emprestimo_id: int,
) -> int:
    """Reconstitui o saldo do contrato após correções e exclusões."""
    emprestimo = db.execute(
        """
        SELECT id, data_emprestimo, valor_original_centavos,
               taxa_juros_mensal, status
          FROM emprestimos
         WHERE id = ?
        """,
        (emprestimo_id,),
    ).fetchone()

    if emprestimo is None:
        raise ValueError("Empréstimo não encontrado para recálculo.")

    movimentos = db.execute(
        """
        SELECT id, tipo, data_movimento, valor_centavos, competencia
          FROM movimentacoes_emprestimo
         WHERE emprestimo_id = ?
         ORDER BY data_movimento, id
        """,
        (emprestimo_id,),
    ).fetchall()

    valor_original = int(emprestimo["valor_original_centavos"])
    saldo = valor_original
    encontrou_movimento_inicial = False
    contrato_encerrado = False

    for movimento in movimentos:
        movimento_id = int(movimento["id"])
        tipo = movimento["tipo"]
        valor = int(movimento["valor_centavos"])

        if tipo == "EMPRESTIMO":
            if encontrou_movimento_inicial:
                raise ValueError("Existe mais de uma movimentação inicial de empréstimo.")

            encontrou_movimento_inicial = True
            saldo = valor_original
            db.execute(
                """
                UPDATE movimentacoes_emprestimo
                   SET valor_centavos = ?,
                       saldo_antes_centavos = 0,
                       saldo_depois_centavos = ?
                 WHERE id = ?
                """,
                (valor_original, valor_original, movimento_id),
            )
            continue

        if contrato_encerrado or saldo <= 0:
            raise ValueError(
                f"A movimentação #{movimento_id} ocorre depois da quitação do contrato."
            )

        if movimento["data_movimento"] < emprestimo["data_emprestimo"]:
            raise ValueError(
                f"A movimentação #{movimento_id} possui data anterior ao empréstimo."
            )

        saldo_antes = saldo

        if tipo == "JUROS":
            valor_esperado = calcular_juros_centavos(
                saldo,
                emprestimo["taxa_juros_mensal"],
            )
            if valor != valor_esperado:
                raise ValueError(
                    "A correção deixaria os juros "
                    f"#{movimento_id} inconsistentes: registrado "
                    f"{format_money(valor)}, esperado {format_money(valor_esperado)} "
                    "para o saldo existente naquela data."
                )
            saldo_depois = saldo

        elif tipo == "ABATIMENTO":
            if valor <= 0 or valor >= saldo:
                raise ValueError(
                    f"O abatimento #{movimento_id} precisa ser maior que zero e menor "
                    f"que o saldo de {format_money(saldo)} existente naquele momento."
                )
            saldo -= valor
            saldo_depois = saldo

        elif tipo == "QUITACAO":
            if valor != saldo:
                raise ValueError(
                    f"A quitação #{movimento_id} é de {format_money(valor)}, mas o saldo "
                    f"naquele momento seria {format_money(saldo)}. Corrija as movimentações "
                    "anteriores antes desta operação."
                )
            saldo = 0
            saldo_depois = 0
            contrato_encerrado = True

        else:
            raise ValueError(f"Tipo de movimentação desconhecido: {tipo}.")

        db.execute(
            """
            UPDATE movimentacoes_emprestimo
               SET saldo_antes_centavos = ?,
                   saldo_depois_centavos = ?
             WHERE id = ?
            """,
            (saldo_antes, saldo_depois, movimento_id),
        )

    if not encontrou_movimento_inicial:
        raise ValueError("A movimentação inicial do empréstimo não foi encontrada.")

    status_anterior = emprestimo["status"]
    if saldo == 0:
        novo_status = "QUITADO"
    elif status_anterior == "VENCIDO":
        novo_status = "VENCIDO"
    else:
        novo_status = "ATIVO"

    db.execute(
        """
        UPDATE emprestimos
           SET saldo_atual_centavos = ?,
               status = ?,
               updated_at = CURRENT_TIMESTAMP
         WHERE id = ?
        """,
        (saldo, novo_status, emprestimo_id),
    )

    return saldo


def refresh_overdue_card_installments(db: sqlite3.Connection) -> None:
    db.execute(
        """
        UPDATE parcelas_cartao
           SET status = 'VENCIDO'
         WHERE status = 'PENDENTE'
           AND vencimento < ?
        """,
        (date.today().isoformat(),),
    )
    db.execute(
        """
        UPDATE parcelas_cartao
           SET status = 'PENDENTE'
         WHERE status = 'VENCIDO'
           AND vencimento >= ?
           AND data_pagamento IS NULL
        """,
        (date.today().isoformat(),),
    )
    db.commit()

def register_routes(app: Flask) -> None:
    @app.get("/health")
    def health():
        db = get_db()
        db.execute("SELECT 1").fetchone()
        return {
            "status": "ok",
            "database": "ok",
            "database_file": str(DATABASE_PATH),
            "version": APP_VERSION,
        }

    @app.get("/debug/tabelas")
    @login_required
    def debug_tables():
        rows = get_db().execute(
            """
            SELECT name
              FROM sqlite_master
             WHERE type = 'table'
               AND name NOT LIKE 'sqlite_%'
             ORDER BY name
            """
        ).fetchall()
        return [row["name"] for row in rows]

    @app.route("/configuracao-inicial", methods=["GET", "POST"])
    def configuracao_inicial():
        if has_any_user():
            return redirect(url_for("login"))

        if request.method == "POST":
            nome = request.form.get("nome", "").strip()
            login_usuario = request.form.get("login", "").strip().lower()
            senha = request.form.get("senha", "")
            confirmar_senha = request.form.get("confirmar_senha", "")

            errors: list[str] = []
            if len(nome) < 3:
                errors.append("Informe o nome do administrador.")
            if len(login_usuario) < 3:
                errors.append("O login deve ter pelo menos 3 caracteres.")
            if not re.fullmatch(r"[a-z0-9._-]+", login_usuario):
                errors.append("O login pode conter apenas letras, números, ponto, hífen e sublinhado.")
            if len(senha) < 8:
                errors.append("A senha deve ter pelo menos 8 caracteres.")
            if senha != confirmar_senha:
                errors.append("A confirmação da senha não confere.")

            if errors:
                for error in errors:
                    flash(error, "danger")
                return render_template("configuracao_inicial.html", nome=nome, login=login_usuario)

            db = get_db()
            db.execute(
                """
                INSERT INTO usuarios (nome, login, senha_hash)
                VALUES (?, ?, ?)
                """,
                (nome, login_usuario, generate_password_hash(senha)),
            )
            db.commit()

            flash("Administrador criado. Faça login para continuar.", "success")
            return redirect(url_for("login"))

        return render_template("configuracao_inicial.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if not has_any_user():
            return redirect(url_for("configuracao_inicial"))

        if g.usuario is not None:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            login_usuario = request.form.get("login", "").strip().lower()
            senha = request.form.get("senha", "")

            usuario = get_db().execute(
                """
                SELECT id, nome, login, senha_hash, ativo
                  FROM usuarios
                 WHERE login = ?
                """,
                (login_usuario,),
            ).fetchone()

            if usuario is None or not usuario["ativo"] or not check_password_hash(usuario["senha_hash"], senha):
                flash("Login ou senha inválidos.", "danger")
                return render_template("login.html", login=login_usuario), 401

            csrf_token = session.get("csrf_token")
            session.clear()
            if csrf_token:
                session["csrf_token"] = csrf_token
            session["usuario_id"] = usuario["id"]

            return redirect(url_for("dashboard"))

        return render_template("login.html")

    @app.post("/logout")
    @login_required
    def logout():
        session.clear()
        flash("Sessão encerrada.", "success")
        return redirect(url_for("login"))

    @app.get("/")
    @login_required
    def index():
        return redirect(url_for("dashboard"))

    @app.get("/dashboard")
    @login_required
    def dashboard():
        db = get_db()
        sync_receivable_titles(db)
        mes_atual = date.today().strftime("%Y-%m")

        metrics = db.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM clientes WHERE ativo = 1) AS clientes_ativos,
                (SELECT COUNT(*) FROM emprestimos WHERE status IN ('ATIVO', 'VENCIDO')) AS emprestimos_ativos,
                COALESCE((SELECT SUM(valor_original_centavos) FROM emprestimos), 0) AS total_emprestado_centavos,
                COALESCE((SELECT SUM(saldo_atual_centavos) FROM emprestimos WHERE status <> 'QUITADO'), 0) AS saldo_devedor_centavos,
                COALESCE((SELECT SUM(valor_centavos)
                            FROM movimentacoes_emprestimo
                           WHERE tipo = 'JUROS' AND substr(data_movimento, 1, 7) = ?), 0) AS juros_mes_centavos,
                COALESCE((SELECT SUM(valor_centavos)
                            FROM movimentacoes_emprestimo
                           WHERE tipo = 'ABATIMENTO' AND substr(data_movimento, 1, 7) = ?), 0) AS abatimentos_mes_centavos,
                COALESCE((SELECT SUM(valor_centavos)
                            FROM movimentacoes_emprestimo
                           WHERE tipo IN ('JUROS', 'ABATIMENTO', 'QUITACAO')
                             AND substr(data_movimento, 1, 7) = ?), 0) AS recebimentos_mes_centavos
            """,
            (mes_atual, mes_atual, mes_atual),
        ).fetchone()

        ultimos_emprestimos = db.execute(
            """
            SELECT e.id,
                   e.data_emprestimo,
                   e.valor_original_centavos,
                   e.saldo_atual_centavos,
                   e.status,
                   c.id AS cliente_id,
                   c.nome AS cliente_nome
              FROM emprestimos e
              JOIN clientes c ON c.id = e.cliente_id
             ORDER BY e.id DESC
             LIMIT 5
            """
        ).fetchall()

        ultimas_movimentacoes = db.execute(
            """
            SELECT m.id, m.tipo, m.data_movimento, m.valor_centavos,
                   e.id AS emprestimo_id, c.nome AS cliente_nome
              FROM movimentacoes_emprestimo m
              JOIN emprestimos e ON e.id = m.emprestimo_id
              JOIN clientes c ON c.id = e.cliente_id
             WHERE m.tipo <> 'EMPRESTIMO'
             ORDER BY m.data_movimento DESC, m.id DESC
             LIMIT 6
            """
        ).fetchall()

        periodos_recebimento = get_receivable_periods()
        for periodo in periodos_recebimento.values():
            periodo["resumo"] = receivable_period_summary(db, periodo["inicio"], periodo["fim"])

        proximos_titulos = db.execute(
            """
            SELECT t.id, t.competencia, t.data_vencimento,
                   t.valor_previsto_centavos, t.status, t.natureza,
                   t.titulo_origem_id,
                   e.id AS emprestimo_id, c.nome AS cliente_nome
              FROM titulos_receber t
              JOIN emprestimos e ON e.id = t.emprestimo_id
              JOIN clientes c ON c.id = e.cliente_id
             WHERE t.status IN ('PREVISTO', 'VENCIDO')
             ORDER BY CASE WHEN t.status = 'VENCIDO' THEN 0 ELSE 1 END,
                      t.data_vencimento, c.nome COLLATE NOCASE
             LIMIT 8
            """
        ).fetchall()

        return render_template(
            "dashboard.html",
            metrics=metrics,
            ultimos_emprestimos=ultimos_emprestimos,
            ultimas_movimentacoes=ultimas_movimentacoes,
            mes_atual=mes_atual,
            periodos_recebimento=periodos_recebimento,
            proximos_titulos=proximos_titulos,
        )

    # -------------------- Relatório / Extrato por cliente --------------------

    @app.get("/relatorios/clientes")
    @login_required
    def relatorio_cliente():
        db = get_db()

        clientes = db.execute(
            """
            SELECT id, nome, ativo
              FROM clientes
             ORDER BY ativo DESC, nome COLLATE NOCASE
            """
        ).fetchall()

        cliente_id = parse_int(request.args.get("cliente_id"))
        cliente = None
        resumo = None
        emprestimos = []
        conferencia_mensal = []
        pendencias_competencia = []
        extrato = []
        resumo_periodo = None

        data_inicio_text = request.args.get("data_inicio", "").strip()
        data_fim_text = request.args.get("data_fim", "").strip()

        if cliente_id is not None:
            cliente = db.execute(
                "SELECT * FROM clientes WHERE id = ?",
                (cliente_id,),
            ).fetchone()

            if cliente is None:
                abort(404)

            sync_receivable_titles(db)

            limites = db.execute(
                """
                SELECT MIN(data_emprestimo) AS primeira_data
                  FROM emprestimos
                 WHERE cliente_id = ?
                """,
                (cliente_id,),
            ).fetchone()

            default_inicio = (
                date.fromisoformat(limites["primeira_data"])
                if limites and limites["primeira_data"]
                else date.today()
            )
            default_fim = date.today()

            data_inicio = (
                parse_iso_date(data_inicio_text)
                if data_inicio_text
                else default_inicio
            )
            data_fim = (
                parse_iso_date(data_fim_text)
                if data_fim_text
                else default_fim
            )

            if data_inicio is None:
                flash("Data inicial inválida.", "warning")
                data_inicio = default_inicio

            if data_fim is None:
                flash("Data final inválida.", "warning")
                data_fim = default_fim

            if data_inicio > data_fim:
                flash(
                    "A data inicial não pode ser posterior à data final.",
                    "warning",
                )
                data_inicio, data_fim = default_inicio, default_fim

            data_inicio_text = data_inicio.isoformat()
            data_fim_text = data_fim.isoformat()

            resumo = resumo_financeiro_cliente(db, cliente_id)
            emprestimos = posicao_emprestimos_cliente(db, cliente_id)
            conferencia_mensal, pendencias_competencia = conferencia_mensal_cliente(
                db,
                cliente_id,
                data_inicio,
                data_fim,
            )
            extrato, resumo_periodo = extrato_movimentacoes_cliente(
                db,
                cliente_id,
                data_inicio,
                data_fim,
            )

        return render_template(
            "relatorios/cliente_extrato.html",
            clientes=clientes,
            cliente=cliente,
            resumo=resumo,
            emprestimos=emprestimos,
            conferencia_mensal=conferencia_mensal,
            pendencias_competencia=pendencias_competencia,
            extrato=extrato,
            resumo_periodo=resumo_periodo,
            data_inicio=data_inicio_text,
            data_fim=data_fim_text,
        )


    # -------------------- Clientes --------------------

    @app.get("/clientes")
    @login_required
    def clientes_lista():
        termo = request.args.get("q", "").strip()
        status = request.args.get("status", "ativos").strip().lower()

        sql = """
            SELECT id, nome, telefone, email, cpf, cidade, estado, ativo, created_at
              FROM clientes
             WHERE 1 = 1
        """
        params: list[Any] = []

        if status == "ativos":
            sql += " AND ativo = 1"
        elif status == "inativos":
            sql += " AND ativo = 0"

        if termo:
            like = f"%{termo}%"
            sql += """
                AND (
                    nome LIKE ? COLLATE NOCASE
                    OR telefone LIKE ?
                    OR email LIKE ? COLLATE NOCASE
                    OR cpf LIKE ?
                )
            """
            params.extend([like, like, like, like])

        sql += " ORDER BY nome COLLATE NOCASE"

        clientes = get_db().execute(sql, params).fetchall()
        return render_template("clientes/lista.html", clientes=clientes, termo=termo, status=status)

    @app.route("/clientes/novo", methods=["GET", "POST"])
    @login_required
    def clientes_novo():
        if request.method == "POST":
            form = cliente_form_data()
            errors = validate_cliente(form)

            if errors:
                for error in errors:
                    flash(error, "danger")
                return render_template("clientes/form.html", cliente=form, titulo="Novo cliente")

            db = get_db()
            cursor = db.execute(
                """
                INSERT INTO clientes (
                    nome, telefone, email, cpf, endereco,
                    cidade, estado, cep, observacoes, ativo
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    form["nome"],
                    form["telefone"],
                    form["email"],
                    form["cpf"],
                    form["endereco"],
                    form["cidade"],
                    form["estado"],
                    form["cep"],
                    form["observacoes"],
                ),
            )
            cliente_id = cursor.lastrowid
            db.commit()

            flash("Cliente cadastrado com sucesso.", "success")
            return redirect(url_for("clientes_detalhe", cliente_id=cliente_id))

        return render_template("clientes/form.html", cliente={}, titulo="Novo cliente")

    @app.get("/clientes/<int:cliente_id>")
    @login_required
    def clientes_detalhe(cliente_id: int):
        cliente = get_cliente_or_404(cliente_id)

        db = get_db()
        emprestimos = db.execute(
            """
            SELECT id, descricao, data_emprestimo, valor_original_centavos,
                   saldo_atual_centavos, taxa_juros_mensal,
                   data_primeiro_vencimento, status
              FROM emprestimos
             WHERE cliente_id = ?
             ORDER BY id DESC
            """,
            (cliente_id,),
        ).fetchall()
        resumo_financeiro = resumo_financeiro_cliente(db, cliente_id)
        contas_bancarias = get_client_accounts(cliente_id, only_active=False)
        cartoes = db.execute(
            "SELECT id, descricao, ativo FROM cartoes_credito WHERE cliente_id = ? ORDER BY ativo DESC, id DESC",
            (cliente_id,),
        ).fetchall()

        return render_template(
            "clientes/detalhe.html",
            cliente=cliente,
            emprestimos=emprestimos,
            contas_bancarias=contas_bancarias,
            cartoes=cartoes,
            resumo_financeiro=resumo_financeiro,
        )

    @app.route("/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
    @login_required
    def clientes_editar(cliente_id: int):
        cliente_atual = get_cliente_or_404(cliente_id)

        if request.method == "POST":
            form = cliente_form_data()
            errors = validate_cliente(form, cliente_id=cliente_id)

            if errors:
                form["id"] = cliente_id
                form["ativo"] = cliente_atual["ativo"]
                for error in errors:
                    flash(error, "danger")
                return render_template("clientes/form.html", cliente=form, titulo="Editar cliente")

            db = get_db()
            db.execute(
                """
                UPDATE clientes
                   SET nome = ?,
                       telefone = ?,
                       email = ?,
                       cpf = ?,
                       endereco = ?,
                       cidade = ?,
                       estado = ?,
                       cep = ?,
                       observacoes = ?,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE id = ?
                """,
                (
                    form["nome"],
                    form["telefone"],
                    form["email"],
                    form["cpf"],
                    form["endereco"],
                    form["cidade"],
                    form["estado"],
                    form["cep"],
                    form["observacoes"],
                    cliente_id,
                ),
            )
            db.commit()

            flash("Cliente atualizado com sucesso.", "success")
            return redirect(url_for("clientes_detalhe", cliente_id=cliente_id))

        return render_template("clientes/form.html", cliente=cliente_atual, titulo="Editar cliente")

    @app.post("/clientes/<int:cliente_id>/status")
    @login_required
    def clientes_status(cliente_id: int):
        cliente = get_cliente_or_404(cliente_id)
        novo_status = 0 if cliente["ativo"] else 1

        db = get_db()
        db.execute(
            """
            UPDATE clientes
               SET ativo = ?, updated_at = CURRENT_TIMESTAMP
             WHERE id = ?
            """,
            (novo_status, cliente_id),
        )
        db.commit()

        flash(
            "Cliente ativado." if novo_status else "Cliente inativado.",
            "success",
        )
        return redirect(url_for("clientes_detalhe", cliente_id=cliente_id))

    # -------------------- Contas bancárias --------------------

    @app.get("/contas")
    @login_required
    def contas_lista():
        tipo = request.args.get("tipo", "todas").strip().lower()
        termo = request.args.get("q", "").strip()

        sql = """
            SELECT cb.*, c.nome AS cliente_nome
              FROM contas_bancarias cb
              LEFT JOIN clientes c ON c.id = cb.cliente_id
             WHERE 1 = 1
        """
        params: list[Any] = []

        if tipo == "nossas":
            sql += " AND cb.tipo_titular = 'NOSSA'"
        elif tipo == "clientes":
            sql += " AND cb.tipo_titular = 'CLIENTE'"

        if termo:
            like = f"%{termo}%"
            sql += """
                AND (
                    cb.banco LIKE ? COLLATE NOCASE
                    OR cb.descricao LIKE ? COLLATE NOCASE
                    OR cb.chave_pix LIKE ? COLLATE NOCASE
                    OR c.nome LIKE ? COLLATE NOCASE
                )
            """
            params.extend([like, like, like, like])

        sql += " ORDER BY cb.ativo DESC, cb.tipo_titular, cb.principal DESC, COALESCE(c.nome, ''), cb.banco"
        contas = get_db().execute(sql, params).fetchall()
        return render_template("contas/lista.html", contas=contas, tipo=tipo, termo=termo)

    @app.route("/contas/nova", methods=["GET", "POST"])
    @login_required
    def contas_nova():
        db = get_db()
        clientes = db.execute(
            "SELECT id, nome FROM clientes WHERE ativo = 1 ORDER BY nome COLLATE NOCASE"
        ).fetchall()
        cliente_query = request.args.get("cliente_id", type=int)
        tipo_query = "CLIENTE" if cliente_query else request.args.get("tipo", "NOSSA").upper()

        form = {
            "tipo_titular": request.form.get("tipo_titular", tipo_query),
            "cliente_id": request.form.get("cliente_id", str(cliente_query or "")),
            "banco": request.form.get("banco", ""),
            "descricao": request.form.get("descricao", ""),
            "agencia": request.form.get("agencia", ""),
            "conta": request.form.get("conta", ""),
            "tipo_conta": request.form.get("tipo_conta", ""),
            "chave_pix": request.form.get("chave_pix", ""),
            "principal": request.form.get("principal", "") == "1",
        }

        if request.method == "POST":
            tipo_titular = form["tipo_titular"].strip().upper()
            cliente_id = parse_int(form["cliente_id"])
            banco = form["banco"].strip()
            errors: list[str] = []

            if tipo_titular not in {"NOSSA", "CLIENTE"}:
                errors.append("Tipo de titular inválido.")
            if len(banco) < 2:
                errors.append("Informe o banco.")
            if tipo_titular == "CLIENTE":
                cliente = db.execute("SELECT id, ativo FROM clientes WHERE id = ?", (cliente_id,)).fetchone()
                if cliente is None or not cliente["ativo"]:
                    errors.append("Selecione um cliente ativo para a conta.")
            else:
                cliente_id = None

            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                try:
                    if form["principal"]:
                        if tipo_titular == "NOSSA":
                            db.execute("UPDATE contas_bancarias SET principal = 0 WHERE tipo_titular = 'NOSSA'")
                        else:
                            db.execute(
                                "UPDATE contas_bancarias SET principal = 0 WHERE tipo_titular = 'CLIENTE' AND cliente_id = ?",
                                (cliente_id,),
                            )

                    cursor = db.execute(
                        """
                        INSERT INTO contas_bancarias (
                            tipo_titular, cliente_id, banco, descricao, agencia, conta,
                            tipo_conta, chave_pix, principal, ativo
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                        """,
                        (
                            tipo_titular,
                            cliente_id,
                            banco,
                            normalize_optional(form["descricao"]),
                            normalize_optional(form["agencia"]),
                            normalize_optional(form["conta"]),
                            normalize_optional(form["tipo_conta"]),
                            normalize_optional(form["chave_pix"]),
                            1 if form["principal"] else 0,
                        ),
                    )
                    registrar_auditoria(db, "conta_bancaria", int(cursor.lastrowid), "CRIADA", f"Banco: {banco}.")
                    db.commit()
                except sqlite3.DatabaseError:
                    db.rollback()
                    app.logger.exception("Erro ao cadastrar conta bancária")
                    flash("Não foi possível cadastrar a conta bancária.", "danger")
                else:
                    flash("Conta bancária cadastrada.", "success")
                    if cliente_id:
                        return redirect(url_for("clientes_detalhe", cliente_id=cliente_id))
                    return redirect(url_for("contas_lista"))

        return render_template("contas/form.html", conta=form, clientes=clientes, titulo="Nova conta bancária")

    @app.route("/contas/<int:conta_id>/editar", methods=["GET", "POST"])
    @login_required
    def contas_editar(conta_id: int):
        db = get_db()
        conta = db.execute("SELECT * FROM contas_bancarias WHERE id = ?", (conta_id,)).fetchone()
        if conta is None:
            abort(404)

        clientes = db.execute(
            "SELECT id, nome FROM clientes WHERE ativo = 1 OR id = ? ORDER BY nome COLLATE NOCASE",
            (conta["cliente_id"],),
        ).fetchall()

        form = {
            "tipo_titular": conta["tipo_titular"],
            "cliente_id": str(conta["cliente_id"] or ""),
            "banco": conta["banco"] or "",
            "descricao": conta["descricao"] or "",
            "agencia": conta["agencia"] or "",
            "conta": conta["conta"] or "",
            "tipo_conta": conta["tipo_conta"] or "",
            "chave_pix": conta["chave_pix"] or "",
            "principal": bool(conta["principal"]),
        }

        if request.method == "POST":
            form.update({
                "tipo_titular": request.form.get("tipo_titular", ""),
                "cliente_id": request.form.get("cliente_id", ""),
                "banco": request.form.get("banco", ""),
                "descricao": request.form.get("descricao", ""),
                "agencia": request.form.get("agencia", ""),
                "conta": request.form.get("conta", ""),
                "tipo_conta": request.form.get("tipo_conta", ""),
                "chave_pix": request.form.get("chave_pix", ""),
                "principal": request.form.get("principal", "") == "1",
            })
            tipo_titular = form["tipo_titular"].strip().upper()
            cliente_id = parse_int(form["cliente_id"])
            errors: list[str] = []
            if tipo_titular not in {"NOSSA", "CLIENTE"}:
                errors.append("Tipo de titular inválido.")
            if len(form["banco"].strip()) < 2:
                errors.append("Informe o banco.")
            if tipo_titular == "CLIENTE":
                if db.execute("SELECT 1 FROM clientes WHERE id = ?", (cliente_id,)).fetchone() is None:
                    errors.append("Selecione um cliente válido.")
            else:
                cliente_id = None

            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                try:
                    if form["principal"]:
                        if tipo_titular == "NOSSA":
                            db.execute("UPDATE contas_bancarias SET principal = 0 WHERE tipo_titular = 'NOSSA' AND id <> ?", (conta_id,))
                        else:
                            db.execute(
                                "UPDATE contas_bancarias SET principal = 0 WHERE tipo_titular = 'CLIENTE' AND cliente_id = ? AND id <> ?",
                                (cliente_id, conta_id),
                            )
                    db.execute(
                        """
                        UPDATE contas_bancarias
                           SET tipo_titular = ?, cliente_id = ?, banco = ?, descricao = ?, agencia = ?,
                               conta = ?, tipo_conta = ?, chave_pix = ?, principal = ?, updated_at = CURRENT_TIMESTAMP
                         WHERE id = ?
                        """,
                        (
                            tipo_titular, cliente_id, form["banco"].strip(), normalize_optional(form["descricao"]),
                            normalize_optional(form["agencia"]), normalize_optional(form["conta"]),
                            normalize_optional(form["tipo_conta"]), normalize_optional(form["chave_pix"]),
                            1 if form["principal"] else 0, conta_id,
                        ),
                    )
                    registrar_auditoria(db, "conta_bancaria", conta_id, "EDITADA")
                    db.commit()
                except sqlite3.DatabaseError:
                    db.rollback()
                    app.logger.exception("Erro ao editar conta bancária")
                    flash("Não foi possível editar a conta bancária.", "danger")
                else:
                    flash("Conta bancária atualizada.", "success")
                    return redirect(url_for("contas_lista"))

        return render_template("contas/form.html", conta=form, clientes=clientes, titulo="Editar conta bancária")

    @app.post("/contas/<int:conta_id>/status")
    @login_required
    def contas_status(conta_id: int):
        db = get_db()
        conta = db.execute("SELECT id, ativo, principal FROM contas_bancarias WHERE id = ?", (conta_id,)).fetchone()
        if conta is None:
            abort(404)
        novo_status = 0 if conta["ativo"] else 1
        db.execute(
            "UPDATE contas_bancarias SET ativo = ?, principal = CASE WHEN ? = 0 THEN 0 ELSE principal END, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (novo_status, novo_status, conta_id),
        )
        registrar_auditoria(db, "conta_bancaria", conta_id, "ATIVADA" if novo_status else "INATIVADA")
        db.commit()
        flash("Conta bancária ativada." if novo_status else "Conta bancária inativada.", "success")
        return redirect(request.referrer or url_for("contas_lista"))

    # -------------------- Empréstimos --------------------

    @app.get("/emprestimos")
    @login_required
    def emprestimos_lista():
        termo = request.args.get("q", "").strip()
        status = request.args.get("status", "ativos").strip().lower()

        sql = """
            SELECT e.id,
                   e.descricao,
                   e.data_emprestimo,
                   e.valor_original_centavos,
                   e.saldo_atual_centavos,
                   e.taxa_juros_mensal,
                   e.data_primeiro_vencimento,
                   e.status,
                   c.id AS cliente_id,
                   c.nome AS cliente_nome
              FROM emprestimos e
              JOIN clientes c ON c.id = e.cliente_id
             WHERE 1 = 1
        """
        params: list[Any] = []

        status_map = {
            "ativos": "ATIVO",
            "quitados": "QUITADO",
            "vencidos": "VENCIDO",
        }
        if status in status_map:
            sql += " AND e.status = ?"
            params.append(status_map[status])

        if termo:
            like = f"%{termo}%"
            sql += """
                AND (
                    c.nome LIKE ? COLLATE NOCASE
                    OR e.descricao LIKE ? COLLATE NOCASE
                    OR CAST(e.id AS TEXT) LIKE ?
                )
            """
            params.extend([like, like, like])

        sql += " ORDER BY e.id DESC"

        emprestimos = get_db().execute(sql, params).fetchall()
        return render_template(
            "emprestimos/lista.html",
            emprestimos=emprestimos,
            termo=termo,
            status=status,
        )

    @app.route("/emprestimos/novo", methods=["GET", "POST"])
    @login_required
    def emprestimos_novo():
        db = get_db()
        clientes = db.execute(
            """
            SELECT id, nome, cpf
              FROM clientes
             WHERE ativo = 1
             ORDER BY nome COLLATE NOCASE
            """
        ).fetchall()

        if not clientes:
            flash("Cadastre e mantenha ao menos um cliente ativo antes de criar um empréstimo.", "warning")
            return redirect(url_for("clientes_novo"))

        cliente_id_query = request.args.get("cliente_id", type=int)
        contas_proprias = get_own_accounts()
        contas_clientes = db.execute(
            """
            SELECT cb.id, cb.cliente_id, cb.banco, cb.descricao, cb.chave_pix, cb.principal, c.nome AS cliente_nome
              FROM contas_bancarias cb
              JOIN clientes c ON c.id = cb.cliente_id
             WHERE cb.tipo_titular = 'CLIENTE'
               AND cb.ativo = 1
               AND c.ativo = 1
             ORDER BY c.nome COLLATE NOCASE, cb.principal DESC, cb.banco COLLATE NOCASE
            """
        ).fetchall()

        if request.method == "POST":
            form = emprestimo_form_data()
            errors = validate_emprestimo(form)

            if errors:
                for error in errors:
                    flash(error, "danger")
                return render_template(
                    "emprestimos/form.html",
                    emprestimo=form,
                    clientes=clientes,
                    contas_proprias=contas_proprias,
                    contas_clientes=contas_clientes,
                    titulo="Novo empréstimo",
                )

            cliente = db.execute(
                "SELECT id, nome, ativo FROM clientes WHERE id = ?",
                (form["cliente_id"],),
            ).fetchone()

            if cliente is None or not cliente["ativo"]:
                flash("O cliente selecionado não existe ou está inativo.", "danger")
                return render_template(
                    "emprestimos/form.html",
                    emprestimo=form,
                    clientes=clientes,
                    contas_proprias=contas_proprias,
                    contas_clientes=contas_clientes,
                    titulo="Novo empréstimo",
                )

            flow_errors = validate_money_flow_accounts(
                int(form["cliente_id"]),
                form["conta_origem_id"],
                form["conta_destino_id"],
                is_loan_disbursement=True,
            )
            if flow_errors:
                for error in flow_errors:
                    flash(error, "danger")
                return render_template(
                    "emprestimos/form.html",
                    emprestimo=form,
                    clientes=clientes,
                    contas_proprias=contas_proprias,
                    contas_clientes=contas_clientes,
                    titulo="Novo empréstimo",
                )

            valor_centavos = int(form["valor_original_centavos"])
            data_emprestimo = str(form["data_emprestimo"])
            data_primeiro_vencimento = str(form["data_primeiro_vencimento"])
            dia_vencimento = date.fromisoformat(data_primeiro_vencimento).day
            origem_banco, origem_pix, destino_banco, destino_pix = get_account_snapshots(
                form["conta_origem_id"], form["conta_destino_id"]
            )

            try:
                cursor = db.execute(
                    """
                    INSERT INTO emprestimos (
                        cliente_id,
                        descricao,
                        data_emprestimo,
                        valor_original_centavos,
                        saldo_atual_centavos,
                        taxa_juros_mensal,
                        data_primeiro_vencimento,
                        dia_vencimento,
                        status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ATIVO')
                    """,
                    (
                        form["cliente_id"],
                        form["descricao"],
                        data_emprestimo,
                        valor_centavos,
                        valor_centavos,
                        float(form["taxa_juros_mensal"]),
                        data_primeiro_vencimento,
                        dia_vencimento,
                    ),
                )
                emprestimo_id = cursor.lastrowid

                db.execute(
                    """
                    INSERT INTO movimentacoes_emprestimo (
                        emprestimo_id,
                        tipo,
                        data_movimento,
                        valor_centavos,
                        conta_origem_id,
                        conta_destino_id,
                        origem_banco_snapshot, origem_pix_snapshot,
                        destino_banco_snapshot, destino_pix_snapshot,
                        observacao,
                        usuario_id,
                        saldo_antes_centavos,
                        saldo_depois_centavos
                    ) VALUES (?, 'EMPRESTIMO', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        emprestimo_id,
                        data_emprestimo,
                        valor_centavos,
                        form["conta_origem_id"],
                        form["conta_destino_id"],
                        origem_banco, origem_pix, destino_banco, destino_pix,
                        "Registro automático da criação do empréstimo.",
                        g.usuario["id"],
                        0,
                        valor_centavos,
                    ),
                )

                registrar_auditoria(
                    db,
                    "emprestimo",
                    int(emprestimo_id),
                    "CRIADO",
                    f"Valor original: {valor_centavos} centavos.",
                )

                db.commit()
            except sqlite3.DatabaseError:
                db.rollback()
                app.logger.exception("Erro ao cadastrar empréstimo")
                flash("Não foi possível cadastrar o empréstimo. Nenhuma alteração foi gravada.", "danger")
                return render_template(
                    "emprestimos/form.html",
                    emprestimo=form,
                    clientes=clientes,
                    contas_proprias=contas_proprias,
                    contas_clientes=contas_clientes,
                    titulo="Novo empréstimo",
                ), 500

            flash("Empréstimo cadastrado com sucesso.", "success")
            return redirect(url_for("emprestimos_detalhe", emprestimo_id=emprestimo_id))

        emprestimo = {
            "cliente_id": cliente_id_query,
            "descricao": "",
            "data_emprestimo": date.today().isoformat(),
            "valor_original": "",
            "taxa_juros_mensal": "",
            "data_primeiro_vencimento": "",
            "conta_origem_id": contas_proprias[0]["id"] if contas_proprias else None,
            "conta_destino_id": next((c["id"] for c in contas_clientes if c["cliente_id"] == cliente_id_query), None),
        }

        return render_template(
            "emprestimos/form.html",
            emprestimo=emprestimo,
            clientes=clientes,
            contas_proprias=contas_proprias,
            contas_clientes=contas_clientes,
            titulo="Novo empréstimo",
        )

    @app.get("/emprestimos/<int:emprestimo_id>")
    @login_required
    def emprestimos_detalhe(emprestimo_id: int):
        emprestimo = get_emprestimo_or_404(emprestimo_id)
        db = get_db()

        movimentacoes = db.execute(
            """
            SELECT m.id, m.tipo, m.data_movimento, m.valor_centavos,
                   m.observacao, m.created_at, m.competencia,
                   m.pagamento_integrado_id,
                   m.saldo_antes_centavos, m.saldo_depois_centavos,
                   m.conta_origem_id, m.conta_destino_id,
                   u.nome AS usuario_nome,
                   COALESCE(m.origem_banco_snapshot, co.banco) AS origem_banco, COALESCE(m.origem_pix_snapshot, co.chave_pix) AS origem_pix,
                   COALESCE(m.destino_banco_snapshot, cd.banco) AS destino_banco, COALESCE(m.destino_pix_snapshot, cd.chave_pix) AS destino_pix
              FROM movimentacoes_emprestimo m
              LEFT JOIN usuarios u ON u.id = m.usuario_id
              LEFT JOIN contas_bancarias co ON co.id = m.conta_origem_id
              LEFT JOIN contas_bancarias cd ON cd.id = m.conta_destino_id
             WHERE m.emprestimo_id = ?
             ORDER BY m.data_movimento DESC, m.id DESC
            """,
            (emprestimo_id,),
        ).fetchall()

        resumo = db.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN tipo = 'JUROS' THEN valor_centavos ELSE 0 END), 0) AS juros_centavos,
                COALESCE(SUM(CASE WHEN tipo = 'ABATIMENTO' THEN valor_centavos ELSE 0 END), 0) AS abatimentos_centavos,
                COALESCE(SUM(CASE WHEN tipo = 'QUITACAO' THEN valor_centavos ELSE 0 END), 0) AS quitacoes_centavos
              FROM movimentacoes_emprestimo
             WHERE emprestimo_id = ?
            """,
            (emprestimo_id,),
        ).fetchone()

        juros_atual_centavos = calcular_juros_centavos(
            emprestimo["saldo_atual_centavos"],
            emprestimo["taxa_juros_mensal"],
        )

        return render_template(
            "emprestimos/detalhe.html",
            emprestimo=emprestimo,
            movimentacoes=movimentacoes,
            resumo=resumo,
            juros_atual_centavos=juros_atual_centavos,
        )

    @app.route("/emprestimos/<int:emprestimo_id>/juros", methods=["GET", "POST"])
    @login_required
    def emprestimos_juros(emprestimo_id: int):
        emprestimo = get_emprestimo_or_404(emprestimo_id)
        contas_cliente = get_client_accounts(emprestimo["cliente_id"])
        contas_proprias = get_own_accounts()

        if emprestimo["status"] == "QUITADO" or emprestimo["saldo_atual_centavos"] <= 0:
            flash("Este empréstimo já está quitado e não aceita novos juros.", "warning")
            return redirect(url_for("emprestimos_detalhe", emprestimo_id=emprestimo_id))

        juros_centavos = calcular_juros_centavos(
            emprestimo["saldo_atual_centavos"],
            emprestimo["taxa_juros_mensal"],
        )

        if juros_centavos <= 0:
            flash("A taxa atual não gera valor de juros para este saldo.", "warning")
            return redirect(url_for("emprestimos_detalhe", emprestimo_id=emprestimo_id))

        form = {
            "data_movimento": request.form.get("data_movimento", date.today().isoformat()),
            "competencia": request.form.get("competencia", date.today().strftime("%Y-%m")),
            "observacao": request.form.get("observacao", ""),
            "conta_origem_id": parse_int(request.form.get("conta_origem_id")) if request.method == "POST" else (contas_cliente[0]["id"] if contas_cliente else None),
            "conta_destino_id": parse_int(request.form.get("conta_destino_id")) if request.method == "POST" else (contas_proprias[0]["id"] if contas_proprias else None),
        }

        if request.method == "POST":
            data_movimento = parse_iso_date(form["data_movimento"])
            competencia = parse_competencia(form["competencia"])
            errors: list[str] = []

            if data_movimento is None:
                errors.append("Informe uma data válida para o lançamento dos juros.")
            elif data_movimento < date.fromisoformat(emprestimo["data_emprestimo"]):
                errors.append("A data dos juros não pode ser anterior ao empréstimo.")

            if competencia is None:
                errors.append("Informe uma competência válida para os juros.")
            elif competencia < emprestimo["data_emprestimo"][:7]:
                errors.append("A competência não pode ser anterior ao mês do empréstimo.")

            errors.extend(validate_money_flow_accounts(
                emprestimo["cliente_id"], form["conta_origem_id"], form["conta_destino_id"],
                is_loan_disbursement=False,
            ))

            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                db = get_db()
                duplicate = db.execute(
                    """
                    SELECT id
                      FROM movimentacoes_emprestimo
                     WHERE emprestimo_id = ?
                       AND tipo = 'JUROS'
                       AND competencia = ?
                     LIMIT 1
                    """,
                    (emprestimo_id, competencia),
                ).fetchone()

                if duplicate is not None:
                    flash(
                        f"Já existem juros lançados para a competência {format_competencia_br(competencia)}.",
                        "warning",
                    )
                else:
                    origem_banco, origem_pix, destino_banco, destino_pix = get_account_snapshots(
                        form["conta_origem_id"], form["conta_destino_id"]
                    )
                    try:
                        db.execute(
                            """
                            INSERT INTO movimentacoes_emprestimo (
                                emprestimo_id, tipo, data_movimento, valor_centavos,
                                observacao, competencia, usuario_id,
                                saldo_antes_centavos, saldo_depois_centavos,
                                conta_origem_id, conta_destino_id,
                                origem_banco_snapshot, origem_pix_snapshot,
                                destino_banco_snapshot, destino_pix_snapshot
                            ) VALUES (?, 'JUROS', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                emprestimo_id,
                                data_movimento.isoformat(),
                                juros_centavos,
                                normalize_optional(form["observacao"]),
                                competencia,
                                g.usuario["id"],
                                emprestimo["saldo_atual_centavos"],
                                emprestimo["saldo_atual_centavos"],
                                form["conta_origem_id"],
                                form["conta_destino_id"],
                                origem_banco, origem_pix, destino_banco, destino_pix,
                            ),
                        )
                        registrar_auditoria(
                            db,
                            "emprestimo",
                            emprestimo_id,
                            "JUROS_LANCADOS",
                            f"Competência {competencia}; valor {juros_centavos} centavos.",
                        )
                        db.commit()
                    except sqlite3.IntegrityError:
                        db.rollback()
                        flash("Os juros desta competência já foram lançados.", "warning")
                    else:
                        flash(
                            f"Juros de {format_money(juros_centavos)} registrados. O saldo principal não foi alterado.",
                            "success",
                        )
                        return redirect(url_for("emprestimos_detalhe", emprestimo_id=emprestimo_id))

        return render_template(
            "emprestimos/movimento.html",
            emprestimo=emprestimo,
            operacao="JUROS",
            form=form,
            valor_calculado_centavos=juros_centavos,
            contas_cliente=contas_cliente,
            contas_proprias=contas_proprias,
        )

    @app.route("/emprestimos/<int:emprestimo_id>/abatimento", methods=["GET", "POST"])
    @login_required
    def emprestimos_abatimento(emprestimo_id: int):
        emprestimo = get_emprestimo_or_404(emprestimo_id)
        contas_cliente = get_client_accounts(emprestimo["cliente_id"])
        contas_proprias = get_own_accounts()

        if emprestimo["status"] == "QUITADO" or emprestimo["saldo_atual_centavos"] <= 0:
            flash("Este empréstimo já está quitado.", "warning")
            return redirect(url_for("emprestimos_detalhe", emprestimo_id=emprestimo_id))

        form = {
            "data_movimento": request.form.get("data_movimento", date.today().isoformat()),
            "valor": request.form.get("valor", ""),
            "observacao": request.form.get("observacao", ""),
            "conta_origem_id": parse_int(request.form.get("conta_origem_id")) if request.method == "POST" else (contas_cliente[0]["id"] if contas_cliente else None),
            "conta_destino_id": parse_int(request.form.get("conta_destino_id")) if request.method == "POST" else (contas_proprias[0]["id"] if contas_proprias else None),
        }

        if request.method == "POST":
            data_movimento = parse_iso_date(form["data_movimento"])
            valor_centavos = parse_money_to_centavos(form["valor"])
            errors: list[str] = []

            if data_movimento is None:
                errors.append("Informe uma data válida para o abatimento.")
            elif data_movimento < date.fromisoformat(emprestimo["data_emprestimo"]):
                errors.append("A data do abatimento não pode ser anterior ao empréstimo.")

            if valor_centavos is None or valor_centavos <= 0:
                errors.append("Informe um valor de abatimento maior que zero.")
            elif valor_centavos >= emprestimo["saldo_atual_centavos"]:
                errors.append(
                    "O abatimento deve ser menor que o saldo atual. Para zerar o contrato, use Quitação."
                )

            errors.extend(validate_money_flow_accounts(
                emprestimo["cliente_id"], form["conta_origem_id"], form["conta_destino_id"],
                is_loan_disbursement=False,
            ))

            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                db = get_db()
                saldo_antes = int(emprestimo["saldo_atual_centavos"])
                saldo_depois = saldo_antes - int(valor_centavos)
                origem_banco, origem_pix, destino_banco, destino_pix = get_account_snapshots(
                    form["conta_origem_id"], form["conta_destino_id"]
                )

                try:
                    db.execute(
                        """
                        UPDATE emprestimos
                           SET saldo_atual_centavos = ?,
                               updated_at = CURRENT_TIMESTAMP
                         WHERE id = ?
                           AND status <> 'QUITADO'
                        """,
                        (saldo_depois, emprestimo_id),
                    )
                    db.execute(
                        """
                        INSERT INTO movimentacoes_emprestimo (
                            emprestimo_id, tipo, data_movimento, valor_centavos,
                            observacao, usuario_id,
                            saldo_antes_centavos, saldo_depois_centavos,
                            conta_origem_id, conta_destino_id,
                            origem_banco_snapshot, origem_pix_snapshot,
                            destino_banco_snapshot, destino_pix_snapshot
                        ) VALUES (?, 'ABATIMENTO', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            emprestimo_id,
                            data_movimento.isoformat(),
                            valor_centavos,
                            normalize_optional(form["observacao"]),
                            g.usuario["id"],
                            saldo_antes,
                            saldo_depois,
                            form["conta_origem_id"],
                            form["conta_destino_id"],
                            origem_banco, origem_pix, destino_banco, destino_pix,
                        ),
                    )
                    registrar_auditoria(
                        db,
                        "emprestimo",
                        emprestimo_id,
                        "ABATIMENTO",
                        f"Valor {valor_centavos} centavos; saldo {saldo_antes} -> {saldo_depois}.",
                    )
                    db.commit()
                except sqlite3.DatabaseError:
                    db.rollback()
                    app.logger.exception("Erro ao registrar abatimento")
                    flash("Não foi possível registrar o abatimento. Nada foi gravado.", "danger")
                else:
                    flash(
                        f"Abatimento de {format_money(valor_centavos)} registrado. Novo saldo: {format_money(saldo_depois)}.",
                        "success",
                    )
                    return redirect(url_for("emprestimos_detalhe", emprestimo_id=emprestimo_id))

        return render_template(
            "emprestimos/movimento.html",
            emprestimo=emprestimo,
            operacao="ABATIMENTO",
            form=form,
            valor_calculado_centavos=None,
            contas_cliente=contas_cliente,
            contas_proprias=contas_proprias,
        )

    @app.route("/emprestimos/<int:emprestimo_id>/quitacao", methods=["GET", "POST"])
    @login_required
    def emprestimos_quitacao(emprestimo_id: int):
        emprestimo = get_emprestimo_or_404(emprestimo_id)
        contas_cliente = get_client_accounts(emprestimo["cliente_id"])
        contas_proprias = get_own_accounts()

        if emprestimo["status"] == "QUITADO" or emprestimo["saldo_atual_centavos"] <= 0:
            flash("Este empréstimo já está quitado.", "warning")
            return redirect(url_for("emprestimos_detalhe", emprestimo_id=emprestimo_id))

        form = {
            "data_movimento": request.form.get("data_movimento", date.today().isoformat()),
            "observacao": request.form.get("observacao", ""),
            "conta_origem_id": parse_int(request.form.get("conta_origem_id")) if request.method == "POST" else (contas_cliente[0]["id"] if contas_cliente else None),
            "conta_destino_id": parse_int(request.form.get("conta_destino_id")) if request.method == "POST" else (contas_proprias[0]["id"] if contas_proprias else None),
        }

        if request.method == "POST":
            data_movimento = parse_iso_date(form["data_movimento"])
            errors: list[str] = []

            if data_movimento is None:
                errors.append("Informe uma data válida para a quitação.")
            elif data_movimento < date.fromisoformat(emprestimo["data_emprestimo"]):
                errors.append("A data da quitação não pode ser anterior ao empréstimo.")

            errors.extend(validate_money_flow_accounts(
                emprestimo["cliente_id"], form["conta_origem_id"], form["conta_destino_id"],
                is_loan_disbursement=False,
            ))

            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                db = get_db()
                saldo_antes = int(emprestimo["saldo_atual_centavos"])
                origem_banco, origem_pix, destino_banco, destino_pix = get_account_snapshots(
                    form["conta_origem_id"], form["conta_destino_id"]
                )

                try:
                    db.execute(
                        """
                        UPDATE emprestimos
                           SET saldo_atual_centavos = 0,
                               status = 'QUITADO',
                               updated_at = CURRENT_TIMESTAMP
                         WHERE id = ?
                           AND status <> 'QUITADO'
                        """,
                        (emprestimo_id,),
                    )
                    db.execute(
                        """
                        INSERT INTO movimentacoes_emprestimo (
                            emprestimo_id, tipo, data_movimento, valor_centavos,
                            observacao, usuario_id,
                            saldo_antes_centavos, saldo_depois_centavos,
                            conta_origem_id, conta_destino_id,
                            origem_banco_snapshot, origem_pix_snapshot,
                            destino_banco_snapshot, destino_pix_snapshot
                        ) VALUES (?, 'QUITACAO', ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            emprestimo_id,
                            data_movimento.isoformat(),
                            saldo_antes,
                            normalize_optional(form["observacao"]),
                            g.usuario["id"],
                            saldo_antes,
                            form["conta_origem_id"],
                            form["conta_destino_id"],
                            origem_banco, origem_pix, destino_banco, destino_pix,
                        ),
                    )
                    registrar_auditoria(
                        db,
                        "emprestimo",
                        emprestimo_id,
                        "QUITADO",
                        f"Saldo quitado: {saldo_antes} centavos.",
                    )
                    db.commit()
                except sqlite3.DatabaseError:
                    db.rollback()
                    app.logger.exception("Erro ao quitar empréstimo")
                    flash("Não foi possível quitar o empréstimo. Nada foi gravado.", "danger")
                else:
                    flash(
                        f"Empréstimo quitado. Valor de quitação: {format_money(saldo_antes)}.",
                        "success",
                    )
                    return redirect(url_for("emprestimos_detalhe", emprestimo_id=emprestimo_id))

        return render_template(
            "emprestimos/movimento.html",
            emprestimo=emprestimo,
            operacao="QUITACAO",
            form=form,
            valor_calculado_centavos=emprestimo["saldo_atual_centavos"],
            contas_cliente=contas_cliente,
            contas_proprias=contas_proprias,
        )

    # -------------------- Pagamentos integrados --------------------

    @app.get("/pagamentos-integrados")
    @login_required
    def pagamentos_integrados_lista():
        termo = request.args.get("q", "").strip()
        mes = request.args.get("mes", "").strip()

        sql = """
            SELECT p.id, p.data_pagamento, p.valor_total_centavos,
                   p.observacao, p.created_at,
                   c.id AS cliente_id, c.nome AS cliente_nome,
                   u.nome AS usuario_nome,
                   COUNT(i.id) AS quantidade_itens
              FROM pagamentos_integrados p
              JOIN clientes c ON c.id = p.cliente_id
              LEFT JOIN usuarios u ON u.id = p.usuario_id
              LEFT JOIN pagamentos_integrados_itens i
                     ON i.pagamento_integrado_id = p.id
             WHERE 1 = 1
        """
        params: list[Any] = []

        if parse_competencia(mes) is not None:
            sql += " AND substr(p.data_pagamento, 1, 7) = ?"
            params.append(mes)

        if termo:
            like = f"%{termo}%"
            sql += """
                AND (
                    c.nome LIKE ? COLLATE NOCASE
                    OR CAST(p.id AS TEXT) LIKE ?
                    OR p.observacao LIKE ? COLLATE NOCASE
                )
            """
            params.extend([like, like, like])

        sql += """
            GROUP BY p.id
            ORDER BY p.data_pagamento DESC, p.id DESC
            LIMIT 500
        """

        pagamentos = get_db().execute(sql, params).fetchall()

        return render_template(
            "pagamentos_integrados/lista.html",
            pagamentos=pagamentos,
            termo=termo,
            mes=mes,
        )

    @app.route("/pagamentos-integrados/novo", methods=["GET", "POST"])
    @login_required
    def pagamentos_integrados_novo():
        db = get_db()
        sync_receivable_titles(db)

        clientes = db.execute(
            """
            SELECT DISTINCT c.id, c.nome
              FROM clientes c
              JOIN emprestimos e ON e.cliente_id = c.id
             ORDER BY c.nome COLLATE NOCASE
            """
        ).fetchall()

        cliente_id = (
            parse_int(request.form.get("cliente_id"))
            if request.method == "POST"
            else parse_int(request.args.get("cliente_id"))
        )

        cliente = None
        emprestimos = []
        titulos_abertos = []
        contas_cliente = []
        contas_proprias = get_own_accounts()

        if cliente_id is not None:
            cliente = db.execute(
                "SELECT id, nome FROM clientes WHERE id = ?",
                (cliente_id,),
            ).fetchone()

            if cliente is not None:
                emprestimos = db.execute(
                    """
                    SELECT id, data_emprestimo, valor_original_centavos,
                           saldo_atual_centavos, taxa_juros_mensal,
                           data_primeiro_vencimento, dia_vencimento,
                           status, descricao
                      FROM emprestimos
                     WHERE cliente_id = ?
                     ORDER BY data_emprestimo, id
                    """,
                    (cliente_id,),
                ).fetchall()

                titulos_abertos = db.execute(
                    """
                    SELECT t.id, t.emprestimo_id, t.competencia,
                           t.data_vencimento, t.valor_previsto_centavos,
                           t.valor_recebido_centavos,
                           t.saldo_base_centavos, t.taxa_juros_mensal,
                           t.status, t.observacao, t.titulo_origem_id,
                           t.natureza, t.sequencia,
                           e.descricao, e.data_emprestimo
                      FROM titulos_receber t
                      JOIN emprestimos e ON e.id = t.emprestimo_id
                     WHERE e.cliente_id = ?
                       AND t.status IN ('PREVISTO', 'VENCIDO')
                       AND t.movimentacao_id IS NULL
                     ORDER BY
                           CASE WHEN t.status = 'VENCIDO' THEN 0 ELSE 1 END,
                           t.data_vencimento,
                           t.emprestimo_id
                    """,
                    (cliente_id,),
                ).fetchall()

                contas_cliente = get_client_accounts(cliente_id)

        form = {
            "cliente_id": cliente_id,
            "data_pagamento": request.form.get(
                "data_pagamento",
                date.today().isoformat(),
            ),
            "valor_total": request.form.get("valor_total", ""),
            "conta_origem_id": (
                parse_int(request.form.get("conta_origem_id"))
                if request.method == "POST"
                else (contas_cliente[0]["id"] if contas_cliente else None)
            ),
            "conta_destino_id": (
                parse_int(request.form.get("conta_destino_id"))
                if request.method == "POST"
                else (contas_proprias[0]["id"] if contas_proprias else None)
            ),
            "observacao": request.form.get("observacao", ""),
        }

        selected_title_ids: list[int] = []
        for value in request.form.getlist("titulo_id"):
            parsed = parse_int(value)
            if parsed is not None and parsed not in selected_title_ids:
                selected_title_ids.append(parsed)

        selected_manual_ids: list[int] = []
        for value in request.form.getlist("emprestimo_manual_id"):
            parsed = parse_int(value)
            if parsed is not None and parsed not in selected_manual_ids:
                selected_manual_ids.append(parsed)

        if request.method == "POST":
            errors: list[str] = []

            if cliente is None:
                errors.append("Selecione um cliente válido.")

            data_pagamento = parse_iso_date(form["data_pagamento"])
            if data_pagamento is None:
                errors.append("Informe uma data válida para o pagamento.")

            valor_total_centavos = parse_money_to_centavos(form["valor_total"])
            if valor_total_centavos is None or valor_total_centavos <= 0:
                errors.append("Informe o valor total recebido.")

            if cliente is not None:
                errors.extend(
                    validate_money_flow_accounts(
                        cliente_id,
                        form["conta_origem_id"],
                        form["conta_destino_id"],
                        is_loan_disbursement=False,
                    )
                )

            itens: list[dict[str, Any]] = []
            total_rateado = 0
            pares_usados: set[tuple[int, str]] = set()

            # 1) Títulos já em aberto. O usuário pode baixar o valor integral
            # ou apenas uma parte. No pagamento parcial, o título selecionado
            # vira PARCIAL e nasce um novo SALDO_JUROS com a mesma competência
            # e vencimento, relacionado ao documento anterior.
            if cliente is not None:
                titulos_by_id = {int(row["id"]): row for row in titulos_abertos}

                for titulo_id in selected_title_ids:
                    titulo = titulos_by_id.get(titulo_id)

                    if titulo is None:
                        errors.append(
                            f"O título #{titulo_id} não está mais disponível em aberto "
                            "para este cliente."
                        )
                        continue

                    par = (
                        int(titulo["emprestimo_id"]),
                        str(titulo["competencia"]),
                    )
                    if par in pares_usados:
                        errors.append(
                            f"O empréstimo #{par[0]} / "
                            f"{format_competencia_br(par[1])} foi selecionado mais de uma vez."
                        )
                        continue

                    valor_documento = int(titulo["valor_previsto_centavos"])
                    valor_item = parse_money_to_centavos(
                        request.form.get(
                            f"valor_titulo_{titulo_id}",
                            format_money(valor_documento).replace("R$ ", ""),
                        )
                    )

                    if valor_item is None or valor_item <= 0:
                        errors.append(
                            f"Informe o valor recebido do título #{titulo_id}."
                        )
                        continue

                    if valor_item > valor_documento:
                        errors.append(
                            f"Título #{titulo_id}: o valor recebido não pode superar "
                            f"o saldo do documento ({format_money(valor_documento)})."
                        )
                        continue

                    pares_usados.add(par)
                    itens.append(
                        {
                            "emprestimo_id": par[0],
                            "competencia": par[1],
                            "valor_centavos": int(valor_item),
                            "valor_integral_centavos": valor_documento,
                            "saldo_base_centavos": int(titulo["saldo_base_centavos"]),
                            "taxa_juros_mensal": titulo["taxa_juros_mensal"],
                            "titulo_receber_id": titulo_id,
                            "origem_item": "TITULO",
                            "parcial": int(valor_item) < valor_documento,
                        }
                    )
                    total_rateado += int(valor_item)

            # 2) Lançamentos manuais/históricos para competências que ainda
            # não possuem documento aberto. O valor pode ser integral ou parcial.
            # Quando parcial, o sistema cria o documento original e, em seguida,
            # um SALDO_JUROS vinculado para o restante.
            if cliente is not None and data_pagamento is not None:
                loans_by_id = {int(row["id"]): row for row in emprestimos}

                for emprestimo_id in selected_manual_ids:
                    loan = loans_by_id.get(emprestimo_id)

                    if loan is None:
                        errors.append(
                            f"O empréstimo #{emprestimo_id} não pertence ao cliente selecionado."
                        )
                        continue

                    competencia = parse_competencia(
                        request.form.get(
                            f"competencia_manual_{emprestimo_id}",
                            "",
                        )
                    )
                    valor_item = parse_money_to_centavos(
                        request.form.get(
                            f"valor_manual_{emprestimo_id}",
                            "",
                        )
                    )

                    if competencia is None:
                        errors.append(
                            f"Informe a competência dos juros do empréstimo #{emprestimo_id}."
                        )
                        continue

                    if competencia < loan["data_emprestimo"][:7]:
                        errors.append(
                            f"A competência do empréstimo #{emprestimo_id} "
                            "não pode ser anterior ao contrato."
                        )
                        continue

                    if valor_item is None or valor_item <= 0:
                        errors.append(
                            f"Informe o valor de juros do empréstimo #{emprestimo_id}."
                        )
                        continue

                    par = (emprestimo_id, competencia)
                    if par in pares_usados:
                        errors.append(
                            f"O empréstimo #{emprestimo_id} / "
                            f"{format_competencia_br(competencia)} já foi selecionado "
                            "na seção de títulos em aberto."
                        )
                        continue

                    titulo_aberto = db.execute(
                        """
                        SELECT id
                          FROM titulos_receber
                         WHERE emprestimo_id = ?
                           AND tipo = 'JUROS'
                           AND competencia = ?
                           AND status IN ('PREVISTO', 'VENCIDO')
                         ORDER BY sequencia DESC, id DESC
                         LIMIT 1
                        """,
                        par,
                    ).fetchone()

                    if titulo_aberto is not None:
                        errors.append(
                            f"Existe o título em aberto #{titulo_aberto['id']} para o "
                            f"empréstimo #{emprestimo_id} / "
                            f"{format_competencia_br(competencia)}. "
                            "Selecione esse título na seção 'Títulos em aberto'."
                        )
                        continue

                    # Se já houve recebimentos na competência sem saldo em aberto,
                    # consideramos a obrigação encerrada e evitamos novo manual.
                    recebido_competencia = int(
                        db.execute(
                            """
                            SELECT COALESCE(SUM(valor_centavos), 0) AS total
                              FROM movimentacoes_emprestimo
                             WHERE emprestimo_id = ?
                               AND tipo = 'JUROS'
                               AND competencia = ?
                            """,
                            par,
                        ).fetchone()["total"]
                    )

                    try:
                        saldo_base = saldo_principal_antes_da_data(
                            db,
                            emprestimo_id,
                            data_pagamento,
                        )
                    except ValueError as exc:
                        errors.append(str(exc))
                        continue

                    if saldo_base <= 0:
                        errors.append(
                            f"O empréstimo #{emprestimo_id} não possuía saldo "
                            "devedor na data informada."
                        )
                        continue

                    juros_esperado = calcular_juros_centavos(
                        saldo_base,
                        loan["taxa_juros_mensal"],
                    )

                    if recebido_competencia >= juros_esperado:
                        errors.append(
                            f"O empréstimo #{emprestimo_id} já possui "
                            f"{format_money(recebido_competencia)} de juros recebidos "
                            f"para {format_competencia_br(competencia)}."
                        )
                        continue

                    saldo_obrigacao = juros_esperado - recebido_competencia
                    if valor_item > saldo_obrigacao:
                        errors.append(
                            f"Empréstimo #{emprestimo_id}: o saldo de juros da competência "
                            f"é {format_money(saldo_obrigacao)}. O valor informado "
                            f"({format_money(valor_item)}) é maior que o devido."
                        )
                        continue

                    # Se já houve algum pagamento na competência mas não há título
                    # em aberto, não inventamos nova cadeia silenciosamente.
                    if recebido_competencia > 0:
                        errors.append(
                            f"O empréstimo #{emprestimo_id} já possui recebimento parcial "
                            f"de {format_money(recebido_competencia)} em "
                            f"{format_competencia_br(competencia)}, mas não há documento "
                            "de saldo em aberto. Corrija a agenda antes de continuar."
                        )
                        continue

                    due_day = int(
                        loan["dia_vencimento"]
                        or (
                            date.fromisoformat(loan["data_primeiro_vencimento"]).day
                            if loan["data_primeiro_vencimento"]
                            else date.fromisoformat(loan["data_emprestimo"]).day
                        )
                    )
                    vencimento_documento = due_date_for_competence(
                        competencia,
                        due_day,
                    )

                    pares_usados.add(par)
                    itens.append(
                        {
                            "emprestimo_id": emprestimo_id,
                            "competencia": competencia,
                            "valor_centavos": int(valor_item),
                            "valor_integral_centavos": int(juros_esperado),
                            "saldo_base_centavos": int(saldo_base),
                            "taxa_juros_mensal": loan["taxa_juros_mensal"],
                            "titulo_receber_id": None,
                            "origem_item": "MANUAL",
                            "parcial": int(valor_item) < int(juros_esperado),
                            "data_vencimento": vencimento_documento,
                        }
                    )
                    total_rateado += int(valor_item)

            emprestimos_distintos = {
                int(item["emprestimo_id"])
                for item in itens
            }
            if len(emprestimos_distintos) < 2:
                errors.append(
                    "Um pagamento integrado precisa distribuir o recebimento "
                    "entre pelo menos dois empréstimos diferentes."
                )

            if (
                valor_total_centavos is not None
                and valor_total_centavos > 0
                and total_rateado != valor_total_centavos
            ):
                errors.append(
                    "A soma dos rateios "
                    f"({format_money(total_rateado)}) precisa ser exatamente igual "
                    f"ao valor total recebido ({format_money(valor_total_centavos)})."
                )

            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                origem_banco, origem_pix, destino_banco, destino_pix = get_account_snapshots(
                    form["conta_origem_id"],
                    form["conta_destino_id"],
                )

                try:
                    cursor = db.execute(
                        """
                        INSERT INTO pagamentos_integrados (
                            cliente_id, data_pagamento, valor_total_centavos,
                            conta_origem_id, conta_destino_id,
                            origem_banco_snapshot, origem_pix_snapshot,
                            destino_banco_snapshot, destino_pix_snapshot,
                            observacao, usuario_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            cliente_id,
                            data_pagamento.isoformat(),
                            valor_total_centavos,
                            form["conta_origem_id"],
                            form["conta_destino_id"],
                            origem_banco,
                            origem_pix,
                            destino_banco,
                            destino_pix,
                            normalize_optional(form["observacao"]),
                            g.usuario["id"],
                        ),
                    )
                    pagamento_id = int(cursor.lastrowid)

                    auditoria_itens: list[dict[str, Any]] = []

                    for item in itens:
                        # Em um item manual parcial, criamos primeiro o documento
                        # original de juros. A movimentação deste pagamento ficará
                        # vinculada a ele e a baixa criará o SALDO_JUROS.
                        if (
                            item["titulo_receber_id"] is None
                            and item["origem_item"] == "MANUAL"
                            and item.get("parcial")
                        ):
                            item["titulo_receber_id"] = criar_titulo_manual_parcial(
                                db,
                                emprestimo_id=item["emprestimo_id"],
                                competencia=item["competencia"],
                                data_vencimento=item["data_vencimento"],
                                valor_integral_centavos=item["valor_integral_centavos"],
                                saldo_base_centavos=item["saldo_base_centavos"],
                                taxa_juros_mensal=item["taxa_juros_mensal"],
                            )

                        observacao_movimento = f"Pagamento integrado #{pagamento_id}"
                        if item["titulo_receber_id"] is not None:
                            observacao_movimento += (
                                f" — Título a receber #{item['titulo_receber_id']}"
                            )
                        if item.get("parcial"):
                            observacao_movimento += " — RECEBIMENTO PARCIAL DE JUROS"

                        if normalize_optional(form["observacao"]):
                            observacao_movimento += (
                                f" — {normalize_optional(form['observacao'])}"
                            )

                        cursor_mov = db.execute(
                            """
                            INSERT INTO movimentacoes_emprestimo (
                                emprestimo_id, tipo, data_movimento,
                                valor_centavos, observacao, competencia,
                                usuario_id, saldo_antes_centavos,
                                saldo_depois_centavos,
                                conta_origem_id, conta_destino_id,
                                origem_banco_snapshot, origem_pix_snapshot,
                                destino_banco_snapshot, destino_pix_snapshot,
                                pagamento_integrado_id, titulo_receber_id
                            ) VALUES (
                                ?, 'JUROS', ?, ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?, ?, ?, ?, ?
                            )
                            """,
                            (
                                item["emprestimo_id"],
                                data_pagamento.isoformat(),
                                item["valor_centavos"],
                                observacao_movimento,
                                item["competencia"],
                                g.usuario["id"],
                                item["saldo_base_centavos"],
                                item["saldo_base_centavos"],
                                form["conta_origem_id"],
                                form["conta_destino_id"],
                                origem_banco,
                                origem_pix,
                                destino_banco,
                                destino_pix,
                                pagamento_id,
                                item["titulo_receber_id"],
                            ),
                        )
                        movimento_id = int(cursor_mov.lastrowid)

                        db.execute(
                            """
                            INSERT INTO pagamentos_integrados_itens (
                                pagamento_integrado_id, emprestimo_id,
                                tipo, competencia, valor_centavos,
                                saldo_base_centavos, movimentacao_id,
                                titulo_receber_id, origem_item
                            ) VALUES (?, ?, 'JUROS', ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                pagamento_id,
                                item["emprestimo_id"],
                                item["competencia"],
                                item["valor_centavos"],
                                item["saldo_base_centavos"],
                                movimento_id,
                                item["titulo_receber_id"],
                                item["origem_item"],
                            ),
                        )

                        titulo_saldo_id = None
                        if item["titulo_receber_id"] is not None:
                            titulo_saldo_id = aplicar_recebimento_titulo(
                                db,
                                titulo_id=item["titulo_receber_id"],
                                valor_recebido_centavos=item["valor_centavos"],
                                movimentacao_id=movimento_id,
                                data_recebimento=data_pagamento,
                                observacao=observacao_movimento,
                            )

                        auditoria_itens.append(
                            {
                                **item,
                                "movimentacao_id": movimento_id,
                                "titulo_saldo_id": titulo_saldo_id,
                            }
                        )

                    registrar_auditoria(
                        db,
                        "pagamento_integrado",
                        pagamento_id,
                        "CRIADO",
                        json.dumps(
                            {
                                "cliente_id": cliente_id,
                                "data_pagamento": data_pagamento.isoformat(),
                                "valor_total_centavos": valor_total_centavos,
                                "itens": auditoria_itens,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                            # Itens manuais carregam data_vencimento como
                            # datetime.date. A auditoria precisa transformá-la
                            # em texto ISO para não provocar TypeError/HTTP 500.
                            default=lambda value: (
                                value.isoformat()
                                if isinstance(value, (date, datetime))
                                else str(value)
                            ),
                        ),
                    )

                    # Cabeçalho, rateios, movimentos e baixa dos títulos
                    # são persistidos em uma única transação.
                    db.commit()

                except Exception as exc:
                    db.rollback()
                    app.logger.exception("Erro ao registrar pagamento integrado")
                    flash(
                        "O pagamento integrado não foi gravado. "
                        f"Erro interno: {type(exc).__name__}: {exc}",
                        "danger",
                    )
                else:
                    flash(
                        f"Pagamento integrado #{pagamento_id} registrado. "
                        f"{len(itens)} juros foram baixados.",
                        "success",
                    )
                    return redirect(
                        url_for(
                            "pagamentos_integrados_detalhe",
                            pagamento_id=pagamento_id,
                        )
                    )

        default_competencia = (
            form["data_pagamento"][:7]
            if len(form["data_pagamento"]) >= 7
            else date.today().strftime("%Y-%m")
        )

        linhas_form: dict[int, dict[str, Any]] = {}
        for loan in emprestimos:
            loan_id = int(loan["id"])
            linhas_form[loan_id] = {
                "selected": loan_id in selected_manual_ids,
                "competencia": request.form.get(
                    f"competencia_manual_{loan_id}",
                    default_competencia,
                ),
                "valor": request.form.get(
                    f"valor_manual_{loan_id}",
                    format_money(
                        calcular_juros_centavos(
                            loan["saldo_atual_centavos"],
                            loan["taxa_juros_mensal"],
                        )
                    ).replace("R$ ", ""),
                ),
            }

        return render_template(
            "pagamentos_integrados/form.html",
            clientes=clientes,
            cliente=cliente,
            emprestimos=emprestimos,
            titulos_abertos=titulos_abertos,
            selected_title_ids=selected_title_ids,
            contas_cliente=contas_cliente,
            contas_proprias=contas_proprias,
            form=form,
            linhas_form=linhas_form,
        )

    @app.get("/pagamentos-integrados/<int:pagamento_id>")
    @login_required
    def pagamentos_integrados_detalhe(pagamento_id: int):
        pagamento = get_pagamento_integrado_or_404(pagamento_id)
        itens = get_db().execute(
            """
            SELECT i.id, i.emprestimo_id, i.competencia,
                   i.valor_centavos, i.saldo_base_centavos,
                   i.movimentacao_id, i.titulo_receber_id, i.origem_item,
                   e.taxa_juros_mensal, e.descricao,
                   t.status AS titulo_status,
                   t.valor_previsto_centavos AS titulo_valor_centavos,
                   s.id AS titulo_saldo_id,
                   s.valor_previsto_centavos AS titulo_saldo_centavos,
                   s.status AS titulo_saldo_status
              FROM pagamentos_integrados_itens i
              JOIN emprestimos e ON e.id = i.emprestimo_id
              LEFT JOIN titulos_receber t ON t.id = i.titulo_receber_id
              LEFT JOIN titulos_receber s ON s.titulo_origem_id = t.id
             WHERE i.pagamento_integrado_id = ?
             ORDER BY i.id
            """,
            (pagamento_id,),
        ).fetchall()

        return render_template(
            "pagamentos_integrados/detalhe.html",
            pagamento=pagamento,
            itens=itens,
        )

    @app.route(
        "/pagamentos-integrados/<int:pagamento_id>/excluir",
        methods=["GET", "POST"],
    )
    @login_required
    def pagamentos_integrados_excluir(pagamento_id: int):
        pagamento = get_pagamento_integrado_or_404(pagamento_id)
        db = get_db()

        itens = db.execute(
            """
            SELECT i.*, m.data_movimento
              FROM pagamentos_integrados_itens i
              JOIN movimentacoes_emprestimo m ON m.id = i.movimentacao_id
             WHERE i.pagamento_integrado_id = ?
             ORDER BY i.id
            """,
            (pagamento_id,),
        ).fetchall()

        if request.method == "POST":
            senha = request.form.get("senha_confirmacao", "")
            motivo = request.form.get("motivo_exclusao", "").strip()
            errors: list[str] = []

            if not validar_senha_usuario_atual(senha):
                errors.append("A senha de confirmação do usuário logado é inválida.")

            if len(motivo) < 5:
                errors.append(
                    "Informe o motivo da exclusão com pelo menos 5 caracteres."
                )

            # Um pagamento antigo não pode ser removido se o saldo criado por
            # ele já foi baixado em outro recebimento. Nesse caso o usuário deve
            # desfazer primeiro o pagamento mais recente da cadeia.
            title_actions: list[dict[str, Any]] = []
            for item in itens:
                titulo_id = item["titulo_receber_id"]
                if titulo_id is None:
                    continue

                descendants = db.execute(
                    """
                    WITH RECURSIVE arvore(id, movimentacao_id, status, depth) AS (
                        SELECT id, movimentacao_id, status, 1
                          FROM titulos_receber
                         WHERE titulo_origem_id = ?
                        UNION ALL
                        SELECT t.id, t.movimentacao_id, t.status, a.depth + 1
                          FROM titulos_receber t
                          JOIN arvore a ON t.titulo_origem_id = a.id
                    )
                    SELECT * FROM arvore ORDER BY depth DESC, id DESC
                    """,
                    (titulo_id,),
                ).fetchall()

                paid_descendant = next(
                    (
                        row
                        for row in descendants
                        if row["movimentacao_id"] is not None
                        or row["status"] in {"PARCIAL", "RECEBIDO"}
                    ),
                    None,
                )
                if paid_descendant is not None:
                    errors.append(
                        f"O título #{titulo_id} gerou o saldo #{paid_descendant['id']}, "
                        "que já possui recebimento posterior. Exclua primeiro o "
                        "pagamento mais recente dessa cadeia."
                    )
                    continue

                title_actions.append(
                    {
                        "titulo_id": int(titulo_id),
                        "origem_item": item["origem_item"],
                        "descendants": [int(row["id"]) for row in descendants],
                    }
                )

            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                snapshot = {
                    "pagamento": dict(pagamento),
                    "itens": [dict(item) for item in itens],
                    "motivo": motivo,
                }

                try:
                    # Remove primeiro as referências aos títulos e movimentos.
                    db.execute(
                        "DELETE FROM pagamentos_integrados_itens WHERE pagamento_integrado_id = ?",
                        (pagamento_id,),
                    )
                    db.execute(
                        "DELETE FROM movimentacoes_emprestimo WHERE pagamento_integrado_id = ?",
                        (pagamento_id,),
                    )

                    for action in title_actions:
                        for descendant_id in action["descendants"]:
                            db.execute(
                                "DELETE FROM titulos_receber WHERE id = ?",
                                (descendant_id,),
                            )

                        if action["origem_item"] == "MANUAL":
                            # Título sintético criado exclusivamente porque o
                            # lançamento manual foi parcial.
                            db.execute(
                                "DELETE FROM titulos_receber WHERE id = ?",
                                (action["titulo_id"],),
                            )
                        else:
                            # O título já existia antes do pagamento: reabre.
                            db.execute(
                                """
                                UPDATE titulos_receber
                                   SET status = CASE
                                           WHEN data_vencimento < date('now')
                                           THEN 'VENCIDO'
                                           ELSE 'PREVISTO'
                                       END,
                                       valor_recebido_centavos = 0,
                                       movimentacao_id = NULL,
                                       data_recebimento = NULL,
                                       updated_at = CURRENT_TIMESTAMP
                                 WHERE id = ?
                                """,
                                (action["titulo_id"],),
                            )

                    db.execute(
                        "DELETE FROM pagamentos_integrados WHERE id = ?",
                        (pagamento_id,),
                    )

                    registrar_auditoria(
                        db,
                        "pagamento_integrado",
                        pagamento_id,
                        "EXCLUIDO",
                        json.dumps(
                            snapshot,
                            ensure_ascii=False,
                            sort_keys=True,
                            default=str,
                        ),
                    )
                    db.commit()

                except sqlite3.DatabaseError as exc:
                    db.rollback()
                    app.logger.exception("Erro ao excluir pagamento integrado")
                    flash(
                        f"O pagamento integrado não foi excluído: {exc}",
                        "danger",
                    )
                else:
                    flash(
                        f"Pagamento integrado #{pagamento_id} excluído. "
                        "Os lançamentos e eventuais saldos parciais criados por ele "
                        "também foram revertidos.",
                        "success",
                    )
                    return redirect(url_for("pagamentos_integrados_lista"))

        return render_template(
            "pagamentos_integrados/excluir.html",
            pagamento=pagamento,
            itens=itens,
        )


    # -------------------- Movimentações --------------------

    @app.route("/movimentacoes/<int:movimentacao_id>/editar", methods=["GET", "POST"])
    @login_required
    def movimentacoes_editar(movimentacao_id: int):
        movimento = get_movimentacao_or_404(movimentacao_id)

        if movimento["pagamento_integrado_id"] is not None:
            flash(
                "Esta movimentação faz parte de um pagamento integrado. "
                "Para preservar o fechamento do pagamento, abra o pagamento integrado.",
                "warning",
            )
            return redirect(
                url_for(
                    "pagamentos_integrados_detalhe",
                    pagamento_id=movimento["pagamento_integrado_id"],
                )
            )
        emprestimo = get_emprestimo_or_404(movimento["emprestimo_id"])
        contas_cliente = get_client_accounts(emprestimo["cliente_id"])
        contas_proprias = get_own_accounts()

        form = {
            "data_movimento": request.form.get("data_movimento", movimento["data_movimento"]),
            "competencia": request.form.get("competencia", movimento["competencia"] or ""),
            "valor": request.form.get("valor", format_money(movimento["valor_centavos"]).replace("R$ ", "")),
            "conta_origem_id": parse_int(request.form.get("conta_origem_id")) if request.method == "POST" else movimento["conta_origem_id"],
            "conta_destino_id": parse_int(request.form.get("conta_destino_id")) if request.method == "POST" else movimento["conta_destino_id"],
            "observacao": request.form.get("observacao", movimento["observacao"] or ""),
            "motivo_correcao": request.form.get("motivo_correcao", ""),
        }

        if request.method == "POST":
            errors: list[str] = []
            senha = request.form.get("senha_confirmacao", "")
            motivo = form["motivo_correcao"].strip()

            if not validar_senha_usuario_atual(senha):
                errors.append("A senha de confirmação do usuário logado é inválida.")

            if len(motivo) < 5:
                errors.append("Informe o motivo da correção com pelo menos 5 caracteres.")

            if movimento["tipo"] == "EMPRESTIMO":
                data_movimento = date.fromisoformat(movimento["data_movimento"])
            else:
                data_movimento = parse_iso_date(form["data_movimento"])
                if data_movimento is None:
                    errors.append("Informe uma data válida para a movimentação.")
                elif data_movimento < date.fromisoformat(emprestimo["data_emprestimo"]):
                    errors.append("A data não pode ser anterior à data do empréstimo.")

            competencia = movimento["competencia"]
            if movimento["tipo"] == "JUROS":
                competencia = parse_competencia(form["competencia"])
                if competencia is None:
                    errors.append("Informe uma competência válida para os juros.")
                elif competencia < emprestimo["data_emprestimo"][:7]:
                    errors.append("A competência não pode ser anterior ao mês do empréstimo.")
                elif competencia != movimento["competencia"]:
                    duplicate = get_db().execute(
                        """
                        SELECT id
                          FROM movimentacoes_emprestimo
                         WHERE emprestimo_id = ?
                           AND tipo = 'JUROS'
                           AND competencia = ?
                           AND id <> ?
                         LIMIT 1
                        """,
                        (movimento["emprestimo_id"], competencia, movimentacao_id),
                    ).fetchone()
                    if duplicate:
                        errors.append(
                            f"Já existem juros para {format_competencia_br(competencia)} neste empréstimo."
                        )

            valor_centavos = int(movimento["valor_centavos"])
            if movimento["tipo"] == "ABATIMENTO":
                valor_editado = parse_money_to_centavos(form["valor"])
                if valor_editado is None or valor_editado <= 0:
                    errors.append("Informe um valor de abatimento maior que zero.")
                else:
                    valor_centavos = int(valor_editado)

            errors.extend(
                validate_money_flow_accounts(
                    emprestimo["cliente_id"],
                    form["conta_origem_id"],
                    form["conta_destino_id"],
                    is_loan_disbursement=movimento["tipo"] == "EMPRESTIMO",
                )
            )

            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                db = get_db()
                before = movimentacao_para_auditoria(movimento)

                origem_banco = movimento["origem_banco_snapshot"]
                origem_pix = movimento["origem_pix_snapshot"]
                destino_banco = movimento["destino_banco_snapshot"]
                destino_pix = movimento["destino_pix_snapshot"]

                if form["conta_origem_id"] != movimento["conta_origem_id"]:
                    origem = get_account(form["conta_origem_id"])
                    origem_banco = origem["banco"] if origem else None
                    origem_pix = origem["chave_pix"] if origem else None

                if form["conta_destino_id"] != movimento["conta_destino_id"]:
                    destino = get_account(form["conta_destino_id"])
                    destino_banco = destino["banco"] if destino else None
                    destino_pix = destino["chave_pix"] if destino else None

                try:
                    db.execute(
                        """
                        UPDATE movimentacoes_emprestimo
                           SET data_movimento = ?, competencia = ?, valor_centavos = ?,
                               conta_origem_id = ?, conta_destino_id = ?,
                               origem_banco_snapshot = ?, origem_pix_snapshot = ?,
                               destino_banco_snapshot = ?, destino_pix_snapshot = ?,
                               observacao = ?, usuario_ultima_alteracao_id = ?,
                               updated_at = CURRENT_TIMESTAMP
                         WHERE id = ?
                        """,
                        (
                            data_movimento.isoformat(), competencia, valor_centavos,
                            form["conta_origem_id"], form["conta_destino_id"],
                            origem_banco, origem_pix, destino_banco, destino_pix,
                            normalize_optional(form["observacao"]), g.usuario["id"],
                            movimentacao_id,
                        ),
                    )

                    # Corrigir apenas banco/PIX/observação/competência não altera
                    # o principal. Recalcular toda a cadeia só é necessário se
                    # a cronologia ou um valor que reduz saldo foi modificado.
                    precisa_recalcular = (
                        data_movimento.isoformat() != movimento["data_movimento"]
                        or (
                            movimento["tipo"] == "ABATIMENTO"
                            and valor_centavos != int(movimento["valor_centavos"])
                        )
                    )
                    if precisa_recalcular:
                        recalcular_emprestimo_por_movimentacoes(
                            db,
                            int(movimento["emprestimo_id"]),
                        )

                    after_row = db.execute(
                        "SELECT * FROM movimentacoes_emprestimo WHERE id = ?",
                        (movimentacao_id,),
                    ).fetchone()
                    registrar_auditoria(
                        db, "movimentacao_emprestimo", movimentacao_id, "EDITADA",
                        json.dumps(
                            {"motivo": motivo, "antes": before, "depois": movimentacao_para_auditoria(after_row)},
                            ensure_ascii=False, sort_keys=True,
                        ),
                    )
                    db.commit()
                except (sqlite3.DatabaseError, ValueError) as exc:
                    db.rollback()
                    app.logger.exception("Erro ao corrigir movimentação")
                    flash(f"A correção não foi gravada: {exc}", "danger")
                else:
                    flash("Movimentação corrigida com sucesso. A alteração foi registrada na auditoria.", "success")
                    return redirect(url_for("emprestimos_detalhe", emprestimo_id=movimento["emprestimo_id"]))

        return render_template(
            "movimentacoes/editar.html",
            movimento=movimento,
            emprestimo=emprestimo,
            form=form,
            contas_cliente=contas_cliente,
            contas_proprias=contas_proprias,
        )

    @app.route("/movimentacoes/<int:movimentacao_id>/excluir", methods=["GET", "POST"])
    @login_required
    def movimentacoes_excluir(movimentacao_id: int):
        movimento = get_movimentacao_or_404(movimentacao_id)

        if movimento["pagamento_integrado_id"] is not None:
            flash(
                "Esta movimentação faz parte de um pagamento integrado e não pode "
                "ser excluída isoladamente. Exclua o pagamento integrado completo.",
                "warning",
            )
            return redirect(
                url_for(
                    "pagamentos_integrados_detalhe",
                    pagamento_id=movimento["pagamento_integrado_id"],
                )
            )

        if movimento["tipo"] == "EMPRESTIMO":
            flash(
                "A movimentação inicial do empréstimo não pode ser excluída isoladamente. Ela representa a criação do contrato.",
                "warning",
            )
            return redirect(url_for("emprestimos_detalhe", emprestimo_id=movimento["emprestimo_id"]))

        if request.method == "POST":
            senha = request.form.get("senha_confirmacao", "")
            motivo = request.form.get("motivo_exclusao", "").strip()
            errors: list[str] = []

            if not validar_senha_usuario_atual(senha):
                errors.append("A senha de confirmação do usuário logado é inválida.")
            if len(motivo) < 5:
                errors.append("Informe o motivo da exclusão com pelo menos 5 caracteres.")

            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                db = get_db()
                before = movimentacao_para_auditoria(movimento)
                try:
                    if movimento["tipo"] == "JUROS" and movimento["titulo_receber_id"] is not None:
                        titulo_id = int(movimento["titulo_receber_id"])
                        descendants = db.execute(
                            """
                            WITH RECURSIVE arvore(id, movimentacao_id, status, depth) AS (
                                SELECT id, movimentacao_id, status, 1
                                  FROM titulos_receber
                                 WHERE titulo_origem_id = ?
                                UNION ALL
                                SELECT t.id, t.movimentacao_id, t.status, a.depth + 1
                                  FROM titulos_receber t
                                  JOIN arvore a ON t.titulo_origem_id = a.id
                            )
                            SELECT * FROM arvore ORDER BY depth DESC, id DESC
                            """,
                            (titulo_id,),
                        ).fetchall()
                        paid_descendant = next(
                            (
                                row for row in descendants
                                if row["movimentacao_id"] is not None
                                or row["status"] in {"PARCIAL", "RECEBIDO"}
                            ),
                            None,
                        )
                        if paid_descendant is not None:
                            raise ValueError(
                                f"O título #{titulo_id} possui o saldo #{paid_descendant['id']} "
                                "com recebimento posterior. Exclua primeiro a movimentação mais recente da cadeia."
                            )

                        for child in descendants:
                            db.execute(
                                "DELETE FROM titulos_receber WHERE id = ?",
                                (child["id"],),
                            )

                        db.execute(
                            """
                            UPDATE titulos_receber
                               SET status = CASE
                                       WHEN data_vencimento < date('now') THEN 'VENCIDO'
                                       ELSE 'PREVISTO'
                                   END,
                                   valor_recebido_centavos = 0,
                                   movimentacao_id = NULL,
                                   data_recebimento = NULL,
                                   updated_at = CURRENT_TIMESTAMP
                             WHERE id = ?
                            """,
                            (titulo_id,),
                        )

                    db.execute("DELETE FROM movimentacoes_emprestimo WHERE id = ?", (movimentacao_id,))

                    if movimento["tipo"] in {"ABATIMENTO", "QUITACAO"}:
                        saldo = recalcular_emprestimo_por_movimentacoes(
                            db,
                            int(movimento["emprestimo_id"]),
                        )
                    else:
                        saldo_row = db.execute(
                            "SELECT saldo_atual_centavos FROM emprestimos WHERE id = ?",
                            (movimento["emprestimo_id"],),
                        ).fetchone()
                        saldo = int(saldo_row["saldo_atual_centavos"])

                    registrar_auditoria(
                        db, "movimentacao_emprestimo", movimentacao_id, "EXCLUIDA",
                        json.dumps(
                            {"motivo": motivo, "registro_excluido": before, "saldo_apos_recalculo_centavos": saldo},
                            ensure_ascii=False, sort_keys=True,
                        ),
                    )
                    db.commit()
                except (sqlite3.DatabaseError, ValueError) as exc:
                    db.rollback()
                    app.logger.exception("Erro ao excluir movimentação")
                    flash(f"A exclusão não foi gravada: {exc}", "danger")
                else:
                    flash("Movimentação excluída com sucesso. A exclusão foi registrada na auditoria.", "success")
                    return redirect(url_for("emprestimos_detalhe", emprestimo_id=movimento["emprestimo_id"]))

        return render_template("movimentacoes/excluir.html", movimento=movimento)

    @app.get("/movimentacoes")
    @login_required
    def movimentacoes_lista():
        tipo = request.args.get("tipo", "todos").strip().upper()
        termo = request.args.get("q", "").strip()
        data_inicio_text = request.args.get("data_inicio", "").strip()
        data_fim_text = request.args.get("data_fim", "").strip()
        mes = request.args.get("mes", "").strip()  # compatibilidade com links antigos

        tipos_validos = {"EMPRESTIMO", "JUROS", "ABATIMENTO", "QUITACAO"}
        data_inicio = parse_iso_date(data_inicio_text)
        data_fim = parse_iso_date(data_fim_text)

        if data_inicio_text and data_inicio is None:
            flash("Data inicial inválida.", "warning")
        if data_fim_text and data_fim is None:
            flash("Data final inválida.", "warning")

        if data_inicio is not None and data_fim is not None and data_inicio > data_fim:
            flash("A data inicial não pode ser posterior à data final.", "warning")
            data_inicio = None
            data_fim = None

        sql = """
            SELECT m.id, m.tipo, m.data_movimento, m.valor_centavos,
                   m.observacao, m.competencia, m.pagamento_integrado_id,
                   m.titulo_receber_id,
                   m.saldo_antes_centavos, m.saldo_depois_centavos,
                   e.id AS emprestimo_id, c.id AS cliente_id, c.nome AS cliente_nome,
                   u.nome AS usuario_nome,
                   COALESCE(m.origem_banco_snapshot, co.banco) AS origem_banco,
                   COALESCE(m.origem_pix_snapshot, co.chave_pix) AS origem_pix,
                   COALESCE(m.destino_banco_snapshot, cd.banco) AS destino_banco,
                   COALESCE(m.destino_pix_snapshot, cd.chave_pix) AS destino_pix
              FROM movimentacoes_emprestimo m
              JOIN emprestimos e ON e.id = m.emprestimo_id
              JOIN clientes c ON c.id = e.cliente_id
              LEFT JOIN usuarios u ON u.id = m.usuario_id
              LEFT JOIN contas_bancarias co ON co.id = m.conta_origem_id
              LEFT JOIN contas_bancarias cd ON cd.id = m.conta_destino_id
             WHERE 1 = 1
        """
        params: list[Any] = []

        if tipo in tipos_validos:
            sql += " AND m.tipo = ?"
            params.append(tipo)

        if data_inicio is not None:
            sql += " AND m.data_movimento >= ?"
            params.append(data_inicio.isoformat())

        if data_fim is not None:
            sql += " AND m.data_movimento <= ?"
            params.append(data_fim.isoformat())

        if (
            data_inicio is None
            and data_fim is None
            and parse_competencia(mes) is not None
        ):
            sql += " AND substr(m.data_movimento, 1, 7) = ?"
            params.append(mes)

        if termo:
            like = f"%{termo}%"
            sql += """
                AND (
                    c.nome LIKE ? COLLATE NOCASE
                    OR CAST(e.id AS TEXT) LIKE ?
                    OR m.observacao LIKE ? COLLATE NOCASE
                    OR m.origem_banco_snapshot LIKE ? COLLATE NOCASE
                    OR m.destino_banco_snapshot LIKE ? COLLATE NOCASE
                )
            """
            params.extend([like, like, like, like, like])

        sql += " ORDER BY m.data_movimento DESC, m.id DESC LIMIT 500"

        movimentacoes = get_db().execute(sql, params).fetchall()

        return render_template(
            "movimentacoes/lista.html",
            movimentacoes=movimentacoes,
            tipo=tipo.lower(),
            termo=termo,
            data_inicio=data_inicio_text,
            data_fim=data_fim_text,
        )


    # -------------------- Agenda / Títulos a receber --------------------

    @app.get("/receber")
    @login_required
    def titulos_receber_lista():
        db = get_db()
        sync_receivable_titles(db)

        status = request.args.get("status", "abertos").strip().lower()
        periodo_key = request.args.get("periodo", "todos").strip().lower()
        termo = request.args.get("q", "").strip()
        data_inicio_text = request.args.get("data_inicio", "").strip()
        data_fim_text = request.args.get("data_fim", "").strip()
        data_inicio = parse_iso_date(data_inicio_text)
        data_fim = parse_iso_date(data_fim_text)

        if data_inicio_text and data_inicio is None:
            flash("Data inicial inválida.", "warning")
        if data_fim_text and data_fim is None:
            flash("Data final inválida.", "warning")

        if data_inicio is not None and data_fim is not None and data_inicio > data_fim:
            flash("A data inicial não pode ser posterior à data final.", "warning")
            data_inicio = None
            data_fim = None

        periodos = get_receivable_periods()

        sql = """
            SELECT t.id, t.tipo, t.competencia, t.data_vencimento,
                   t.valor_previsto_centavos, t.valor_recebido_centavos,
                   t.saldo_base_centavos, t.taxa_juros_mensal, t.status,
                   t.observacao, t.data_recebimento, t.movimentacao_id,
                   t.titulo_origem_id, t.natureza, t.sequencia,
                   e.id AS emprestimo_id,
                   e.saldo_atual_centavos,
                   c.id AS cliente_id,
                   c.nome AS cliente_nome
              FROM titulos_receber t
              JOIN emprestimos e ON e.id = t.emprestimo_id
              JOIN clientes c ON c.id = e.cliente_id
             WHERE 1 = 1
        """
        params: list[Any] = []

        if status == "abertos":
            sql += " AND t.status IN ('PREVISTO', 'VENCIDO')"
        elif status in {"previsto", "vencido", "parcial", "recebido", "cancelado"}:
            sql += " AND t.status = ?"
            params.append(status.upper())

        # O período manual tem prioridade sobre os atalhos de semana/mês.
        if data_inicio is not None:
            sql += " AND t.data_vencimento >= ?"
            params.append(data_inicio.isoformat())

        if data_fim is not None:
            sql += " AND t.data_vencimento <= ?"
            params.append(data_fim.isoformat())

        if data_inicio is None and data_fim is None and periodo_key in periodos:
            periodo = periodos[periodo_key]
            sql += " AND t.data_vencimento BETWEEN ? AND ?"
            params.extend(
                [
                    periodo["inicio"].isoformat(),
                    periodo["fim"].isoformat(),
                ]
            )

        if termo:
            like = f"%{termo}%"
            sql += """
                AND (
                    c.nome LIKE ? COLLATE NOCASE
                    OR CAST(e.id AS TEXT) LIKE ?
                    OR t.competencia LIKE ?
                    OR t.observacao LIKE ? COLLATE NOCASE
                )
            """
            params.extend([like, like, like, like])

        sql += """
            ORDER BY
                CASE
                    WHEN t.status = 'VENCIDO' THEN 0
                    WHEN t.status = 'PREVISTO' THEN 1
                    WHEN t.status = 'PARCIAL' THEN 2
                    WHEN t.status = 'RECEBIDO' THEN 3
                    ELSE 4
                END,
                t.data_vencimento,
                c.nome COLLATE NOCASE
            LIMIT 500
        """

        titulos = db.execute(sql, params).fetchall()

        for periodo in periodos.values():
            periodo["resumo"] = receivable_period_summary(
                db,
                periodo["inicio"],
                periodo["fim"],
            )

        return render_template(
            "receber/lista.html",
            titulos=titulos,
            status=status,
            periodo_key=periodo_key,
            termo=termo,
            data_inicio=data_inicio_text,
            data_fim=data_fim_text,
            periodos=periodos,
        )

    @app.route("/receber/<int:titulo_id>", methods=["GET", "POST"])
    @login_required
    def titulos_receber_detalhe(titulo_id: int):
        db = get_db()
        sync_receivable_titles(db)
        titulo = get_titulo_receber_or_404(titulo_id)

        contas_cliente = get_client_accounts(titulo["cliente_id"])
        contas_proprias = get_own_accounts()

        form = {
            "data_recebimento": request.form.get(
                "data_recebimento",
                date.today().isoformat(),
            ),
            "valor_recebido": request.form.get(
                "valor_recebido",
                format_money(titulo["valor_previsto_centavos"]).replace("R$ ", ""),
            ),
            "conta_origem_id": (
                parse_int(request.form.get("conta_origem_id"))
                if request.method == "POST"
                else (contas_cliente[0]["id"] if contas_cliente else None)
            ),
            "conta_destino_id": (
                parse_int(request.form.get("conta_destino_id"))
                if request.method == "POST"
                else (contas_proprias[0]["id"] if contas_proprias else None)
            ),
            "observacao": request.form.get("observacao", ""),
        }

        if request.method == "POST":
            if titulo["status"] not in {"PREVISTO", "VENCIDO"}:
                flash("Este título não está mais em aberto.", "warning")
                return redirect(url_for("titulos_receber_detalhe", titulo_id=titulo_id))

            data_recebimento = parse_iso_date(form["data_recebimento"])
            valor_recebido = parse_money_to_centavos(form["valor_recebido"])
            errors: list[str] = []

            if data_recebimento is None:
                errors.append("Informe uma data válida para o recebimento.")
            elif data_recebimento < date.fromisoformat(titulo["data_emprestimo"]):
                errors.append("A data do recebimento não pode ser anterior ao empréstimo.")

            valor_documento = int(titulo["valor_previsto_centavos"])
            if valor_recebido is None or valor_recebido <= 0:
                errors.append("Informe o valor efetivamente recebido.")
            elif valor_recebido > valor_documento:
                errors.append(
                    f"O valor recebido não pode superar o saldo do documento "
                    f"({format_money(valor_documento)})."
                )

            errors.extend(
                validate_money_flow_accounts(
                    titulo["cliente_id"],
                    form["conta_origem_id"],
                    form["conta_destino_id"],
                    is_loan_disbursement=False,
                )
            )

            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                origem_banco, origem_pix, destino_banco, destino_pix = get_account_snapshots(
                    form["conta_origem_id"],
                    form["conta_destino_id"],
                )

                try:
                    parcial = int(valor_recebido) < valor_documento
                    observacao_mov = normalize_optional(form["observacao"])
                    if parcial:
                        base = "RECEBIMENTO PARCIAL DE JUROS"
                        observacao_mov = (
                            f"{base} — {observacao_mov}" if observacao_mov else base
                        )

                    cursor = db.execute(
                        """
                        INSERT INTO movimentacoes_emprestimo (
                            emprestimo_id, tipo, data_movimento, valor_centavos,
                            observacao, competencia, usuario_id,
                            saldo_antes_centavos, saldo_depois_centavos,
                            conta_origem_id, conta_destino_id,
                            origem_banco_snapshot, origem_pix_snapshot,
                            destino_banco_snapshot, destino_pix_snapshot,
                            titulo_receber_id
                        ) VALUES (?, 'JUROS', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            titulo["emprestimo_id"],
                            data_recebimento.isoformat(),
                            valor_recebido,
                            observacao_mov,
                            titulo["competencia"],
                            g.usuario["id"],
                            titulo["saldo_base_centavos"],
                            titulo["saldo_base_centavos"],
                            form["conta_origem_id"],
                            form["conta_destino_id"],
                            origem_banco,
                            origem_pix,
                            destino_banco,
                            destino_pix,
                            titulo_id,
                        ),
                    )
                    movement_id = int(cursor.lastrowid)

                    saldo_id = aplicar_recebimento_titulo(
                        db,
                        titulo_id=titulo_id,
                        valor_recebido_centavos=int(valor_recebido),
                        movimentacao_id=movement_id,
                        data_recebimento=data_recebimento,
                        observacao=observacao_mov,
                    )

                    registrar_auditoria(
                        db,
                        "titulo_receber",
                        titulo_id,
                        "RECEBIMENTO_PARCIAL" if saldo_id else "RECEBIDO",
                        json.dumps(
                            {
                                "valor_recebido_centavos": int(valor_recebido),
                                "movimentacao_id": movement_id,
                                "titulo_saldo_id": saldo_id,
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    )
                    db.commit()
                except (sqlite3.DatabaseError, ValueError) as exc:
                    db.rollback()
                    app.logger.exception("Erro ao confirmar título a receber")
                    flash(f"O recebimento não foi gravado: {exc}", "danger")
                else:
                    if saldo_id:
                        flash(
                            f"Recebimento parcial de {format_money(valor_recebido)} registrado. "
                            f"O saldo restante foi gerado no título #{saldo_id}.",
                            "success",
                        )
                        return redirect(url_for("titulos_receber_detalhe", titulo_id=saldo_id))

                    flash(
                        f"Recebimento de {format_money(valor_recebido)} confirmado.",
                        "success",
                    )
                    return redirect(url_for("titulos_receber_detalhe", titulo_id=titulo_id))

        titulo = get_titulo_receber_or_404(titulo_id)
        titulo_origem = None
        if titulo["titulo_origem_id"] is not None:
            titulo_origem = db.execute(
                "SELECT id, status, valor_previsto_centavos FROM titulos_receber WHERE id = ?",
                (titulo["titulo_origem_id"],),
            ).fetchone()

        titulos_saldo = db.execute(
            """
            SELECT id, status, valor_previsto_centavos, valor_recebido_centavos,
                   data_vencimento, sequencia
              FROM titulos_receber
             WHERE titulo_origem_id = ?
             ORDER BY sequencia, id
            """,
            (titulo_id,),
        ).fetchall()

        return render_template(
            "receber/detalhe.html",
            titulo=titulo,
            titulo_origem=titulo_origem,
            titulos_saldo=titulos_saldo,
            contas_cliente=contas_cliente,
            contas_proprias=contas_proprias,
            form=form,
        )


    @app.route("/receber/<int:titulo_id>/editar", methods=["GET", "POST"])
    @login_required
    def titulos_receber_editar(titulo_id: int):
        db = get_db()
        sync_receivable_titles(db)
        titulo = get_titulo_receber_or_404(titulo_id)

        if titulo["status"] not in {"PREVISTO", "VENCIDO"}:
            flash(
                "Somente títulos em aberto podem ser alterados.",
                "warning",
            )
            return redirect(
                url_for("titulos_receber_detalhe", titulo_id=titulo_id)
            )

        form = {
            "competencia": request.form.get(
                "competencia",
                titulo["competencia"],
            ),
            "data_vencimento": request.form.get(
                "data_vencimento",
                titulo["data_vencimento"],
            ),
            "valor_previsto": request.form.get(
                "valor_previsto",
                format_money(
                    titulo["valor_previsto_centavos"]
                ).replace("R$ ", ""),
            ),
            "observacao": request.form.get(
                "observacao",
                titulo["observacao"] or "",
            ),
            "motivo_alteracao": request.form.get(
                "motivo_alteracao",
                "",
            ),
        }

        if request.method == "POST":
            errors: list[str] = []
            competencia = parse_competencia(form["competencia"])
            data_vencimento = parse_iso_date(form["data_vencimento"])
            valor_previsto = parse_money_to_centavos(form["valor_previsto"])
            motivo = form["motivo_alteracao"].strip()
            senha = request.form.get("senha_confirmacao", "")

            if not validar_senha_usuario_atual(senha):
                errors.append(
                    "A senha de confirmação do usuário logado é inválida."
                )

            if len(motivo) < 5:
                errors.append(
                    "Informe o motivo da alteração com pelo menos 5 caracteres."
                )

            if competencia is None:
                errors.append("Informe uma competência válida.")

            if data_vencimento is None:
                errors.append("Informe uma data de vencimento válida.")

            if titulo["natureza"] == "SALDO_JUROS":
                if competencia is not None and competencia != titulo["competencia"]:
                    errors.append(
                        "Um saldo de juros deve manter a mesma competência do documento de origem."
                    )
                if (
                    data_vencimento is not None
                    and data_vencimento.isoformat() != titulo["data_vencimento"]
                ):
                    errors.append(
                        "Um saldo de juros deve manter o mesmo vencimento do documento de origem."
                    )

            if valor_previsto is None or valor_previsto <= 0:
                errors.append("Informe um valor previsto válido.")

            if (
                data_vencimento is not None
                and data_vencimento
                < date.fromisoformat(titulo["data_emprestimo"])
            ):
                errors.append(
                    "O vencimento não pode ser anterior à data do empréstimo."
                )

            if (
                competencia is not None
                and competencia < titulo["data_emprestimo"][:7]
            ):
                errors.append(
                    "A competência não pode ser anterior ao empréstimo."
                )

            if competencia is not None:
                conflito_titulo = db.execute(
                    """
                    SELECT id
                      FROM titulos_receber
                     WHERE emprestimo_id = ?
                       AND tipo = 'JUROS'
                       AND competencia = ?
                       AND id <> ?
                       AND status IN ('PREVISTO', 'VENCIDO')
                     LIMIT 1
                    """,
                    (
                        titulo["emprestimo_id"],
                        competencia,
                        titulo_id,
                    ),
                ).fetchone()

                if conflito_titulo is not None:
                    errors.append(
                        f"Já existe o título #{conflito_titulo['id']} para "
                        f"{format_competencia_br(competencia)}."
                    )

                if competencia != titulo["competencia"]:
                    conflito_movimento = db.execute(
                        """
                        SELECT id
                          FROM movimentacoes_emprestimo
                         WHERE emprestimo_id = ?
                           AND tipo = 'JUROS'
                           AND competencia = ?
                         LIMIT 1
                        """,
                        (titulo["emprestimo_id"], competencia),
                    ).fetchone()

                    if conflito_movimento is not None:
                        errors.append(
                            f"Já existe uma movimentação de juros para "
                            f"{format_competencia_br(competencia)}."
                        )

            saldo_base = None
            juros_esperado = None
            if data_vencimento is not None:
                try:
                    if data_vencimento <= date.today():
                        saldo_base = saldo_principal_antes_da_data(
                            db,
                            int(titulo["emprestimo_id"]),
                            data_vencimento,
                        )
                    else:
                        saldo_base = int(titulo["saldo_atual_centavos"])
                except ValueError as exc:
                    errors.append(str(exc))

                if saldo_base is not None and saldo_base > 0:
                    juros_esperado = calcular_juros_centavos(
                        saldo_base,
                        titulo["taxa_atual"],
                    )

                    if (
                        titulo["natureza"] != "SALDO_JUROS"
                        and valor_previsto is not None
                        and valor_previsto != juros_esperado
                    ):
                        errors.append(
                            "O juro continua sendo integral. Para o saldo-base "
                            f"de {format_money(saldo_base)} e taxa de "
                            f"{format_percent_br(titulo['taxa_atual'])}, o valor "
                            f"correto é {format_money(juros_esperado)}."
                        )

            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                before = titulo_receber_para_auditoria(titulo)
                novo_status = (
                    "VENCIDO"
                    if data_vencimento < date.today()
                    else "PREVISTO"
                )

                try:
                    db.execute(
                        """
                        UPDATE titulos_receber
                           SET competencia = ?,
                               data_vencimento = ?,
                               valor_previsto_centavos = ?,
                               saldo_base_centavos = ?,
                               taxa_juros_mensal = ?,
                               status = ?,
                               observacao = ?,
                               ajuste_manual = 1,
                               updated_at = CURRENT_TIMESTAMP
                         WHERE id = ?
                           AND status IN ('PREVISTO', 'VENCIDO')
                        """,
                        (
                            competencia,
                            data_vencimento.isoformat(),
                            valor_previsto,
                            (titulo["saldo_base_centavos"] if titulo["natureza"] == "SALDO_JUROS" else saldo_base),
                            titulo["taxa_juros_mensal"],
                            novo_status,
                            normalize_optional(form["observacao"]),
                            titulo_id,
                        ),
                    )

                    if competencia != titulo["competencia"]:
                        # Preserva um cancelamento da competência antiga para
                        # que a sincronização automática não recrie o título
                        # que acabou de ser corrigido.
                        db.execute(
                            """
                            INSERT INTO titulos_receber (
                                emprestimo_id, tipo, competencia,
                                data_vencimento, valor_previsto_centavos,
                                valor_recebido_centavos,
                                saldo_base_centavos, taxa_juros_mensal,
                                status, observacao, ajuste_manual,
                                natureza, sequencia
                            )
                            SELECT ?, 'JUROS', ?, ?, ?, 0, ?, ?, 'CANCELADO', ?, 1, 'JUROS', 1
                             WHERE NOT EXISTS (
                                 SELECT 1
                                   FROM titulos_receber
                                  WHERE emprestimo_id = ?
                                    AND tipo = 'JUROS'
                                    AND competencia = ?
                                    AND status = 'CANCELADO'
                             )
                            """,
                            (
                                titulo["emprestimo_id"],
                                titulo["competencia"],
                                titulo["data_vencimento"],
                                titulo["valor_previsto_centavos"],
                                titulo["saldo_base_centavos"],
                                titulo["taxa_juros_mensal"],
                                (
                                    f"Competência substituída pelo título #{titulo_id} "
                                    f"em {format_competencia_br(competencia)}."
                                ),
                                titulo["emprestimo_id"],
                                titulo["competencia"],
                            ),
                        )

                    atualizado = db.execute(
                        "SELECT * FROM titulos_receber WHERE id = ?",
                        (titulo_id,),
                    ).fetchone()

                    registrar_auditoria(
                        db,
                        "titulo_receber",
                        titulo_id,
                        "ALTERADO",
                        json.dumps(
                            {
                                "motivo": motivo,
                                "antes": before,
                                "depois": titulo_receber_para_auditoria(
                                    atualizado
                                ),
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    )
                    db.commit()

                except sqlite3.DatabaseError as exc:
                    db.rollback()
                    app.logger.exception(
                        "Erro ao alterar título a receber"
                    )
                    flash(
                        f"A alteração não foi gravada: {exc}",
                        "danger",
                    )
                else:
                    flash(
                        "Título em aberto alterado com sucesso.",
                        "success",
                    )
                    return redirect(
                        url_for(
                            "titulos_receber_detalhe",
                            titulo_id=titulo_id,
                        )
                    )

        return render_template(
            "receber/editar.html",
            titulo=titulo,
            form=form,
        )

    @app.route("/receber/<int:titulo_id>/excluir", methods=["GET", "POST"])
    @login_required
    def titulos_receber_excluir(titulo_id: int):
        db = get_db()
        sync_receivable_titles(db)
        titulo = get_titulo_receber_or_404(titulo_id)

        if titulo["status"] not in {"PREVISTO", "VENCIDO"}:
            flash(
                "Somente títulos em aberto podem ser excluídos.",
                "warning",
            )
            return redirect(
                url_for("titulos_receber_detalhe", titulo_id=titulo_id)
            )

        if request.method == "POST":
            senha = request.form.get("senha_confirmacao", "")
            motivo = request.form.get("motivo_exclusao", "").strip()
            errors: list[str] = []

            if not validar_senha_usuario_atual(senha):
                errors.append(
                    "A senha de confirmação do usuário logado é inválida."
                )

            if len(motivo) < 5:
                errors.append(
                    "Informe o motivo da exclusão com pelo menos 5 caracteres."
                )

            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                before = titulo_receber_para_auditoria(titulo)

                try:
                    # Mantemos o registro como CANCELADO em vez de apagá-lo
                    # fisicamente. Assim a sincronização automática não recria
                    # a mesma previsão e a auditoria permanece rastreável.
                    db.execute(
                        """
                        UPDATE titulos_receber
                           SET status = 'CANCELADO',
                               updated_at = CURRENT_TIMESTAMP
                         WHERE id = ?
                           AND status IN ('PREVISTO', 'VENCIDO')
                        """,
                        (titulo_id,),
                    )

                    registrar_auditoria(
                        db,
                        "titulo_receber",
                        titulo_id,
                        "EXCLUIDO",
                        json.dumps(
                            {
                                "motivo": motivo,
                                "registro": before,
                                "resultado": "CANCELADO",
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    )
                    db.commit()

                except sqlite3.DatabaseError as exc:
                    db.rollback()
                    app.logger.exception(
                        "Erro ao excluir título a receber"
                    )
                    flash(
                        f"A exclusão não foi gravada: {exc}",
                        "danger",
                    )
                else:
                    flash(
                        "Título removido dos recebimentos em aberto. "
                        "O histórico da exclusão foi preservado.",
                        "success",
                    )
                    return redirect(
                        url_for(
                            "titulos_receber_lista",
                            status="abertos",
                        )
                    )

        return render_template(
            "receber/excluir.html",
            titulo=titulo,
        )


    # -------------------- Cartões de crédito --------------------

    @app.get("/cartoes")
    @login_required
    def cartoes_lista():
        db = get_db()
        refresh_overdue_card_installments(db)
        termo = request.args.get("q", "").strip()
        status = request.args.get("status", "ativos").strip().lower()

        sql = """
            SELECT cc.id, cc.descricao, cc.ativo, cc.created_at,
                   c.id AS cliente_id, c.nome AS cliente_nome,
                   COALESCE(SUM(pc.valor_centavos), 0) AS total_parcelado_centavos,
                   COALESCE(SUM(CASE WHEN pc.status = 'PAGO' THEN pc.valor_centavos ELSE 0 END), 0) AS pago_centavos,
                   COALESCE(SUM(CASE WHEN pc.status IN ('PENDENTE','VENCIDO') THEN pc.valor_centavos ELSE 0 END), 0) AS aberto_centavos
              FROM cartoes_credito cc
              JOIN clientes c ON c.id = cc.cliente_id
              LEFT JOIN lancamentos_cartao lc ON lc.cartao_credito_id = cc.id
              LEFT JOIN parcelas_cartao pc ON pc.lancamento_cartao_id = lc.id
             WHERE 1 = 1
        """
        params: list[Any] = []
        if status == "ativos":
            sql += " AND cc.ativo = 1"
        elif status == "inativos":
            sql += " AND cc.ativo = 0"
        if termo:
            like = f"%{termo}%"
            sql += " AND (c.nome LIKE ? COLLATE NOCASE OR cc.descricao LIKE ? COLLATE NOCASE)"
            params.extend([like, like])
        sql += " GROUP BY cc.id, c.id ORDER BY cc.ativo DESC, c.nome COLLATE NOCASE, cc.id DESC"
        cartoes = db.execute(sql, params).fetchall()
        return render_template("cartoes/lista.html", cartoes=cartoes, termo=termo, status=status)

    @app.route("/cartoes/novo", methods=["GET", "POST"])
    @login_required
    def cartoes_novo():
        db = get_db()
        clientes = db.execute(
            "SELECT id, nome FROM clientes WHERE ativo = 1 ORDER BY nome COLLATE NOCASE"
        ).fetchall()
        if not clientes:
            flash("Cadastre um cliente ativo antes de criar um cartão.", "warning")
            return redirect(url_for("clientes_novo"))

        form = {
            "cliente_id": request.form.get("cliente_id", request.args.get("cliente_id", "")),
            "descricao": request.form.get("descricao", ""),
        }
        if request.method == "POST":
            cliente_id = parse_int(form["cliente_id"])
            descricao = form["descricao"].strip()
            errors: list[str] = []
            cliente = db.execute("SELECT id, ativo FROM clientes WHERE id = ?", (cliente_id,)).fetchone()
            if cliente is None or not cliente["ativo"]:
                errors.append("Selecione um cliente ativo.")
            if len(descricao) < 2:
                errors.append("Informe uma descrição para o cartão.")

            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                try:
                    cursor = db.execute(
                        "INSERT INTO cartoes_credito (cliente_id, descricao, ativo) VALUES (?, ?, 1)",
                        (cliente_id, descricao),
                    )
                    registrar_auditoria(db, "cartao_credito", int(cursor.lastrowid), "CRIADO", descricao)
                    db.commit()
                except sqlite3.DatabaseError:
                    db.rollback()
                    app.logger.exception("Erro ao criar cartão")
                    flash("Não foi possível cadastrar o cartão.", "danger")
                else:
                    flash("Cartão cadastrado.", "success")
                    return redirect(url_for("cartoes_detalhe", cartao_id=cursor.lastrowid))

        return render_template("cartoes/form.html", form=form, clientes=clientes)

    @app.get("/cartoes/<int:cartao_id>")
    @login_required
    def cartoes_detalhe(cartao_id: int):
        db = get_db()
        refresh_overdue_card_installments(db)
        cartao = db.execute(
            """
            SELECT cc.*, c.nome AS cliente_nome, c.id AS cliente_id
              FROM cartoes_credito cc
              JOIN clientes c ON c.id = cc.cliente_id
             WHERE cc.id = ?
            """,
            (cartao_id,),
        ).fetchone()
        if cartao is None:
            abort(404)

        lancamentos = db.execute(
            """
            SELECT lc.id, lc.descricao, lc.valor_total_centavos, lc.quantidade_parcelas,
                   lc.data_compra, u.nome AS usuario_nome
              FROM lancamentos_cartao lc
              LEFT JOIN usuarios u ON u.id = lc.usuario_id
             WHERE lc.cartao_credito_id = ?
             ORDER BY lc.data_compra DESC, lc.id DESC
            """,
            (cartao_id,),
        ).fetchall()
        parcelas = db.execute(
            """
            SELECT pc.*, lc.descricao AS lancamento_descricao,
                   COALESCE(pc.origem_banco_snapshot, co.banco) AS origem_banco, COALESCE(pc.origem_pix_snapshot, co.chave_pix) AS origem_pix,
                   COALESCE(pc.destino_banco_snapshot, cd.banco) AS destino_banco, COALESCE(pc.destino_pix_snapshot, cd.chave_pix) AS destino_pix,
                   u.nome AS usuario_pagamento_nome
              FROM parcelas_cartao pc
              JOIN lancamentos_cartao lc ON lc.id = pc.lancamento_cartao_id
              LEFT JOIN contas_bancarias co ON co.id = pc.conta_origem_id
              LEFT JOIN contas_bancarias cd ON cd.id = pc.conta_destino_id
              LEFT JOIN usuarios u ON u.id = pc.usuario_pagamento_id
             WHERE lc.cartao_credito_id = ?
             ORDER BY pc.vencimento, pc.id
            """,
            (cartao_id,),
        ).fetchall()
        resumo = db.execute(
            """
            SELECT COALESCE(SUM(pc.valor_centavos), 0) AS total_centavos,
                   COALESCE(SUM(CASE WHEN pc.status = 'PAGO' THEN pc.valor_centavos ELSE 0 END), 0) AS pago_centavos,
                   COALESCE(SUM(CASE WHEN pc.status IN ('PENDENTE','VENCIDO') THEN pc.valor_centavos ELSE 0 END), 0) AS aberto_centavos,
                   COALESCE(SUM(CASE WHEN pc.status = 'VENCIDO' THEN pc.valor_centavos ELSE 0 END), 0) AS vencido_centavos
              FROM parcelas_cartao pc
              JOIN lancamentos_cartao lc ON lc.id = pc.lancamento_cartao_id
             WHERE lc.cartao_credito_id = ?
            """,
            (cartao_id,),
        ).fetchone()
        return render_template(
            "cartoes/detalhe.html", cartao=cartao, lancamentos=lancamentos,
            parcelas=parcelas, resumo=resumo,
        )

    @app.post("/cartoes/<int:cartao_id>/status")
    @login_required
    def cartoes_status(cartao_id: int):
        db = get_db()
        cartao = db.execute("SELECT id, ativo FROM cartoes_credito WHERE id = ?", (cartao_id,)).fetchone()
        if cartao is None:
            abort(404)
        novo_status = 0 if cartao["ativo"] else 1
        db.execute("UPDATE cartoes_credito SET ativo = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (novo_status, cartao_id))
        registrar_auditoria(db, "cartao_credito", cartao_id, "ATIVADO" if novo_status else "INATIVADO")
        db.commit()
        flash("Cartão ativado." if novo_status else "Cartão inativado.", "success")
        return redirect(url_for("cartoes_detalhe", cartao_id=cartao_id))

    @app.route("/cartoes/<int:cartao_id>/lancamentos/novo", methods=["GET", "POST"])
    @login_required
    def cartoes_lancamento_novo(cartao_id: int):
        db = get_db()
        cartao = db.execute(
            """
            SELECT cc.*, c.nome AS cliente_nome
              FROM cartoes_credito cc
              JOIN clientes c ON c.id = cc.cliente_id
             WHERE cc.id = ?
            """, (cartao_id,)
        ).fetchone()
        if cartao is None:
            abort(404)
        if not cartao["ativo"]:
            flash("Ative o cartão antes de criar novos lançamentos.", "warning")
            return redirect(url_for("cartoes_detalhe", cartao_id=cartao_id))

        form = {
            "descricao": request.form.get("descricao", ""),
            "valor_total": request.form.get("valor_total", ""),
            "quantidade_parcelas": request.form.get("quantidade_parcelas", "1"),
            "data_compra": request.form.get("data_compra", date.today().isoformat()),
            "primeiro_vencimento": request.form.get("primeiro_vencimento", ""),
        }
        if request.method == "POST":
            descricao = form["descricao"].strip()
            valor_centavos = parse_money_to_centavos(form["valor_total"])
            quantidade = parse_int(form["quantidade_parcelas"])
            data_compra = parse_iso_date(form["data_compra"])
            primeiro_vencimento = parse_iso_date(form["primeiro_vencimento"])
            errors: list[str] = []
            if len(descricao) < 2:
                errors.append("Informe a descrição da compra.")
            if valor_centavos is None or valor_centavos <= 0:
                errors.append("Informe um valor total maior que zero.")
            if quantidade is None or quantidade < 1 or quantidade > 120:
                errors.append("A quantidade de parcelas deve estar entre 1 e 120.")
            if data_compra is None:
                errors.append("Informe uma data de compra válida.")
            if primeiro_vencimento is None:
                errors.append("Informe o primeiro vencimento.")
            elif data_compra is not None and primeiro_vencimento < data_compra:
                errors.append("O primeiro vencimento não pode ser anterior à compra.")

            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                assert valor_centavos is not None and quantidade is not None and data_compra and primeiro_vencimento
                try:
                    cursor = db.execute(
                        """
                        INSERT INTO lancamentos_cartao (
                            cartao_credito_id, descricao, valor_total_centavos,
                            quantidade_parcelas, data_compra, usuario_id
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (cartao_id, descricao, valor_centavos, quantidade, data_compra.isoformat(), g.usuario["id"]),
                    )
                    lancamento_id = int(cursor.lastrowid)
                    valores = split_centavos(valor_centavos, quantidade)
                    for index, valor_parcela in enumerate(valores):
                        vencimento = add_months_iso(primeiro_vencimento, index)
                        status_inicial = "VENCIDO" if vencimento < date.today() else "PENDENTE"
                        db.execute(
                            """
                            INSERT INTO parcelas_cartao (
                                lancamento_cartao_id, numero_parcela, valor_centavos, vencimento, status
                            ) VALUES (?, ?, ?, ?, ?)
                            """,
                            (lancamento_id, index + 1, valor_parcela, vencimento.isoformat(), status_inicial),
                        )
                    registrar_auditoria(db, "lancamento_cartao", lancamento_id, "CRIADO", f"{quantidade} parcela(s), {valor_centavos} centavos.")
                    db.commit()
                except sqlite3.DatabaseError:
                    db.rollback()
                    app.logger.exception("Erro ao criar lançamento do cartão")
                    flash("Não foi possível criar o lançamento e suas parcelas.", "danger")
                else:
                    flash("Lançamento e parcelas criados com sucesso.", "success")
                    return redirect(url_for("cartoes_detalhe", cartao_id=cartao_id))

        return render_template("cartoes/lancamento_form.html", cartao=cartao, form=form)

    @app.route("/parcelas-cartao/<int:parcela_id>/pagar", methods=["GET", "POST"])
    @login_required
    def parcelas_cartao_pagar(parcela_id: int):
        db = get_db()
        refresh_overdue_card_installments(db)
        parcela = db.execute(
            """
            SELECT pc.*, lc.descricao AS lancamento_descricao, lc.data_compra,
                   cc.id AS cartao_id, cc.cliente_id, cc.descricao AS cartao_descricao,
                   c.nome AS cliente_nome
              FROM parcelas_cartao pc
              JOIN lancamentos_cartao lc ON lc.id = pc.lancamento_cartao_id
              JOIN cartoes_credito cc ON cc.id = lc.cartao_credito_id
              JOIN clientes c ON c.id = cc.cliente_id
             WHERE pc.id = ?
            """, (parcela_id,)
        ).fetchone()
        if parcela is None:
            abort(404)
        if parcela["status"] == "PAGO":
            flash("Esta parcela já foi paga.", "warning")
            return redirect(url_for("cartoes_detalhe", cartao_id=parcela["cartao_id"]))
        if parcela["status"] == "CANCELADO":
            flash("Esta parcela está cancelada.", "warning")
            return redirect(url_for("cartoes_detalhe", cartao_id=parcela["cartao_id"]))

        contas_cliente = get_client_accounts(parcela["cliente_id"])
        contas_proprias = get_own_accounts()
        form = {
            "data_pagamento": request.form.get("data_pagamento", date.today().isoformat()),
            "conta_origem_id": parse_int(request.form.get("conta_origem_id")) if request.method == "POST" else (contas_cliente[0]["id"] if contas_cliente else None),
            "conta_destino_id": parse_int(request.form.get("conta_destino_id")) if request.method == "POST" else (contas_proprias[0]["id"] if contas_proprias else None),
            "observacao": request.form.get("observacao", ""),
        }
        if request.method == "POST":
            data_pagamento = parse_iso_date(form["data_pagamento"])
            errors: list[str] = []
            if data_pagamento is None:
                errors.append("Informe uma data de pagamento válida.")
            elif data_pagamento < date.fromisoformat(parcela["data_compra"]):
                errors.append("O pagamento não pode ser anterior à compra.")
            errors.extend(validate_money_flow_accounts(
                parcela["cliente_id"], form["conta_origem_id"], form["conta_destino_id"],
                is_loan_disbursement=False,
            ))
            if errors:
                for error in errors:
                    flash(error, "danger")
            else:
                origem_banco, origem_pix, destino_banco, destino_pix = get_account_snapshots(
                    form["conta_origem_id"], form["conta_destino_id"]
                )
                try:
                    db.execute(
                        """
                        UPDATE parcelas_cartao
                           SET status = 'PAGO', data_pagamento = ?, conta_origem_id = ?,
                               conta_destino_id = ?, origem_banco_snapshot = ?, origem_pix_snapshot = ?,
                               destino_banco_snapshot = ?, destino_pix_snapshot = ?,
                               usuario_pagamento_id = ?, pagamento_observacao = ?
                         WHERE id = ? AND status IN ('PENDENTE','VENCIDO')
                        """,
                        (
                            data_pagamento.isoformat(), form["conta_origem_id"], form["conta_destino_id"],
                            origem_banco, origem_pix, destino_banco, destino_pix,
                            g.usuario["id"], normalize_optional(form["observacao"]), parcela_id,
                        ),
                    )
                    registrar_auditoria(db, "parcela_cartao", parcela_id, "PAGA", f"Valor {parcela['valor_centavos']} centavos.")
                    db.commit()
                except sqlite3.DatabaseError:
                    db.rollback()
                    app.logger.exception("Erro ao registrar pagamento da parcela")
                    flash("Não foi possível registrar o pagamento.", "danger")
                else:
                    flash(f"Pagamento de {format_money(parcela['valor_centavos'])} registrado.", "success")
                    return redirect(url_for("cartoes_detalhe", cartao_id=parcela["cartao_id"]))

        return render_template(
            "cartoes/pagamento.html", parcela=parcela, form=form,
            contas_cliente=contas_cliente, contas_proprias=contas_proprias,
        )


def cliente_form_data() -> dict[str, Any]:
    cpf = only_digits(request.form.get("cpf"))
    telefone = only_digits(request.form.get("telefone"))
    cep = only_digits(request.form.get("cep"))

    return {
        "nome": request.form.get("nome", "").strip(),
        "telefone": telefone or None,
        "email": normalize_optional(request.form.get("email")),
        "cpf": cpf or None,
        "endereco": normalize_optional(request.form.get("endereco")),
        "cidade": normalize_optional(request.form.get("cidade")),
        "estado": (request.form.get("estado", "").strip().upper() or None),
        "cep": cep or None,
        "observacoes": normalize_optional(request.form.get("observacoes")),
    }


def validate_cliente(form: dict[str, Any], cliente_id: int | None = None) -> list[str]:
    errors: list[str] = []

    if len(form["nome"]) < 3:
        errors.append("O nome do cliente deve ter pelo menos 3 caracteres.")

    cpf = form["cpf"] or ""
    if not validate_cpf(cpf):
        errors.append("Informe um CPF válido.")

    estado = form["estado"] or ""
    if estado and len(estado) != 2:
        errors.append("O estado deve ser informado com 2 letras, por exemplo CE.")

    cep = form["cep"] or ""
    if cep and len(cep) != 8:
        errors.append("O CEP deve possuir 8 dígitos.")

    email = form["email"] or ""
    if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        errors.append("Informe um e-mail válido.")

    if cpf:
        db = get_db()
        if cliente_id is None:
            existing = db.execute(
                "SELECT id FROM clientes WHERE cpf = ? LIMIT 1",
                (cpf,),
            ).fetchone()
        else:
            existing = db.execute(
                "SELECT id FROM clientes WHERE cpf = ? AND id <> ? LIMIT 1",
                (cpf, cliente_id),
            ).fetchone()

        if existing is not None:
            errors.append("Já existe outro cliente cadastrado com este CPF.")

    return errors


def emprestimo_form_data() -> dict[str, Any]:
    cliente_id_raw = request.form.get("cliente_id", "").strip()
    valor_raw = request.form.get("valor_original", "").strip()
    taxa_raw = request.form.get("taxa_juros_mensal", "").strip()

    try:
        cliente_id = int(cliente_id_raw)
    except (TypeError, ValueError):
        cliente_id = None

    valor_centavos = parse_money_to_centavos(valor_raw)
    taxa = parse_percent(taxa_raw)

    return {
        "cliente_id": cliente_id,
        "descricao": normalize_optional(request.form.get("descricao")),
        "data_emprestimo": request.form.get("data_emprestimo", "").strip(),
        "valor_original": valor_raw,
        "valor_original_centavos": valor_centavos,
        "taxa_juros_mensal_input": taxa_raw,
        "taxa_juros_mensal": taxa,
        "data_primeiro_vencimento": request.form.get("data_primeiro_vencimento", "").strip(),
        "conta_origem_id": parse_int(request.form.get("conta_origem_id")),
        "conta_destino_id": parse_int(request.form.get("conta_destino_id")),
    }


def validate_emprestimo(form: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if form["cliente_id"] is None:
        errors.append("Selecione o cliente do empréstimo.")

    if form.get("conta_origem_id") is None:
        errors.append("Selecione a conta própria de onde o valor saiu.")
    if form.get("conta_destino_id") is None:
        errors.append("Selecione a conta do cliente que recebeu o empréstimo.")

    data_emprestimo = parse_iso_date(form["data_emprestimo"])
    if data_emprestimo is None:
        errors.append("Informe uma data de empréstimo válida.")

    valor_centavos = form["valor_original_centavos"]
    if valor_centavos is None:
        errors.append("Informe um valor de empréstimo válido.")
    elif valor_centavos <= 0:
        errors.append("O valor do empréstimo deve ser maior que zero.")

    taxa = form["taxa_juros_mensal"]
    if taxa is None:
        errors.append("Informe uma taxa de juros mensal válida.")
    elif taxa < 0:
        errors.append("A taxa de juros não pode ser negativa.")

    primeiro_vencimento = parse_iso_date(form["data_primeiro_vencimento"])
    if primeiro_vencimento is None:
        errors.append("Informe a data do primeiro vencimento.")
    elif data_emprestimo is not None and primeiro_vencimento < data_emprestimo:
        errors.append("O primeiro vencimento não pode ser anterior à data do empréstimo.")

    return errors


def iter_months(start_date: date, end_date: date) -> list[str]:
    """Retorna competências YYYY-MM inclusivas entre duas datas."""
    if start_date > end_date:
        return []

    current = first_day_of_month(start_date)
    last = first_day_of_month(end_date)
    result: list[str] = []

    while current <= last:
        result.append(current.strftime("%Y-%m"))
        current = add_months_iso(current, 1)

    return result


def primeiro_vencimento_emprestimo(emprestimo: sqlite3.Row) -> date:
    """Resolve o primeiro vencimento do contrato com a mesma regra da agenda."""
    data_emprestimo = date.fromisoformat(emprestimo["data_emprestimo"])

    if emprestimo["data_primeiro_vencimento"]:
        return date.fromisoformat(emprestimo["data_primeiro_vencimento"])

    base_due = add_months_iso(data_emprestimo, 1)
    due_day = int(emprestimo["dia_vencimento"] or base_due.day)

    return base_due.replace(
        day=min(due_day, monthrange(base_due.year, base_due.month)[1])
    )


def resumo_financeiro_cliente(
    db: sqlite3.Connection,
    cliente_id: int,
) -> dict[str, int]:
    """
    Posição atual do cliente.

    - total_historico_emprestado: soma dos contratos já concedidos;
    - principal_em_aberto: capital ainda emprestado hoje;
    - juros_em_aberto: documentos PREVISTO/VENCIDO ainda pendentes;
    - total_a_receber: principal + juros em aberto.
    """
    emprestimos = db.execute(
        """
        SELECT
            COUNT(*) AS quantidade_emprestimos,
            COALESCE(SUM(valor_original_centavos), 0) AS total_historico_emprestado_centavos,
            COALESCE(SUM(
                CASE
                    WHEN status <> 'QUITADO'
                    THEN saldo_atual_centavos
                    ELSE 0
                END
            ), 0) AS principal_em_aberto_centavos
          FROM emprestimos
         WHERE cliente_id = ?
        """,
        (cliente_id,),
    ).fetchone()

    juros = db.execute(
        """
        SELECT COALESCE(SUM(t.valor_previsto_centavos), 0) AS juros_em_aberto_centavos
          FROM titulos_receber t
          JOIN emprestimos e ON e.id = t.emprestimo_id
         WHERE e.cliente_id = ?
           AND t.status IN ('PREVISTO', 'VENCIDO')
        """,
        (cliente_id,),
    ).fetchone()

    total_historico = int(emprestimos["total_historico_emprestado_centavos"] or 0)
    principal = int(emprestimos["principal_em_aberto_centavos"] or 0)
    juros_abertos = int(juros["juros_em_aberto_centavos"] or 0)

    return {
        "quantidade_emprestimos": int(emprestimos["quantidade_emprestimos"] or 0),
        "total_historico_emprestado_centavos": total_historico,
        "principal_em_aberto_centavos": principal,
        "juros_em_aberto_centavos": juros_abertos,
        "total_a_receber_centavos": principal + juros_abertos,
    }


def posicao_emprestimos_cliente(
    db: sqlite3.Connection,
    cliente_id: int,
) -> list[sqlite3.Row]:
    return db.execute(
        """
        SELECT e.id, e.descricao, e.data_emprestimo,
               e.valor_original_centavos, e.saldo_atual_centavos,
               e.taxa_juros_mensal, e.data_primeiro_vencimento,
               e.dia_vencimento, e.status,
               COALESCE((
                    SELECT SUM(t.valor_previsto_centavos)
                      FROM titulos_receber t
                     WHERE t.emprestimo_id = e.id
                       AND t.status IN ('PREVISTO', 'VENCIDO')
               ), 0) AS juros_em_aberto_centavos,
               COALESCE((
                    SELECT SUM(m.valor_centavos)
                      FROM movimentacoes_emprestimo m
                     WHERE m.emprestimo_id = e.id
                       AND m.tipo = 'JUROS'
               ), 0) AS juros_recebidos_centavos,
               (
                    SELECT MAX(m.data_movimento)
                      FROM movimentacoes_emprestimo m
                     WHERE m.emprestimo_id = e.id
                       AND m.tipo IN ('JUROS', 'ABATIMENTO', 'QUITACAO')
               ) AS ultimo_recebimento
          FROM emprestimos e
         WHERE e.cliente_id = ?
         ORDER BY
               CASE WHEN e.status = 'QUITADO' THEN 1 ELSE 0 END,
               e.data_emprestimo,
               e.id
        """,
        (cliente_id,),
    ).fetchall()


def conferencia_mensal_cliente(
    db: sqlite3.Connection,
    cliente_id: int,
    start_date: date,
    end_date: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Compara, mês a mês:
    1) o juro esperado pela COMPETÊNCIA;
    2) o que realmente foi recebido daquela competência;
    3) o que entrou no caixa no mês calendário.

    Também retorna as pendências detalhadas por contrato/competência.
    """
    competencias = iter_months(start_date, end_date)

    emprestimos = db.execute(
        """
        SELECT id, cliente_id, descricao, data_emprestimo,
               valor_original_centavos, saldo_atual_centavos,
               taxa_juros_mensal, data_primeiro_vencimento,
               dia_vencimento, status
          FROM emprestimos
         WHERE cliente_id = ?
         ORDER BY data_emprestimo, id
        """,
        (cliente_id,),
    ).fetchall()

    juros_rows = db.execute(
        """
        SELECT m.emprestimo_id, m.competencia,
               COALESCE(SUM(m.valor_centavos), 0) AS recebido_centavos,
               GROUP_CONCAT(DISTINCT m.data_movimento) AS datas_pagamento
          FROM movimentacoes_emprestimo m
          JOIN emprestimos e ON e.id = m.emprestimo_id
         WHERE e.cliente_id = ?
           AND m.tipo = 'JUROS'
           AND m.competencia IS NOT NULL
           AND m.competencia BETWEEN ? AND ?
         GROUP BY m.emprestimo_id, m.competencia
        """,
        (
            cliente_id,
            start_date.strftime("%Y-%m"),
            end_date.strftime("%Y-%m"),
        ),
    ).fetchall()

    juros_por_contrato_comp = {
        (int(row["emprestimo_id"]), row["competencia"]): {
            "recebido_centavos": int(row["recebido_centavos"] or 0),
            "datas_pagamento": row["datas_pagamento"] or "",
        }
        for row in juros_rows
    }

    caixa_rows = db.execute(
        """
        SELECT substr(m.data_movimento, 1, 7) AS mes_pagamento,
               COALESCE(SUM(
                    CASE WHEN m.tipo = 'JUROS'
                         THEN m.valor_centavos ELSE 0 END
               ), 0) AS juros_recebidos_centavos,
               COALESCE(SUM(
                    CASE WHEN m.tipo IN ('JUROS', 'ABATIMENTO', 'QUITACAO')
                         THEN m.valor_centavos ELSE 0 END
               ), 0) AS total_recebido_centavos,
               COUNT(
                    CASE WHEN m.tipo IN ('JUROS', 'ABATIMENTO', 'QUITACAO')
                         THEN 1 END
               ) AS quantidade_recebimentos
          FROM movimentacoes_emprestimo m
          JOIN emprestimos e ON e.id = m.emprestimo_id
         WHERE e.cliente_id = ?
           AND m.data_movimento BETWEEN ? AND ?
         GROUP BY substr(m.data_movimento, 1, 7)
        """,
        (cliente_id, start_date.isoformat(), end_date.isoformat()),
    ).fetchall()

    caixa_por_mes = {
        row["mes_pagamento"]: {
            "juros_recebidos_centavos": int(row["juros_recebidos_centavos"] or 0),
            "total_recebido_centavos": int(row["total_recebido_centavos"] or 0),
            "quantidade_recebimentos": int(row["quantidade_recebimentos"] or 0),
        }
        for row in caixa_rows
    }

    quitacoes = db.execute(
        """
        SELECT m.emprestimo_id, MIN(m.data_movimento) AS data_quitacao
          FROM movimentacoes_emprestimo m
          JOIN emprestimos e ON e.id = m.emprestimo_id
         WHERE e.cliente_id = ?
           AND m.tipo = 'QUITACAO'
         GROUP BY m.emprestimo_id
        """,
        (cliente_id,),
    ).fetchall()

    quitacao_por_emprestimo = {
        int(row["emprestimo_id"]): (
            date.fromisoformat(row["data_quitacao"])
            if row["data_quitacao"]
            else None
        )
        for row in quitacoes
    }

    consolidado: dict[str, dict[str, Any]] = {
        competencia: {
            "competencia": competencia,
            "esperado_centavos": 0,
            "recebido_competencia_centavos": 0,
            "pendente_centavos": 0,
            "contratos_previstos": 0,
            "contratos_pendentes": 0,
            "datas_pagamento": set(),
        }
        for competencia in competencias
    }

    pendencias: list[dict[str, Any]] = []

    for emprestimo in emprestimos:
        primeiro_vencimento = primeiro_vencimento_emprestimo(emprestimo)
        dia_vencimento = int(
            emprestimo["dia_vencimento"] or primeiro_vencimento.day
        )
        data_quitacao = quitacao_por_emprestimo.get(int(emprestimo["id"]))

        for competencia in competencias:
            vencimento = due_date_for_competence(
                competencia=competencia,
                dia_vencimento=dia_vencimento,
            )

            if vencimento < primeiro_vencimento:
                continue

            if data_quitacao is not None and data_quitacao < vencimento:
                continue

            saldo_base = saldo_principal_antes_da_data(
                db,
                int(emprestimo["id"]),
                vencimento,
            )

            if saldo_base <= 0:
                continue

            esperado = calcular_juros_centavos(
                saldo_base,
                emprestimo["taxa_juros_mensal"],
            )

            if esperado <= 0:
                continue

            chave = (int(emprestimo["id"]), competencia)
            recebido_info = juros_por_contrato_comp.get(
                chave,
                {"recebido_centavos": 0, "datas_pagamento": ""},
            )
            recebido = int(recebido_info["recebido_centavos"] or 0)
            pendente = max(esperado - recebido, 0)

            agregado = consolidado[competencia]
            agregado["esperado_centavos"] += esperado
            agregado["recebido_competencia_centavos"] += recebido
            agregado["pendente_centavos"] += pendente
            agregado["contratos_previstos"] += 1

            datas = [
                item.strip()
                for item in str(recebido_info["datas_pagamento"] or "").split(",")
                if item.strip()
            ]
            agregado["datas_pagamento"].update(datas)

            if pendente > 0:
                agregado["contratos_pendentes"] += 1
                pendencias.append(
                    {
                        "competencia": competencia,
                        "emprestimo_id": int(emprestimo["id"]),
                        "descricao": emprestimo["descricao"],
                        "vencimento": vencimento,
                        "saldo_base_centavos": saldo_base,
                        "taxa_juros_mensal": emprestimo["taxa_juros_mensal"],
                        "esperado_centavos": esperado,
                        "recebido_centavos": recebido,
                        "pendente_centavos": pendente,
                        "datas_pagamento": datas,
                        "situacao": (
                            "SEM PAGAMENTO"
                            if recebido == 0
                            else "PARCIAL"
                        ),
                    }
                )

    linhas: list[dict[str, Any]] = []

    for competencia in competencias:
        row = consolidado[competencia]
        caixa = caixa_por_mes.get(
            competencia,
            {
                "juros_recebidos_centavos": 0,
                "total_recebido_centavos": 0,
                "quantidade_recebimentos": 0,
            },
        )

        esperado = int(row["esperado_centavos"])
        recebido_comp = int(row["recebido_competencia_centavos"])
        pendente = int(row["pendente_centavos"])

        if esperado <= 0:
            situacao_competencia = "SEM PREVISÃO"
        elif recebido_comp == 0:
            situacao_competencia = "SEM PAGAMENTO"
        elif pendente > 0:
            situacao_competencia = "PARCIAL"
        elif recebido_comp > esperado:
            situacao_competencia = "A MAIOR"
        else:
            situacao_competencia = "PAGO"

        juros_mes = int(caixa["juros_recebidos_centavos"])
        total_mes = int(caixa["total_recebido_centavos"])

        if total_mes == 0:
            situacao_caixa = "SEM RECEBIMENTO"
        elif juros_mes == 0:
            situacao_caixa = "SEM JUROS"
        else:
            situacao_caixa = "COM RECEBIMENTO"

        linhas.append(
            {
                "competencia": competencia,
                "esperado_centavos": esperado,
                "recebido_competencia_centavos": recebido_comp,
                "pendente_centavos": pendente,
                "contratos_previstos": int(row["contratos_previstos"]),
                "contratos_pendentes": int(row["contratos_pendentes"]),
                "datas_pagamento": sorted(row["datas_pagamento"]),
                "situacao_competencia": situacao_competencia,
                "juros_recebidos_mes_centavos": juros_mes,
                "total_recebido_mes_centavos": total_mes,
                "quantidade_recebimentos_mes": int(
                    caixa["quantidade_recebimentos"]
                ),
                "situacao_caixa": situacao_caixa,
            }
        )

    pendencias.sort(
        key=lambda item: (
            item["competencia"],
            item["emprestimo_id"],
        )
    )

    return linhas, pendencias


def extrato_movimentacoes_cliente(
    db: sqlite3.Connection,
    cliente_id: int,
    start_date: date,
    end_date: date,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """
    Extrato bancário consolidado do cliente.

    Saldo apresentado = principal total ainda emprestado ao cliente após cada
    lançamento; juros não alteram esse saldo.
    """
    emprestimos = db.execute(
        """
        SELECT id, data_emprestimo
          FROM emprestimos
         WHERE cliente_id = ?
        """,
        (cliente_id,),
    ).fetchall()

    saldo_abertura = 0
    for emprestimo in emprestimos:
        data_emprestimo = date.fromisoformat(emprestimo["data_emprestimo"])
        if data_emprestimo < start_date:
            saldo_abertura += saldo_principal_antes_da_data(
                db,
                int(emprestimo["id"]),
                start_date,
            )

    rows = db.execute(
        """
        SELECT m.id, m.tipo, m.data_movimento, m.valor_centavos,
               m.competencia, m.observacao, m.pagamento_integrado_id,
               m.titulo_receber_id,
               e.id AS emprestimo_id, e.descricao AS emprestimo_descricao,
               COALESCE(m.origem_banco_snapshot, co.banco) AS origem_banco,
               COALESCE(m.origem_pix_snapshot, co.chave_pix) AS origem_pix,
               COALESCE(m.destino_banco_snapshot, cd.banco) AS destino_banco,
               COALESCE(m.destino_pix_snapshot, cd.chave_pix) AS destino_pix,
               u.nome AS usuario_nome
          FROM movimentacoes_emprestimo m
          JOIN emprestimos e ON e.id = m.emprestimo_id
          LEFT JOIN usuarios u ON u.id = m.usuario_id
          LEFT JOIN contas_bancarias co ON co.id = m.conta_origem_id
          LEFT JOIN contas_bancarias cd ON cd.id = m.conta_destino_id
         WHERE e.cliente_id = ?
           AND m.data_movimento BETWEEN ? AND ?
         ORDER BY m.data_movimento, m.id
        """,
        (cliente_id, start_date.isoformat(), end_date.isoformat()),
    ).fetchall()

    saldo_principal = saldo_abertura
    result: list[dict[str, Any]] = []

    total_entradas = 0
    total_saidas = 0
    juros_recebidos = 0
    principal_recebido = 0

    for row in rows:
        item = dict(row)
        valor = int(row["valor_centavos"] or 0)
        tipo = row["tipo"]

        entrada = 0
        saida = 0

        if tipo == "EMPRESTIMO":
            saida = valor
            saldo_principal += valor
        elif tipo == "JUROS":
            entrada = valor
            juros_recebidos += valor
        elif tipo in {"ABATIMENTO", "QUITACAO"}:
            entrada = valor
            principal_recebido += valor
            saldo_principal = max(0, saldo_principal - valor)

        total_entradas += entrada
        total_saidas += saida

        mes_pagamento = str(row["data_movimento"])[:7]
        competencia = row["competencia"]

        item.update(
            {
                "entrada_centavos": entrada,
                "saida_centavos": saida,
                "saldo_principal_cliente_centavos": saldo_principal,
                "mes_pagamento": mes_pagamento,
                "competencia_divergente": bool(
                    tipo == "JUROS"
                    and competencia
                    and competencia != mes_pagamento
                ),
            }
        )
        result.append(item)

    return result, {
        "saldo_abertura_centavos": saldo_abertura,
        "total_entradas_centavos": total_entradas,
        "total_saidas_centavos": total_saidas,
        "juros_recebidos_centavos": juros_recebidos,
        "principal_recebido_centavos": principal_recebido,
        "fluxo_liquido_centavos": total_entradas - total_saidas,
        "saldo_principal_final_centavos": saldo_principal,
    }


def get_cliente_or_404(cliente_id: int) -> sqlite3.Row:
    cliente = get_db().execute(
        "SELECT * FROM clientes WHERE id = ?",
        (cliente_id,),
    ).fetchone()

    if cliente is None:
        abort(404)

    return cliente


def get_emprestimo_or_404(emprestimo_id: int) -> sqlite3.Row:
    emprestimo = get_db().execute(
        """
        SELECT e.*,
               c.nome AS cliente_nome,
               c.cpf AS cliente_cpf,
               c.telefone AS cliente_telefone,
               c.ativo AS cliente_ativo
          FROM emprestimos e
          JOIN clientes c ON c.id = e.cliente_id
         WHERE e.id = ?
        """,
        (emprestimo_id,),
    ).fetchone()

    if emprestimo is None:
        abort(404)

    return emprestimo


app = create_app()


if __name__ == "__main__":
    host = os.environ.get("EMPRESTIMO_HOST", "127.0.0.1")
    port = int(os.environ.get("EMPRESTIMO_PORT", "5000"))
    debug = env_bool("EMPRESTIMO_DEBUG", False)

    print()
    print("Sistema de Empréstimos")
    print("----------------------")
    print(f"Banco: {DATABASE_PATH}")
    print(f"Servidor: http://{host}:{port}")
    print(f"Debug: {debug}")
    print()

    # Uso direto com python app.py é destinado a desenvolvimento/testes.
    # Produção Windows usa Waitress; hospedagens usam WSGI.
    app.run(
        host=host,
        port=port,
        debug=debug,
    )
