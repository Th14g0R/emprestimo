"""Regressões financeiras e testes HTTP com banco temporário, sem dados reais."""
import io
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

_TEST_ROOT = tempfile.TemporaryDirectory(prefix='emprestimo-tests-')
os.environ['EMPRESTIMO_DATA_DIR'] = _TEST_ROOT.name
import app as application
import portal
from money import parse_money_to_centavos
from werkzeug.security import generate_password_hash


class MoneyTests(unittest.TestCase):
    def test_formats(self):
        for text, expected in [('1.234,56',123456),('1234.56',123456),('R$ 10,50',1050),('1.234',123400),('0',0),('-12,30',-1230)]:
            with self.subTest(text=text): self.assertEqual(parse_money_to_centavos(text),expected)

    def test_invalid_and_overflow(self):
        for text in ['abc123','1e3','1,234','12.34,56','1 2','NaN','inf','9'*40,'92233720368547758,08','--1','1,2,3','']:
            with self.subTest(text=text): self.assertIsNone(parse_money_to_centavos(text))


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=_TEST_ROOT.name)
        application.DATABASE_PATH=Path(self.tmp.name)/'test.db'
        portal.PROOFS_DIR=Path(self.tmp.name)/'proofs'
        self.app=application.create_app()
        self.app.config.update(TESTING=True)
        self.client=self.app.test_client()
        self.password='senha-de-teste-123'
        with self.app.app_context():
            db=application.get_db()
            db.execute('INSERT INTO usuarios(nome,login,senha_hash) VALUES(?,?,?)',('Administrador teste','admin',generate_password_hash(self.password)))
            db.commit()
        self.authenticate(self.client)
        self.post('/clientes/novo',nome='Cliente de teste',cpf='52998224725',telefone='85999999999',email='teste@example.invalid')
        self.post('/contas/nova',tipo_titular='NOSSA',banco='Banco próprio',chave_pix='proprio@example.invalid')
        self.post('/contas/nova',tipo_titular='CLIENTE',cliente_id='1',banco='Banco cliente',chave_pix='teste@example.invalid')
        self.today=date.today().isoformat()
        result=self.post('/emprestimos/novo',cliente_id='1',descricao='Contrato teste',valor_original='1.000,00',taxa_juros_mensal='10',data_emprestimo=self.today,data_primeiro_vencimento=self.today,conta_origem_id='1',conta_destino_id='2')
        self.assertEqual(result.status_code,302)
        self.client.get('/receber')

    def tearDown(self):
        self.tmp.cleanup()

    def authenticate(self,client,portal_id=None):
        with client.session_transaction() as sess:
            sess['csrf_token']='csrf-test'
            if portal_id: sess['cliente_acesso_id']=portal_id
            else: sess['usuario_id']=1

    def post(self,path,**data):
        return self.client.post(path,data={'csrf_token':'csrf-test',**data})

    def rows(self,sql,params=()):
        with self.app.app_context():return application.get_db().execute(sql,params).fetchall()

    def payment(self,path,**data):
        return self.post(path,data_movimento=self.today,conta_origem_id='2',conta_destino_id='1',**data)

    def test_render_all_admin_gets(self):
        self.post('/cartoes/novo',cliente_id='1',descricao='Cartão teste',dia_vencimento='10')
        self.post('/cartoes/1/lancamentos/novo',descricao='Compra teste',valor_total='100',quantidade_parcelas='2',data_compra=self.today,primeiro_vencimento=self.today)
        paths=['/dashboard','/clientes','/clientes/1','/clientes/1/editar','/contas','/contas/1/editar','/emprestimos','/emprestimos/1','/emprestimos/1/juros','/emprestimos/1/abatimento','/emprestimos/1/quitacao','/pagamentos-integrados','/pagamentos-integrados/novo?cliente_id=1','/movimentacoes','/movimentacoes/1/editar','/receber','/receber/1','/receber/1/editar','/receber/1/excluir','/receber/relatorio?cliente_id=1','/relatorios/clientes?cliente_id=1','/cartoes','/cartoes/novo','/cartoes/1','/cartoes/1/editar','/cartoes/1/lancamentos/novo','/lancamentos-cartao/1/editar','/parcelas-cartao/1/pagar','/acessos-clientes','/comprovantes','/auditoria']
        for path in paths:
            with self.subTest(path=path):self.assertEqual(self.client.get(path).status_code,200)

    def test_csrf_and_auth(self):
        self.assertEqual(self.client.post('/emprestimos/1/quitacao',data={}).status_code,400)
        anonymous=self.app.test_client()
        self.assertEqual(anonymous.get('/dashboard').status_code,302)
        self.assertNotIn('database_file',anonymous.get('/health').json)

    def test_interest_unique_and_does_not_change_principal(self):
        self.payment('/emprestimos/1/juros',competencia=self.today[:7])
        self.payment('/emprestimos/1/juros',competencia=self.today[:7])
        self.assertEqual(len(self.rows("SELECT * FROM movimentacoes_emprestimo WHERE tipo='JUROS'")),1)
        self.assertEqual(self.rows('SELECT saldo_atual_centavos FROM emprestimos')[0][0],100000)

    def test_partial_interest_refused(self):
        self.post('/receber/1',data_recebimento=self.today,valor_recebido='50',conta_origem_id='2',conta_destino_id='1')
        self.assertFalse(self.rows("SELECT * FROM movimentacoes_emprestimo WHERE tipo='JUROS'"))
        self.assertEqual(self.rows('SELECT status FROM titulos_receber WHERE id=1')[0][0],'PREVISTO')

    def test_full_title_received(self):
        self.post('/receber/1',data_recebimento=self.today,valor_recebido='100',conta_origem_id='2',conta_destino_id='1')
        self.assertEqual(self.rows('SELECT status FROM titulos_receber WHERE id=1')[0][0],'RECEBIDO')

    def test_single_contract_payment(self):
        response=self.post('/pagamentos-integrados/novo',cliente_id='1',titulo_id='1',valor_titulo_1='100',data_pagamento=self.today,valor_total='100',conta_origem_id='2',conta_destino_id='1')
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.rows('SELECT status FROM titulos_receber WHERE id=1')[0][0],'RECEBIDO')
        self.assertEqual(self.client.get('/pagamentos-integrados/1').status_code,200)
        self.assertEqual(self.client.get('/pagamentos-integrados/1/excluir').status_code,200)

    def test_abatimento_quitacao_and_bank_snapshots(self):
        self.payment('/emprestimos/1/abatimento',valor='100')
        self.assertEqual(self.rows('SELECT saldo_atual_centavos FROM emprestimos')[0][0],90000)
        self.payment('/emprestimos/1/quitacao')
        row=self.rows('SELECT saldo_atual_centavos,status FROM emprestimos')[0]
        self.assertEqual(tuple(row),(0,'QUITADO'))
        movement=self.rows("SELECT valor_centavos,origem_banco_snapshot,destino_banco_snapshot FROM movimentacoes_emprestimo WHERE tipo='QUITACAO'")[0]
        self.assertEqual(tuple(movement),(90000,'Banco cliente','Banco próprio'))
        self.payment('/emprestimos/1/quitacao')
        self.assertEqual(len(self.rows("SELECT * FROM movimentacoes_emprestimo WHERE tipo='QUITACAO'")),1)

    def test_concurrent_abatimentos(self):
        clients=[self.app.test_client(),self.app.test_client()]
        for client in clients:self.authenticate(client)
        barrier=threading.Barrier(2)
        def pay(client):
            barrier.wait()
            return client.post('/emprestimos/1/abatimento',data={'csrf_token':'csrf-test','data_movimento':self.today,'valor':'100','conta_origem_id':'2','conta_destino_id':'1'}).status_code
        with ThreadPoolExecutor(max_workers=2) as executor:results=list(executor.map(pay,clients))
        self.assertEqual(results,[302,302])
        self.assertEqual(self.rows('SELECT saldo_atual_centavos FROM emprestimos')[0][0],80000)
        self.assertEqual([tuple(r) for r in self.rows("SELECT saldo_antes_centavos,saldo_depois_centavos FROM movimentacoes_emprestimo WHERE tipo='ABATIMENTO' ORDER BY id")],[(100000,90000),(90000,80000)])

    def test_concurrent_interest(self):
        clients=[self.app.test_client(),self.app.test_client()]
        for client in clients:self.authenticate(client)
        barrier=threading.Barrier(2)
        def pay(client):
            barrier.wait()
            return client.post('/emprestimos/1/juros',data={'csrf_token':'csrf-test','data_movimento':self.today,'competencia':self.today[:7],'conta_origem_id':'2','conta_destino_id':'1'}).status_code
        with ThreadPoolExecutor(max_workers=2) as executor:list(executor.map(pay,clients))
        self.assertEqual(len(self.rows("SELECT * FROM movimentacoes_emprestimo WHERE tipo='JUROS'")),1)

    def test_rollback_if_audit_fails(self):
        from unittest.mock import patch
        with self.assertLogs(self.app.logger,level='ERROR'), patch.object(application,'registrar_auditoria',side_effect=sqlite3.DatabaseError('falha de teste')):
            self.payment('/emprestimos/1/abatimento',valor='100')
        self.assertEqual(self.rows('SELECT saldo_atual_centavos FROM emprestimos')[0][0],100000)
        self.assertFalse(self.rows("SELECT * FROM movimentacoes_emprestimo WHERE tipo='ABATIMENTO'"))

    def test_login_failures_persist(self):
        anonymous=self.app.test_client()
        with anonymous.session_transaction() as sess:sess['csrf_token']='csrf-test'
        for _ in range(5):
            self.assertEqual(anonymous.post('/login',data={'csrf_token':'csrf-test','login':'admin','senha':'errada'}).status_code,401)
        self.assertTrue(self.rows('SELECT bloqueado_ate FROM usuarios')[0][0])

    def test_database_guards_and_legacy_preservation(self):
        self.payment('/emprestimos/1/juros',competencia=self.today[:7])
        with self.app.app_context():
            db=application.get_db()
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO movimentacoes_emprestimo(emprestimo_id,tipo,data_movimento,valor_centavos,competencia) VALUES(1,'JUROS',?,10000,?)",(self.today,self.today[:7]))
            db.rollback()
            before=db.execute('SELECT COUNT(*) FROM movimentacoes_emprestimo').fetchone()[0]
            application.migrate_schema(db);db.commit()
            self.assertEqual(db.execute('SELECT COUNT(*) FROM movimentacoes_emprestimo').fetchone()[0],before)
            self.assertEqual(db.execute('PRAGMA foreign_keys').fetchone()[0],1)

    def test_portal_pages_and_proof(self):
        with self.app.app_context():
            db=application.get_db()
            db.execute("INSERT INTO clientes_acessos(cliente_id,email,senha_hash,status) VALUES(1,'teste@example.invalid',?,'ATIVO')",(generate_password_hash(self.password),))
            db.commit()
        client=self.app.test_client();self.authenticate(client,portal_id=1)
        for path in ['/portal','/portal/extrato','/portal/comprovantes','/portal/comprovantes/novo']:
            with self.subTest(path=path):self.assertEqual(client.get(path).status_code,200)
        from PIL import Image
        stream=io.BytesIO();Image.new('RGB',(20,20),'white').save(stream,'PNG');stream.seek(0)
        response=client.post('/portal/comprovantes/novo',data={'csrf_token':'csrf-test','titulo_id':'1','valor_1':'100','data_pagamento':self.today,'comprovante':(stream,'comprovante.png')})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.get('/comprovantes/1').status_code,200)
        self.assertEqual(self.client.get('/acessos-clientes/1/editar').status_code,200)
        with self.client.get('/comprovantes/1/arquivo') as download:
            self.assertEqual(download.status_code,200)
        response=self.post('/comprovantes/1/confirmar',conta_origem_id='2',conta_destino_id='1',senha_confirmacao=self.password)
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.rows('SELECT status FROM comprovantes_pagamento')[0][0],'CONFIRMADO')
        self.assertEqual(self.rows('SELECT status FROM titulos_receber WHERE id=1')[0][0],'RECEBIDO')

    def test_dashboard_is_read_only(self):
        with self.app.app_context():
            db=application.get_db()
            before=db.execute('SELECT COUNT(*) FROM titulos_receber').fetchone()[0]
            db.execute('DELETE FROM titulos_receber');db.commit()
        self.assertEqual(self.client.get('/dashboard').status_code,200)
        self.assertEqual(len(self.rows('SELECT * FROM titulos_receber')),0)
        self.post('/agenda/atualizar')
        self.assertEqual(len(self.rows('SELECT * FROM titulos_receber')),before)

    def test_independent_loans_and_invalid_accounts(self):
        self.post('/emprestimos/novo',cliente_id='1',descricao='Segundo contrato',valor_original='500',taxa_juros_mensal='10',data_emprestimo=self.today,data_primeiro_vencimento=self.today,conta_origem_id='1',conta_destino_id='2')
        self.payment('/emprestimos/1/abatimento',valor='100')
        self.assertEqual([r[0] for r in self.rows('SELECT saldo_atual_centavos FROM emprestimos ORDER BY id')],[90000,50000])
        self.post('/emprestimos/2/abatimento',valor='100',data_movimento=self.today,conta_origem_id='1',conta_destino_id='2')
        self.assertEqual(self.rows('SELECT saldo_atual_centavos FROM emprestimos WHERE id=2')[0][0],50000)

    def test_correction_requires_current_password_and_audit(self):
        self.payment('/emprestimos/1/abatimento',valor='100')
        values=dict(data_movimento=self.today,valor='200',conta_origem_id='2',conta_destino_id='1',motivo_correcao='Correção de teste')
        self.post('/movimentacoes/2/editar',senha_confirmacao='incorreta',**values)
        self.assertEqual(self.rows('SELECT saldo_atual_centavos FROM emprestimos')[0][0],90000)
        self.post('/movimentacoes/2/editar',senha_confirmacao=self.password,**values)
        self.assertEqual(self.rows('SELECT saldo_atual_centavos FROM emprestimos')[0][0],80000)
        self.assertTrue(self.rows("SELECT * FROM auditoria WHERE entidade='movimentacao_emprestimo'"))

    def test_legacy_duplicates_survive_migration(self):
        self.payment('/emprestimos/1/juros',competencia=self.today[:7])
        with self.app.app_context():
            db=application.get_db()
            db.execute('DROP TRIGGER juros_unicos_novos')
            db.execute("INSERT INTO movimentacoes_emprestimo(emprestimo_id,tipo,data_movimento,valor_centavos,competencia) VALUES(1,'JUROS',?,5000,?)",(self.today,self.today[:7]))
            db.commit()
            application.migrate_schema(db);db.commit()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM movimentacoes_emprestimo WHERE tipo='JUROS'").fetchone()[0],2)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT INTO movimentacoes_emprestimo(emprestimo_id,tipo,data_movimento,valor_centavos,competencia) VALUES(1,'JUROS',?,1,?)",(self.today,self.today[:7]))
            db.rollback()
        self.assertIn('ocorrências históricas',self.client.get('/dashboard').get_data(as_text=True))

    def test_rescheduling_requires_review(self):
        proposed=(date.today()+timedelta(days=10)).isoformat()
        response=self.post('/receber/alterar-lote',titulo_id='1',acao='prever',nova_data=proposed)
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.rows('SELECT data_vencimento FROM titulos_receber WHERE id=1')[0][0],self.today)
        self.post('/receber/alterar-lote',titulo_id='1',acao='salvar',nova_data=proposed,senha_confirmacao=self.password,motivo='Ajuste de agenda',assinatura='invalida')
        self.assertEqual(self.rows('SELECT data_vencimento FROM titulos_receber WHERE id=1')[0][0],self.today)

    def test_public_rate_limit(self):
        anonymous=self.app.test_client()
        with anonymous.session_transaction() as sess:sess['csrf_token']='csrf-test'
        responses=[anonymous.post('/portal/cadastro',data={'csrf_token':'csrf-test'}).status_code for _ in range(11)]
        self.assertEqual(responses[-1],429)


if __name__=='__main__':unittest.main()
