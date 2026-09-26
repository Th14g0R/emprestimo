"""Conexões SQLite, schema e migrações incrementais."""
from __future__ import annotations

import sqlite3
from flask import g
from financial_rules import install_guards
from transactions import Connection


def current_database_path() -> str:
    from flask import current_app

    return current_app.config["DATABASE"]


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        connection = sqlite3.connect(
            current_database_path(),
            timeout=10,
            factory=Connection,
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
        CREATE INDEX IF NOT EXISTS idx_titulos_receber_status_vencimento ON titulos_receber(status, data_vencimento, emprestimo_id);


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
    add_column_if_missing(db, "usuarios", "tentativas_falhas", "INTEGER NOT NULL DEFAULT 0")
    add_column_if_missing(db, "usuarios", "bloqueado_ate", "TEXT")
    add_column_if_missing(db, "cartoes_credito", "dia_vencimento", "INTEGER")
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
        "CREATE INDEX IF NOT EXISTS idx_titulos_receber_status_vencimento ON titulos_receber(status, data_vencimento, emprestimo_id)"
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

    # V26: campos opcionais; valores e baixas históricas não são recalculados.
    for tabela in ("titulos_receber", "movimentacoes_emprestimo", "pagamentos_integrados_itens"):
        for coluna, definicao in (
            ("valor_base_centavos", "INTEGER"),
            ("data_base_atraso", "TEXT"),
            ("dias_atraso", "INTEGER NOT NULL DEFAULT 0"),
            ("juros_atraso_centavos", "INTEGER NOT NULL DEFAULT 0"),
            ("data_calculo_atraso", "TEXT"),
        ):
            add_column_if_missing(db, tabela, coluna, definicao)

    install_guards(db)
