from datetime import date, datetime, timezone, timedelta
import uuid
from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from portal.integration import ERPClient, ERPUnavailable, ERPRejected
from portal.reports import ReportPeriod


class MovementReportTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('report.guard');self.client.force_login(self.user)
        self.erp=Mock();self.erp.actor.return_value={'actor':self.user.username,'role':'guard'}
        self.start=datetime(2026,11,23,tzinfo=timezone.utc)
        self.row={'id':str(uuid.uuid4()),'pass_id':str(uuid.uuid4()),'visitor':'<img>','checkpoint':'Точка',
            'requester_login':'requester','direction':'in','actor':self.user.username,'occurred_at':self.start}
        self.report={'items':[self.row],'starts_at':self.start,'ends_at':self.start+timedelta(days=1),
            'generated_at':self.start,'count_in':1,'count_out':0}
        self.erp.movement_report.return_value=self.report
        self.patch=patch('portal.permissions.get_client',return_value=self.erp);self.patch.start();self.addCleanup(self.patch.stop)

    def test_role_period_rendering_and_confirmed_rejection(self):
        response=self.client.get('/reports/movements/',{'start':'2026-11-23','end':'2026-11-23'})
        self.assertContains(response,'Входов: 1');self.assertContains(response,'&lt;img&gt;')
        self.erp.movement_report.reset_mock()
        response=self.client.get('/reports/movements/',{'start':'2026-11-23','end':'2026-12-24'})
        self.erp.movement_report.assert_not_called();self.assertContains(response,'Выберите от1 до31')
        self.erp.actor.return_value['role']='requester'
        self.assertEqual(self.client.get('/reports/movements/').status_code,403)
        self.erp.actor.return_value['role']='guard';self.erp.movement_report.side_effect=ERPRejected('Сократите период')
        self.assertContains(self.client.get('/reports/movements/'),'Сократите период')

    def test_client_rejects_inconsistent_counts_outside_rows_and_partial_limit(self):
        client=ERPClient('http://127.0.0.1:12345','test','test')
        wire={key:(value.isoformat() if isinstance(value,datetime) else value) for key,value in self.report.items()}
        wire['items']=[{**self.row,'occurred_at':self.start.isoformat()}]
        with patch.object(client,'request',return_value=wire):
            result=client.movement_report('actor',date(2026,11,23),date(2026,11,23));self.assertEqual(result['count_in'],1)
            wire['count_in']=2
            with self.assertRaises(ERPUnavailable):client.movement_report('actor',date(2026,11,23),date(2026,11,23))
            wire['count_in']=1;wire['items'][0]['occurred_at']=(self.start-timedelta(seconds=1)).isoformat()
            with self.assertRaises(ERPUnavailable):client.movement_report('actor',date(2026,11,23),date(2026,11,23))
            wire['items']*=1001
            with self.assertRaises(ERPUnavailable):client.movement_report('actor',date(2026,11,23),date(2026,11,23))

    def test_private_csv_roundtrip_and_formula_guard(self):
        import csv, io
        self.row['visitor']='=1+1';self.row['checkpoint']='  @command';self.row['actor']='\tformula'
        response=self.client.get('/reports/movements/',{'start':'2026-11-23','end':'2026-11-23','format':'csv'})
        self.assertEqual(response.status_code,200);self.assertIn('no-store',response['Cache-Control']);self.assertIn('private',response['Cache-Control'])
        rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig')),delimiter=';'))
        self.assertEqual(rows[1][3],"'=1+1");self.assertEqual(rows[1][4],"'  @command");self.assertEqual(rows[1][5],"'\tformula")
        self.assertEqual(len(rows),2);self.assertIn('+00:00',rows[1][1])
        self.erp.movement_report.assert_called_once_with(self.user.username,start=date(2026,11,23),end=date(2026,11,23))
        self.assertEqual(self.client.get('/reports/movements/',{'format':'csv'}).status_code,400)
