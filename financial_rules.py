"""Proteções incrementais, preservando movimentos históricos."""


def install_guards(db):
    # Triggers permitem preservar eventuais duplicidades históricas sem criar
    # novas. Um índice UNIQUE falharia na migração de bases antigas divergentes.
    statements = [
        """CREATE TRIGGER IF NOT EXISTS juros_unicos_novos
        BEFORE INSERT ON movimentacoes_emprestimo WHEN NEW.tipo='JUROS'
        BEGIN
            SELECT CASE WHEN NEW.competencia IS NULL OR NEW.competencia=''
                THEN RAISE(ABORT,'Informe a competencia dos juros.') END;
            SELECT CASE WHEN EXISTS(SELECT 1 FROM movimentacoes_emprestimo
                WHERE tipo='JUROS' AND emprestimo_id=NEW.emprestimo_id
                AND competencia=NEW.competencia)
                THEN RAISE(ABORT,'Ja existem juros para este contrato e competencia.') END;
            SELECT CASE WHEN NEW.titulo_receber_id IS NOT NULL AND EXISTS(
                SELECT 1 FROM titulos_receber WHERE id=NEW.titulo_receber_id
                AND (valor_previsto_centavos<>NEW.valor_centavos
                     OR emprestimo_id<>NEW.emprestimo_id OR competencia<>NEW.competencia))
                THEN RAISE(ABORT,'Juros devem corresponder ao titulo integral.') END;
        END""",
        """CREATE TRIGGER IF NOT EXISTS juros_unicos_correcao
        BEFORE UPDATE OF emprestimo_id,competencia,tipo ON movimentacoes_emprestimo
        WHEN NEW.tipo='JUROS' AND (OLD.tipo<>NEW.tipo
             OR OLD.emprestimo_id<>NEW.emprestimo_id OR OLD.competencia IS NOT NEW.competencia)
        BEGIN
            SELECT CASE WHEN NEW.competencia IS NULL OR NEW.competencia=''
                THEN RAISE(ABORT,'Informe a competencia dos juros.') END;
            SELECT CASE WHEN EXISTS(SELECT 1 FROM movimentacoes_emprestimo
                WHERE tipo='JUROS' AND emprestimo_id=NEW.emprestimo_id
                AND competencia=NEW.competencia AND id<>OLD.id)
                THEN RAISE(ABORT,'Ja existem juros para este contrato e competencia.') END;
        END""",
    ]
    for statement in statements:
        db.execute(statement)


def legacy_conflicts(db):
    return db.execute("""SELECT emprestimo_id,competencia,COUNT(*) AS quantidade
        FROM movimentacoes_emprestimo WHERE tipo='JUROS'
        GROUP BY emprestimo_id,competencia HAVING COUNT(*)>1""").fetchall()
