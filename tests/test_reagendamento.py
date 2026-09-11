import os
import tempfile
import unittest
from datetime import date
from pathlib import Path

TEMP = tempfile.TemporaryDirectory()
os.environ['EMPRESTIMO_DATA_DIR'] = TEMP.name
os.environ['EMPRESTIMO_DATABASE'] = str(Path(TEMP.name) / 'test.db')
os.environ['SECRET_KEY'] = 'test-only'
import app as sistema
from reagendamento import planejar


class ReagendamentoTest(unittest.TestCase):
    def setUp(self):
        self.app = sistema.app
        self.app.config['TESTING'] = True
        self.ctx = self.app.app_context()
        self.ctx.push()
        self.db = sistema.get_db()
        for table in ('auditoria', 'titulos_receber', 'movimentacoes_emprestimo', 'emprestimos', 'clientes', 'usuarios'):
            self.db.execute(f'DELETE FROM {table}')
        self.db.execute("INSERT INTO usuarios(id,nome,login,senha_hash) VALUES(1,'Teste','teste',?)", (sistema.generate_password_hash('senha'),))
        self.db.execute("INSERT INTO clientes(id,nome) VALUES(1,'Cliente')")
        self.db.execute("""INSERT INTO emprestimos(id,cliente_id,data_emprestimo,valor_original_centavos,
            saldo_atual_centavos,taxa_juros_mensal,data_primeiro_vencimento,dia_vencimento)
            VALUES(1,1,'2026-01-04',100000,100000,40,'2026-02-04',4)""")
        for id, due in [(1, '2026-02-04'), (2, '2026-03-04')]:
            self.db.execute("""INSERT INTO titulos_receber(id,emprestimo_id,tipo,competencia,data_vencimento,
                valor_previsto_centavos,saldo_base_centavos,taxa_juros_mensal,status)
                VALUES(?,1,'JUROS',?,?,40000,100000,40,'PREVISTO')""", (id,due[:7],due))
        self.db.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['usuario_id'] = 1
            session['csrf_token'] = 'csrf-test'

    def tearDown(self):
        self.ctx.pop()

    def rows(self):
        return [sistema.get_titulo_receber_or_404(i) for i in (1,2)]

    def test_transition_only_once(self):
        result = planejar(self.rows(), dia=14, proporcional=True)
        self.assertEqual([r['valor'] for r in result], [53333,40000])
        self.assertEqual([r['dias'] for r in result], [10,10])

    def test_month_end_and_invalid_status(self):
        result = planejar(self.rows(), dia=31)
        self.assertEqual(result[0]['nova_data'], '2026-02-28')
        with self.assertRaises(ValueError):
            planejar(self.rows(), dia=1, proporcional=True)
        self.db.execute("UPDATE titulos_receber SET status='RECEBIDO' WHERE id=1")
        with self.assertRaises(ValueError):
            planejar(self.rows(), dia=14)

    def test_preview_save_and_replay(self):
        import re
        data = dict(csrf_token='csrf-test', titulo_id=['1','2'], dia='14', proporcional='1', acao='prever')
        response = self.client.post('/receber/alterar-lote', data=data)
        self.assertEqual(response.status_code,200)
        signature = re.search(r'name="assinatura" value="([a-f0-9]+)"', response.text)[1]
        self.assertEqual(self.rows()[0]['valor_previsto_centavos'],40000)
        data.update(acao='salvar', assinatura=signature, senha_confirmacao='senha', motivo='Reagendamento combinado')
        self.assertEqual(self.client.post('/receber/alterar-lote',data=data).status_code,302)
        self.assertEqual(self.rows()[0]['valor_previsto_centavos'],53333)
        self.client.post('/receber/alterar-lote',data=data)
        self.assertEqual(self.rows()[0]['valor_previsto_centavos'],53333)
        sistema.sync_receivable_titles(self.db)
        self.assertEqual(self.rows()[0]['valor_previsto_centavos'],53333)
        self.assertEqual(self.db.execute('SELECT saldo_atual_centavos FROM emprestimos').fetchone()[0],100000)

    def test_csrf_and_templates(self):
        self.assertEqual(self.client.post('/receber/alterar-lote').status_code,400)
        for name in self.app.jinja_env.list_templates():
            self.app.jinja_env.get_template(name)

    def test_wrong_password_and_atomic_rollback(self):
        import re
        data = dict(csrf_token='csrf-test', titulo_id=['1'], dia='14', futuros='1', acao='prever')
        response = self.client.post('/receber/alterar-lote', data=data)
        signature = re.search(r'name="assinatura" value="([a-f0-9]+)"', response.text)[1]
        data.update(acao='salvar', assinatura=signature, senha_confirmacao='errada', motivo='Novo vencimento')
        self.client.post('/receber/alterar-lote',data=data)
        self.assertEqual(self.rows()[0]['data_vencimento'],'2026-02-04')
        data['senha_confirmacao'] = 'senha'
        self.client.post('/receber/alterar-lote',data=data)
        self.assertEqual(self.rows()[0]['data_vencimento'],'2026-02-04')
        self.assertIsNone(self.db.execute("SELECT 1 FROM auditoria WHERE acao='REAGENDADO'").fetchone())

    def test_render_pages(self):
        for url in ('/receber', '/receber/1', '/receber/1/editar', '/emprestimos/1', '/movimentacoes', '/'):
            response = self.client.get(url)
            self.assertLess(response.status_code,400, url)

    def test_automatic_preview_is_read_only(self):
        data = dict(csrf_token='csrf-test', titulo_id=['1','2'], dia='14', proporcional='1', acao='prever')
        response = self.client.post('/receber/alterar-lote', data=data, headers={'X-Receivable-Preview':'1'})
        self.assertEqual(response.status_code,200)
        self.assertIsNone(response.json['erro'])
        self.assertIn('533,33', response.json['html'])
        self.assertTrue(response.json['assinatura'])
        self.assertEqual(self.rows()[0]['valor_previsto_centavos'],40000)
        data['dia'] = '1'
        response = self.client.post('/receber/alterar-lote', data=data, headers={'X-Receivable-Preview':'1'})
        self.assertTrue(response.json['erro'])
        self.assertEqual(response.json['assinatura'],'')
        data['acao'] = 'salvar'
        response = self.client.post('/receber/alterar-lote', data=data, headers={'X-Receivable-Preview':'1'})
        self.assertTrue(response.json['erro'])

    def test_filter_by_loan(self):
        response = self.client.get('/receber?emprestimo_id=1')
        self.assertIn('form="lote" name="titulo_id"', response.text)
        response = self.client.get('/receber?emprestimo_id=999999')
        self.assertNotIn('form="lote" name="titulo_id"', response.text)

    def test_reversal_reopens_and_audits(self):
        self.db.execute("""INSERT INTO movimentacoes_emprestimo(id,emprestimo_id,tipo,data_movimento,
            valor_centavos,competencia,titulo_receber_id) VALUES(1,1,'JUROS','2026-02-04',40000,'2026-02',1)""")
        self.db.execute("UPDATE titulos_receber SET status='RECEBIDO',movimentacao_id=1,valor_recebido_centavos=40000,data_recebimento='2026-02-04' WHERE id=1")
        self.db.commit()
        response = self.client.get('/receber/1/estornar')
        self.assertIn('/movimentacoes/1/excluir',response.location)
        response = self.client.post(response.location,data=dict(csrf_token='csrf-test',senha_confirmacao='senha',motivo_exclusao='Baixa por engano'))
        self.assertEqual(response.status_code,302)
        row = self.rows()[0]
        self.assertIn(row['status'],['PREVISTO','VENCIDO'])
        self.assertIsNone(row['data_recebimento'])
        self.assertEqual(row['valor_recebido_centavos'],0)
        self.assertTrue(self.db.execute("SELECT 1 FROM auditoria WHERE acao='EXCLUIDA'").fetchone())


if __name__ == '__main__':
    unittest.main()
