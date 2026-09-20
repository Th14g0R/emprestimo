from contextlib import closing
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import io
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from atrasos import calcular, assinatura
from reagendamento import planejar
import test_local as fixture
application=fixture.application
portal=fixture.portal


class CalculoTests(unittest.TestCase):
    def titulo(self):
        return dict(id=1,emprestimo_id=1,competencia='2026-09',natureza='JUROS',status='PREVISTO',
                    data_emprestimo='2026-08-01',data_vencimento='2026-09-01',valor_previsto_centavos=80000)

    def test_exemplo_usuario_e_arredondamento_final(self):
        for days,extra in [(0,0),(1,2667),(3,8000),(10,26667),(30,80000),(31,82667)]:
            with self.subTest(days=days):
                result=calcular(self.titulo(),date(2026,9,1)+timedelta(days=days))
                self.assertEqual(result['juros_atraso_centavos'],extra)
                self.assertEqual(result['valor_total_centavos'],80000+extra)
        self.assertEqual(calcular(self.titulo(),date(2026,8,31))['dias_atraso'],0)

    def test_reagendar_duas_vezes_sem_capitalizar(self):
        t=self.titulo()
        first=calcular(t,date(2026,9,11))
        t.update(valor_base_centavos=80000,data_base_atraso='2026-09-01',
                 data_vencimento='2026-09-11',valor_previsto_centavos=first['valor_total_centavos'])
        result=calcular(t,date(2026,9,16))
        self.assertEqual(result['juros_atraso_centavos'],40000)
        self.assertEqual(result['valor_total_centavos'],120000)

    def test_ajuste_antigo_sem_base_nao_e_capitalizado_silenciosamente(self):
        t=self.titulo()
        t.update(valor_previsto_centavos=100000,ajuste_manual=1,
                 saldo_base_centavos=1000000,taxa_juros_mensal=8)
        with self.assertRaisesRegex(ValueError,'ajuste antigo'):
            calcular(t,date(2026,9,11))
        self.assertEqual(t['valor_previsto_centavos'],100000)

    def test_virada_ano_bissexto_e_limite_dia(self):
        t=self.titulo();t.update(data_emprestimo='2023-01-01',data_vencimento='2024-02-01')
        p=planejar([t],dia=31)[0]
        self.assertEqual(p['nova_data'],'2024-02-29')
        self.assertEqual(p['dias'],28)
        t['data_vencimento']='2025-12-31'
        self.assertEqual(calcular(t,date(2026,1,2))['dias_atraso'],2)


