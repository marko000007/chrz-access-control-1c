from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from uuid import uuid4
from django.test import SimpleTestCase
from portal.integration import ERPClient,ERPUnavailable


class PresenceClientTests(SimpleTestCase):
    def setUp(self):
        self.client=ERPClient('http://127.0.0.1:12345','test','test')
        self.now=datetime(2026,11,23,tzinfo=timezone.utc)
        self.row={'id':str(uuid4()),'request_id':str(uuid4()),'checkpoint_id':str(uuid4()),
                  'visitor':'Visitor','checkpoint':'Point','requester_login':'owner','state':'revoked',
                  'position':'inside','starts_at':(self.now-timedelta(days=1)).isoformat(),
                  'ends_at':self.now.isoformat(),'issued_at':(self.now-timedelta(days=1)).isoformat()}
        self.report={'items':[self.row],'total':1,'revoked':1,'expired':1,'generated_at':self.now.isoformat()}

    def test_revoked_expired_inside_pass_is_kept_and_counts_are_checked(self):
        with patch.object(self.client,'request',return_value=self.report):
            report=self.client.presence_report('guard')
            self.assertEqual((report['total'],report['expired'],report['revoked']),(1,1,1))
            self.assertEqual(report['items'][0]['id'],self.row['id'])
            for key,value in [('total',0),('expired',0),('revoked',True),('generated_at','2026-11-23T00:00:00')]:
                with patch.dict(self.report,{key:value}),self.assertRaises(ERPUnavailable):
                    self.client.presence_report('guard')

    def test_outside_duplicate_and_partial_rows_are_rejected(self):
        with patch.object(self.client,'request',return_value=self.report):
            with patch.dict(self.row,{'position':'outside'}),self.assertRaises(ERPUnavailable):self.client.presence_report('guard')
            with patch.dict(self.report,{'items':[self.row,self.row],'total':2,'expired':2,'revoked':2}),self.assertRaises(ERPUnavailable):self.client.presence_report('guard')
            with patch.dict(self.report,{'items':[self.row]*1001}),self.assertRaises(ERPUnavailable):self.client.presence_report('guard')

from django.contrib.auth import get_user_model
from django.test import TestCase
from unittest.mock import Mock
import csv,io


class PresenceViewTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('presence.guard');self.client.force_login(self.user)
        self.erp=Mock();self.erp.actor.return_value={'actor':self.user.username,'role':'guard'}
        self.now=datetime(2026,11,23,tzinfo=timezone.utc)
        self.row={'id':str(uuid4()),'visitor':'=Visitor <img>','checkpoint':'  @point','state':'revoked','ends_at':self.now}
        self.erp.presence_report.return_value={'items':[self.row],'total':1,'expired':1,'revoked':1,'generated_at':self.now}
        patcher=patch('portal.permissions.get_client',return_value=self.erp);patcher.start();self.addCleanup(patcher.stop)

    def test_private_csv_preserves_snapshot_and_empty_summary(self):
        response=self.client.get('/reports/presence/',{'format':'csv'})
        self.assertIn('no-store',response['Cache-Control']);self.assertIn('private',response['Cache-Control'])
        rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig')),delimiter=';'))
        self.assertEqual((rows[1][0],rows[1][7:10]),('Итоги',['1','1','1']))
        self.assertEqual(rows[2][2],"'=Visitor <img>")
        self.assertEqual(rows[2][3],"'  @point")
        self.erp.presence_report.return_value={'items':[],'total':0,'expired':0,'revoked':0,'generated_at':self.now}
        response=self.client.get('/reports/presence/',{'format':'csv'})
        self.assertEqual(len(list(csv.reader(io.StringIO(response.content.decode('utf-8-sig')),delimiter=';'))),2)

    def test_html_escapes_text_and_requester_cannot_read_report(self):
        self.assertContains(self.client.get('/reports/presence/'),'&lt;img&gt;')
        self.erp.presence_report.reset_mock()
        self.erp.actor.return_value['role']='requester'
        self.assertEqual(self.client.get('/reports/presence/').status_code,403)
        self.erp.presence_report.assert_not_called()

    def test_filters_preserve_complete_source_count_and_csv_selection(self):
        second={**self.row,'id':str(uuid4()),'visitor':'Other','state':'active','ends_at':self.now+timedelta(hours=1)}
        self.erp.presence_report.return_value={'items':[self.row,second],'total':2,'expired':1,'revoked':1,'generated_at':self.now}
        response=self.client.get('/reports/presence/',{'state':'expired','visitor':'VISITOR'})
        self.assertEqual((response.context['report']['total'],response.context['report']['source_total']),(1,2))
        response=self.client.get('/reports/presence/',{'state':'revoked','format':'csv'})
        rows=list(csv.reader(io.StringIO(response.content.decode('utf-8-sig')),delimiter=';'))
        self.assertTrue(all(len(row)==len(rows[0]) for row in rows))
        self.assertEqual(len(rows),3);self.assertEqual(rows[1][11],'2');self.assertEqual(rows[1][-1],'revoked')
        self.erp.presence_report.reset_mock()
        self.assertEqual(self.client.get('/reports/presence/',{'state':'unknown'}).status_code,400)
        self.erp.presence_report.assert_not_called()
