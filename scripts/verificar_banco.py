"""Valida a atualização numa cópia temporária, sem substituir o banco original."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def financeiro(db):
    specifications={
        'emprestimos':['id','cliente_id','valor_original_centavos','saldo_atual_centavos','status'],
        'movimentacoes_emprestimo':['id','emprestimo_id','tipo','data_movimento','valor_centavos'],
        'titulos_receber':['id','emprestimo_id','competencia','data_vencimento','valor_previsto_centavos','valor_recebido_centavos','status'],
        'pagamentos_integrados':['id','cliente_id','data_pagamento','valor_total_centavos'],
        'pagamentos_integrados_itens':['id','pagamento_integrado_id','emprestimo_id','valor_centavos'],
        'parcelas_cartao':['id','valor_centavos','status','data_pagamento'],
    }
    result={}
    for table,columns in specifications.items():
        available={r[1] for r in db.execute(f'PRAGMA table_info({table})')}
        selected=[c for c in columns if c in available]
        if not selected:
            continue
        rows=[tuple(r) for r in db.execute(f'SELECT {",".join(selected)} FROM {table} ORDER BY id')]
        result[table]={'colunas':selected,'quantidade':len(rows),
            'hash':hashlib.sha256(json.dumps(rows,ensure_ascii=False).encode()).hexdigest()}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('banco',type=Path)
    args=parser.parse_args()
    source=args.banco.expanduser().resolve()
    if not source.is_file():
        parser.error('Arquivo de banco não encontrado.')
    with tempfile.TemporaryDirectory(prefix='emprestimo-validacao-') as tmp:
        clone=Path(tmp)/'emprestimos.db'
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as original,closing(sqlite3.connect(clone)) as copied:
            original.backup(copied)
        with closing(sqlite3.connect(clone)) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValueError('A verificação de integridade do banco falhou.')
            before=financeiro(db)
            if 'emprestimos' not in before or 'movimentacoes_emprestimo' not in before:
                raise ValueError('O arquivo não possui as tabelas esperadas deste sistema.')
        os.environ.update(EMPRESTIMO_DATA_DIR=tmp,EMPRESTIMO_DATABASE=str(clone),
            EMPRESTIMO_SECRET_KEY_FILE=str(Path(tmp)/'.secret_key'),SECRET_KEY=secrets.token_hex(32))
        sys.path.insert(0,str(ROOT))
        import app
        warnings=[]
        with app.app.app_context():
            db=app.get_db()
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValueError('A integridade falhou após a migração da cópia.')
            if db.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Há vínculos inválidos no banco; revise antes de substituir dados.')
            # Compara exatamente as colunas históricas, não apenas os totais.
            for table,expected in before.items():
                rows=[tuple(r) for r in db.execute(f'SELECT {",".join(expected["colunas"])} FROM {table} ORDER BY id')]
                digest=hashlib.sha256(json.dumps(rows,ensure_ascii=False).encode()).hexdigest()
                if digest!=expected['hash']:
                    raise ValueError(f'A migração alterou dados financeiros em {table}. Não substitua o banco.')
            queries=[
                ('Competências com juros duplicados históricos',"SELECT COUNT(*) FROM (SELECT 1 FROM movimentacoes_emprestimo WHERE tipo='JUROS' GROUP BY emprestimo_id,competencia HAVING COUNT(*)>1)"),
                ('Saldos parciais antigos em aberto',"SELECT COUNT(*) FROM titulos_receber WHERE natureza='SALDO_JUROS' AND status IN ('PREVISTO','VENCIDO')"),
                ('Títulos ajustados anteriormente sem discriminação de atraso',"SELECT COUNT(*) FROM titulos_receber WHERE ajuste_manual=1 AND valor_base_centavos IS NULL AND status IN ('PREVISTO','VENCIDO')"),
            ]
            for label,sql in queries:
                n=db.execute(sql).fetchone()[0]
                if n:warnings.append(f'{label}: {n}')
            files=db.execute('SELECT arquivo_nome FROM comprovantes_pagamento').fetchall()
            missing=sum(not (source.parent/'comprovantes'/r[0]).is_file() for r in files)
            if missing:warnings.append(f'Comprovantes não encontrados ao lado deste banco: {missing}; copie também a pasta comprovantes.')
        print('Migração validada em cópia temporária. Banco original não foi substituído.')
        print('Integridade e vínculos: OK. Valores, saldos, datas e baixas históricos: preservados.')
        print('Registros conferidos: '+', '.join(f'{t}: {v["quantidade"]}' for t,v in before.items()))
        for warning in warnings:print('Conferir antes de usar: '+warning)
        if warnings:print('A estrutura é compatível, mas os alertas exigem conferência operacional.')
        else:print('Estrutura compatível com esta versão. Faça o teste funcional antes da troca definitiva.')


if __name__=='__main__':
    try:main()
    except (ValueError,sqlite3.DatabaseError) as exc:
        print(f'VALIDAÇÃO NÃO CONCLUÍDA: {exc}',file=sys.stderr)
        sys.exit(1)