class AtrasoHTTPTests(unittest.TestCase):
    def setUp(self):
        self.c=fixture.ApplicationTests();self.c.setUp()
        self.app=self.c.app;self.client=self.c.client
        self.today=date.today();self.due=self.today-timedelta(days=10)
        with self.app.app_context():
            db=application.get_db()
            db.execute('DELETE FROM titulos_receber')
            db.execute('''UPDATE emprestimos SET valor_original_centavos=1000000,
                saldo_atual_centavos=1000000,taxa_juros_mensal=8,data_emprestimo=?,
                data_primeiro_vencimento=?,dia_vencimento=? WHERE id=1''',
                ((self.today-timedelta(days=120)).isoformat(),self.due.isoformat(),self.due.day))
            db.execute("UPDATE movimentacoes_emprestimo SET valor_centavos=1000000,saldo_depois_centavos=1000000,data_movimento=? WHERE tipo='EMPRESTIMO'",((self.today-timedelta(days=120)).isoformat(),))
            self.tid=self.insert_title(db,self.due)
            self.future_ids=[self.insert_title(db,application.add_months_iso(self.due,m)) for m in [1,2]]
            db.commit()

    def tearDown(self):self.c.tearDown()

    def insert_title(self,db,due):
        return db.execute('''INSERT INTO titulos_receber(emprestimo_id,tipo,competencia,data_vencimento,
            valor_previsto_centavos,saldo_base_centavos,taxa_juros_mensal,status)
            VALUES(1,'JUROS',?,?,80000,1000000,8,?)''',
            (due.strftime('%Y-%m'),due.isoformat(),'VENCIDO' if due<self.today else 'PREVISTO')).lastrowid

    def token(self,response):
        self.assertEqual(response.status_code,200)
        match=re.search(r'name="assinatura" value="([^"]+)"',response.get_data(as_text=True))
        self.assertIsNotNone(match,response.get_data(as_text=True))
        return match.group(1)

    def row(self,tid=None):return self.c.rows('SELECT * FROM titulos_receber WHERE id=?',(tid or self.tid,))[0]

    def reschedule(self,new,*,future=False):
        data=dict(titulo_id=str(self.tid),nova_data=new.isoformat())
        if future:data['futuros']='1'
        preview=self.c.post('/receber/alterar-lote',acao='prever',**data)
        result=self.c.post('/receber/alterar-lote',acao='salvar',assinatura=self.token(preview),
            senha_confirmacao=self.c.password,motivo='Acordo de nova data',**data)
        self.assertEqual(result.status_code,302,result.get_data(as_text=True))
        return preview

    def pay(self,paydate=None):
        data=dict(data_recebimento=(paydate or self.today).isoformat(),conta_origem_id='2',conta_destino_id='1')
        preview=self.c.post(f'/receber/{self.tid}',acao='prever',**data)
        response=self.c.post(f'/receber/{self.tid}',acao='confirmar',assinatura=self.token(preview),**data)
        self.assertEqual(response.status_code,302,response.get_data(as_text=True))
        return preview

    def test_reagendar_atual_e_mudar_so_dia_dos_futuros(self):
        preview=self.reschedule(self.today,future=True)
        self.assertIn('Adicional de atraso',preview.get_data(as_text=True))
        row=self.row();self.assertEqual(row['valor_base_centavos'],80000)
        self.assertEqual(row['dias_atraso'],10)
        self.assertEqual(row['juros_atraso_centavos'],26667)
        self.assertEqual(row['valor_previsto_centavos'],106667)
        for tid in self.future_ids:
            t=self.row(tid)
            self.assertEqual(t['valor_previsto_centavos'],80000)
            self.assertEqual(t['juros_atraso_centavos'],0)
            self.assertEqual(date.fromisoformat(t['data_vencimento']).day,self.today.day)
            self.assertEqual(t['data_base_atraso'],t['data_vencimento'])
            self.assertEqual(calcular(t,date.fromisoformat(t['data_vencimento']))['juros_atraso_centavos'],0)
        self.assertEqual(self.c.rows('SELECT dia_vencimento,saldo_atual_centavos FROM emprestimos')[0][0],self.today.day)
        self.assertEqual(self.c.rows('SELECT saldo_atual_centavos FROM emprestimos')[0][0],1000000)
        with self.app.app_context():
            application.sync_receivable_titles(application.get_db(),months_ahead=4)
        for t in self.c.rows('SELECT * FROM titulos_receber WHERE id<>?',(self.tid,)):
            self.assertEqual(t['valor_previsto_centavos'],80000)

    def test_reagendar_duas_vezes_e_receber_sem_cobrar_duplo(self):
        self.reschedule(self.today-timedelta(days=5))
        self.reschedule(self.today)
        self.pay()
        row=self.row()
        self.assertEqual(row['status'],'RECEBIDO')
        self.assertEqual(row['valor_recebido_centavos'],106667)
        movement=self.c.rows("SELECT * FROM movimentacoes_emprestimo WHERE tipo='JUROS'")[0]
        self.assertEqual(movement['valor_base_centavos'],80000)
        self.assertEqual(movement['juros_atraso_centavos'],26667)
        self.assertEqual(movement['saldo_antes_centavos'],movement['saldo_depois_centavos'])

    def test_pagamento_posterior_ao_reagendamento_atualiza_adicional(self):
        self.reschedule(self.today-timedelta(days=5))
        self.assertEqual(self.row()['dias_atraso'],5)
        self.pay()
        self.assertEqual(self.row()['dias_atraso'],10)
        self.assertEqual(self.row()['valor_recebido_centavos'],106667)

    def test_data_alterada_exige_nova_confirmacao(self):
        preview=self.c.post(f'/receber/{self.tid}',acao='prever',data_recebimento=self.today.isoformat())
        response=self.c.post(f'/receber/{self.tid}',acao='confirmar',assinatura=self.token(preview),
            data_recebimento=(self.today-timedelta(days=1)).isoformat(),conta_origem_id='2',conta_destino_id='1')
        self.assertEqual(response.status_code,200)
        self.assertFalse(self.c.rows("SELECT * FROM movimentacoes_emprestimo WHERE tipo='JUROS'"))
        self.assertIn('confirme novamente',response.get_data(as_text=True))

    def test_pagamento_agrupado_calcula_cada_titulo(self):
        with self.app.app_context():
            db=application.get_db();second=self.insert_title(db,self.today-timedelta(days=40));db.commit()
        data=dict(cliente_id='1',titulo_id=[str(self.tid),str(second)],data_pagamento=self.today.isoformat(),conta_origem_id='2',conta_destino_id='1')
        preview=self.c.post('/pagamentos-integrados/novo',acao='prever',**data)
        response=self.c.post('/pagamentos-integrados/novo',acao='confirmar',assinatura=self.token(preview),**data)
        self.assertEqual(response.status_code,302,response.get_data(as_text=True))
        items=self.c.rows('SELECT dias_atraso,valor_base_centavos,juros_atraso_centavos,valor_centavos FROM pagamentos_integrados_itens ORDER BY dias_atraso')
        self.assertEqual([tuple(i) for i in items],[(10,80000,26667,106667),(40,80000,106667,186667)])
        self.assertEqual(self.c.rows('SELECT valor_total_centavos FROM pagamentos_integrados')[0][0],293334)
        self.assertEqual(self.c.rows('SELECT saldo_atual_centavos FROM emprestimos')[0][0],1000000)
        self.assertIn('Adicional de atraso',self.client.get('/pagamentos-integrados/1').get_data(as_text=True))
        for tid in self.future_ids:self.assertEqual(self.row(tid)['valor_previsto_centavos'],80000)

    def test_erro_no_segundo_item_reverte_grupo_completo(self):
        with self.app.app_context():
            db=application.get_db();second=self.insert_title(db,self.today-timedelta(days=40));db.commit()
        data=dict(cliente_id='1',titulo_id=[str(self.tid),str(second)],data_pagamento=self.today.isoformat(),conta_origem_id='2',conta_destino_id='1')
        preview=self.c.post('/pagamentos-integrados/novo',acao='prever',**data)
        original=application.aplicar_recebimento_titulo
        counter=[]
        def failing(*args,**kwargs):
            counter.append(1)
            if len(counter)==2:raise ValueError('Falha simulada no segundo item')
            return original(*args,**kwargs)
        with patch.object(application,'aplicar_recebimento_titulo',side_effect=failing):
            self.c.post('/pagamentos-integrados/novo',acao='confirmar',assinatura=self.token(preview),**data)
        self.assertFalse(self.c.rows('SELECT * FROM pagamentos_integrados'))
        self.assertFalse(self.c.rows("SELECT * FROM movimentacoes_emprestimo WHERE tipo='JUROS'"))
        self.assertEqual(self.row()['valor_previsto_centavos'],80000)

    def test_entrada_pelo_contrato_tambem_cobra_atraso(self):
        data=dict(competencia=self.due.strftime('%Y-%m'),data_movimento=self.today.isoformat(),conta_origem_id='2',conta_destino_id='1')
        preview=self.c.post('/emprestimos/1/juros',acao='prever',**data)
        response=self.c.post('/emprestimos/1/juros',acao='confirmar',assinatura=self.token(preview),**data)
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.c.rows("SELECT valor_centavos FROM movimentacoes_emprestimo WHERE tipo='JUROS'")[0][0],106667)

    def test_portal_com_atraso_e_confirmacao_sem_recalcular_ate_analise(self):
        from werkzeug.security import generate_password_hash
        from PIL import Image
        with self.app.app_context():
            db=application.get_db();db.execute("INSERT INTO clientes_acessos(cliente_id,email,senha_hash,status) VALUES(1,'cliente@example.invalid',?,'ATIVO')",(generate_password_hash('senha123456'),));db.commit()
        client=self.app.test_client();self.c.authenticate(client,portal_id=1)
        data=dict(csrf_token='csrf-test',titulo_id=str(self.tid),data_pagamento=(self.today-timedelta(days=2)).isoformat())
        preview=client.post('/portal/comprovantes/novo',data=dict(data,acao='prever'))
        stream=io.BytesIO();Image.new('RGB',(20,20),'white').save(stream,'PNG');stream.seek(0)
        response=client.post('/portal/comprovantes/novo',data=dict(data,acao='confirmar',assinatura=self.token(preview),comprovante=(stream,'prova.png')))
        self.assertEqual(response.status_code,302,response.get_data(as_text=True))
        admin=self.client.get('/comprovantes/1')
        self.c.post('/comprovantes/1/confirmar',senha_confirmacao=self.c.password,conta_origem_id='2',conta_destino_id='1',assinatura=self.token(admin))
        self.assertEqual(self.row()['dias_atraso'],8)
        self.assertEqual(self.row()['valor_recebido_centavos'],101333)

    def test_conferencia_mensal_inclui_adicional_sem_indicar_pagamento_a_maior(self):
        self.pay()
        with self.app.app_context():
            lines,_=application.conferencia_mensal_cliente(application.get_db(),1,self.due.replace(day=1),self.today)
        line=next(x for x in lines if x['competencia']==self.due.strftime('%Y-%m'))
        self.assertEqual(line['esperado_centavos'],106667)
        self.assertEqual(line['situacao_competencia'],'PAGO')

    def test_estorno_preserva_base_para_novo_recebimento(self):
        self.pay()
        mid=self.c.rows("SELECT id FROM movimentacoes_emprestimo WHERE tipo='JUROS'")[0][0]
        response=self.c.post(f'/movimentacoes/{mid}/excluir',senha_confirmacao=self.c.password,motivo_exclusao='Refazer recebimento')
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.row()['valor_base_centavos'],80000)
        self.pay()
        self.assertEqual(self.row()['valor_recebido_centavos'],106667)


