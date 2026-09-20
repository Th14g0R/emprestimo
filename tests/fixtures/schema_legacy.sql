-- Estrutura legada anterior à v2; sem registros ou dados privados.
CREATE TABLE auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            entidade TEXT NOT NULL,
            entidade_id INTEGER,
            acao TEXT NOT NULL,
            detalhes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON UPDATE CASCADE ON DELETE SET NULL
        );
CREATE TABLE cartoes_credito (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            descricao TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, dia_vencimento INTEGER,
            FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON UPDATE CASCADE ON DELETE RESTRICT
        );
CREATE TABLE clientes (
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
CREATE TABLE contas_bancarias (
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
CREATE TABLE emprestimos (
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
CREATE TABLE lancamentos_cartao (
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
CREATE TABLE movimentacoes_emprestimo (
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
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, competencia TEXT, usuario_id INTEGER, saldo_antes_centavos INTEGER, saldo_depois_centavos INTEGER, updated_at TEXT, usuario_ultima_alteracao_id INTEGER, pagamento_integrado_id INTEGER, titulo_receber_id INTEGER,
            FOREIGN KEY (emprestimo_id) REFERENCES emprestimos(id) ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (conta_origem_id) REFERENCES contas_bancarias(id) ON UPDATE CASCADE ON DELETE RESTRICT,
            FOREIGN KEY (conta_destino_id) REFERENCES contas_bancarias(id) ON UPDATE CASCADE ON DELETE RESTRICT
        );
CREATE TABLE pagamentos_integrados (
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
CREATE TABLE pagamentos_integrados_itens (
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
CREATE TABLE parcelas_cartao (
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
CREATE TABLE titulos_receber (
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
CREATE TABLE usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            login TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        , tentativas_falhas INTEGER NOT NULL DEFAULT 0, bloqueado_ate TEXT);
CREATE INDEX idx_auditoria_created_at
            ON auditoria(created_at);
CREATE INDEX idx_auditoria_entidade
            ON auditoria(entidade, entidade_id);
CREATE INDEX idx_cartoes_cliente ON cartoes_credito(cliente_id);
CREATE INDEX idx_clientes_cpf ON clientes(cpf);
CREATE INDEX idx_clientes_nome ON clientes(nome);
CREATE INDEX idx_contas_cliente ON contas_bancarias(cliente_id);
CREATE INDEX idx_contas_tipo_ativo ON contas_bancarias(tipo_titular, ativo);
CREATE INDEX idx_emprestimos_cliente ON emprestimos(cliente_id);
CREATE INDEX idx_emprestimos_data ON emprestimos(data_emprestimo);
CREATE INDEX idx_emprestimos_status ON emprestimos(status);
CREATE INDEX idx_juros_emprestimo_competencia
            ON movimentacoes_emprestimo(emprestimo_id, competencia)
         WHERE tipo = 'JUROS'
           AND competencia IS NOT NULL
        ;
CREATE INDEX idx_lancamentos_cartao ON lancamentos_cartao(cartao_credito_id);
CREATE INDEX idx_movimentacoes_conta_destino ON movimentacoes_emprestimo(conta_destino_id);
CREATE INDEX idx_movimentacoes_conta_origem ON movimentacoes_emprestimo(conta_origem_id);
CREATE INDEX idx_movimentacoes_data ON movimentacoes_emprestimo(data_movimento);
CREATE INDEX idx_movimentacoes_emprestimo ON movimentacoes_emprestimo(emprestimo_id);
CREATE INDEX idx_movimentacoes_pagamento_integrado ON movimentacoes_emprestimo(pagamento_integrado_id);
CREATE INDEX idx_movimentacoes_tipo_competencia
            ON movimentacoes_emprestimo(tipo, competencia)
        ;
CREATE INDEX idx_movimentacoes_titulo_receber ON movimentacoes_emprestimo(titulo_receber_id);
CREATE INDEX idx_pagamentos_integrados_cliente
            ON pagamentos_integrados(cliente_id);
CREATE INDEX idx_pagamentos_integrados_data
            ON pagamentos_integrados(data_pagamento);
CREATE INDEX idx_pagamentos_integrados_itens_emprestimo
            ON pagamentos_integrados_itens(emprestimo_id);
CREATE INDEX idx_pagamentos_integrados_itens_pagamento
            ON pagamentos_integrados_itens(pagamento_integrado_id);
CREATE INDEX idx_pagamentos_integrados_itens_titulo ON pagamentos_integrados_itens(titulo_receber_id);
CREATE INDEX idx_parcelas_conta_destino ON parcelas_cartao(conta_destino_id);
CREATE INDEX idx_parcelas_conta_origem ON parcelas_cartao(conta_origem_id);
CREATE INDEX idx_parcelas_status ON parcelas_cartao(status);
CREATE INDEX idx_parcelas_vencimento ON parcelas_cartao(vencimento);
CREATE INDEX idx_titulos_receber_competencia ON titulos_receber(emprestimo_id, competencia);
CREATE INDEX idx_titulos_receber_emprestimo ON titulos_receber(emprestimo_id);
CREATE INDEX idx_titulos_receber_origem ON titulos_receber(titulo_origem_id);
CREATE INDEX idx_titulos_receber_status ON titulos_receber(status);
CREATE INDEX idx_titulos_receber_vencimento ON titulos_receber(data_vencimento);
