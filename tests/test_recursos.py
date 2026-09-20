"""Evita regressões de escrita ociosa e preserva atualização de previsões."""
import unittest
import test_local as fixture


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ApplicationTests()
        self.fixture.setUp()
        self.app = self.fixture.app

    def tearDown(self):
        self.fixture.tearDown()

    def test_idle_sync_does_not_write_and_queries_are_bounded(self):
        with self.app.app_context():
            db = fixture.application.get_db()
            columns = [row[1] for row in db.execute('PRAGMA table_info(emprestimos)') if row[1] != 'id']
            names = ','.join(columns)
            for _ in range(24):
                db.execute(f'INSERT INTO emprestimos ({names}) SELECT {names} FROM emprestimos WHERE id=1')
            db.commit()
            fixture.application.sync_receivable_titles(db)
            before = db.total_changes
            statements = []
            db.set_trace_callback(statements.append)
            try:
                for _ in range(3):
                    fixture.application.sync_receivable_titles(db)
            finally:
                db.set_trace_callback(None)
            self.assertEqual(db.total_changes, before)
            self.assertLessEqual(sum(s.lstrip().upper().startswith('SELECT') for s in statements), 18)

    def test_abatimento_still_updates_automatic_forecasts(self):
        response = self.fixture.payment('/emprestimos/1/abatimento', valor='200', observacao='Teste de previsão')
        self.assertEqual(response.status_code, 302)
        loans = self.fixture.rows('SELECT saldo_atual_centavos FROM emprestimos WHERE id=1')
        self.assertEqual(loans[0][0], 80000)
        titles = self.fixture.rows("SELECT valor_previsto_centavos FROM titulos_receber WHERE status='PREVISTO' AND ajuste_manual=0")
        self.assertTrue(titles)
        self.assertTrue(all(t[0] == 8000 for t in titles))

    def test_cancelled_forecast_is_never_recreated(self):
        with self.app.app_context():
            db = fixture.application.get_db()
            db.execute("UPDATE titulos_receber SET status='CANCELADO' WHERE id=1")
            db.commit()
            count = db.execute('SELECT COUNT(*) FROM titulos_receber').fetchone()[0]
            fixture.application.sync_receivable_titles(db)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM titulos_receber').fetchone()[0], count)
            self.assertEqual(db.execute('SELECT status FROM titulos_receber WHERE id=1').fetchone()[0], 'CANCELADO')