class UpgradeTests(unittest.TestCase):
    def test_banco_da_versao_original_preservado(self):
        schema=Path(__file__).resolve().parent/'fixtures/schema_legacy.sql'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'antigo.db'
            with closing(sqlite3.connect(path)) as db:
                db.row_factory=sqlite3.Row
                db.execute('PRAGMA foreign_keys=ON')
                db.executescript(schema.read_text())
                db.execute("INSERT INTO clientes(nome) VALUES('Legado')")
                db.execute("INSERT INTO emprestimos(cliente_id,data_emprestimo,valor_original_centavos,saldo_atual_centavos,taxa_juros_mensal) VALUES(1,'2026-01-01',1000000,900000,8)")
                db.execute("INSERT INTO movimentacoes_emprestimo(emprestimo_id,tipo,data_movimento,valor_centavos,competencia) VALUES(1,'JUROS','2026-02-10',80000,'2026-02')")
                db.execute("INSERT INTO titulos_receber(emprestimo_id,competencia,data_vencimento,valor_previsto_centavos,valor_recebido_centavos,saldo_base_centavos,taxa_juros_mensal,status,movimentacao_id) VALUES(1,'2026-02','2026-02-01',80000,80000,1000000,8,'RECEBIDO',1)")
                db.commit()
            before=hashlib.sha256(path.read_bytes()).hexdigest()
            script=Path(__file__).resolve().parents[1]/'scripts/verificar_banco.py'
            result=subprocess.run([sys.executable,str(script),str(path)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertIn('preservados',result.stdout)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)


if __name__=='__main__':unittest.main()
