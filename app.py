from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
from calendar import monthrange
from datetime import date, datetime
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


def migrate_schema(db: sqlite3.Connection) -> None:
    """Aplica pequenas evoluções de schema sem apagar o banco existente."""
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

    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_juros_emprestimo_competencia
            ON movimentacoes_emprestimo(emprestimo_id, competencia)
         WHERE tipo = 'JUROS'
           AND competencia IS NOT NULL
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


def format_date_br(value: str | None) -> str:
    if not value:
        return "-"

    try:
        return date.fromisoformat(value[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return value


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

        return render_template(
            "dashboard.html",
            metrics=metrics,
            ultimos_emprestimos=ultimos_emprestimos,
            ultimas_movimentacoes=ultimas_movimentacoes,
            mes_atual=mes_atual,
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

    # -------------------- Movimentações --------------------

    @app.route("/movimentacoes/<int:movimentacao_id>/editar", methods=["GET", "POST"])
    @login_required
    def movimentacoes_editar(movimentacao_id: int):
        movimento = get_movimentacao_or_404(movimentacao_id)
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
                else:
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
        mes = request.args.get("mes", "").strip()
        termo = request.args.get("q", "").strip()

        tipos_validos = {"EMPRESTIMO", "JUROS", "ABATIMENTO", "QUITACAO"}

        sql = """
            SELECT m.id, m.tipo, m.data_movimento, m.valor_centavos,
                   m.observacao, m.competencia,
                   m.saldo_antes_centavos, m.saldo_depois_centavos,
                   e.id AS emprestimo_id, c.id AS cliente_id, c.nome AS cliente_nome,
                   u.nome AS usuario_nome,
                   COALESCE(m.origem_banco_snapshot, co.banco) AS origem_banco, COALESCE(m.origem_pix_snapshot, co.chave_pix) AS origem_pix,
                   COALESCE(m.destino_banco_snapshot, cd.banco) AS destino_banco, COALESCE(m.destino_pix_snapshot, cd.chave_pix) AS destino_pix
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

        if parse_competencia(mes) is not None:
            sql += " AND substr(m.data_movimento, 1, 7) = ?"
            params.append(mes)

        if termo:
            like = f"%{termo}%"
            sql += """
                AND (
                    c.nome LIKE ? COLLATE NOCASE
                    OR CAST(e.id AS TEXT) LIKE ?
                    OR m.observacao LIKE ? COLLATE NOCASE
                )
            """
            params.extend([like, like, like])

        sql += " ORDER BY m.data_movimento DESC, m.id DESC LIMIT 500"

        movimentacoes = get_db().execute(sql, params).fetchall()

        return render_template(
            "movimentacoes/lista.html",
            movimentacoes=movimentacoes,
            tipo=tipo.lower(),
            mes=mes,
            termo=termo,
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
