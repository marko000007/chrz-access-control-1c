import csv,io
from datetime import datetime,timezone,timedelta
from uuid import uuid4
from unittest.mock import Mock,patch
from django.contrib.auth import get_user_model
from django.test import TestCase


class ReportFilterTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('filtered-report');self.client.force_login(self.user)
        self.erp=Mock();self.erp.actor.return_value={'actor':self.user.username,'role':'guard'}
        self.now=datetime(2026,11,24,tzinfo=timezone.utc)
        def row(visitor,point,actor,direction):return {'id':str(uuid4()),'pass_id':str(uuid4()),'visitor':visitor,'checkpoint':point,
            'actor':actor,'direction':direction,'requester_login':'requester','occurred_at':self.now}
        self.report={'items':[row('Иван Петров','Проходная1','Guard.A','in'),row('Мария','Проходная2','Guard.B','out')],
            'starts_at':self.now,'ends_at':self.now+timedelta(days=1),'generated_at':self.now,'count_in':1,'count_out':1}
        self.erp.movement_report.return_value=self.report
        patcher=patch('portal.permissions.get_client',return_value=self.erp);patcher.start();self.addCleanup(patcher.stop)
        self.values={'start':'2026-11-24','end':'2026-11-24'}

    def test_filters_preserve_source_counts_and_share_same_json_snapshot(self):
        response=self.client.get('/reports/movements/',{**self.values,'visitor':'ИВАН','checkpoint':'ная1','actor':'guard.a','direction':'in','format':'json'})
        self.assertEqual(response.status_code,200)
        data=response.json();self.assertEqual((data['source_count'],data['count_in'],data['count_out'],len(data['items'])),(2,1,0,1))
        self.assertEqual(data['items'][0]['visitor'],'Иван Петров');self.assertEqual(data['filters']['visitor'],'ИВАН')
        self.assertEqual(response['Cache-Control'],'private, no-store')
        self.assertEqual(self.report['count_out'],1);self.assertEqual(len(self.report['items']),2)
        self.assertEqual(set(self.erp.movement_report.call_args.kwargs),{'start','end'})

    def test_csv_and_export_links_keep_filters_and_empty_result(self):
        values={**self.values,'direction':'out','visitor':'Мария'}
        response=self.client.get('/reports/movements/',values)
        self.assertContains(response,'visitor=%D0%9C%D0%B0%D1%80%D0%B8%D1%8F')
        response=self.client.get('/reports/movements/',{**values,'format':'csv'})
        rows=list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig')),delimiter=';'))
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['Направление'],'Выход')
        response=self.client.get('/reports/movements/',{**self.values,'visitor':'No match','format':'json'})
        self.assertEqual(response.json()['items'],[]);self.assertEqual(response.json()['source_count'],2)

    def test_invalid_filter_never_reaches_report_and_role_is_checked(self):
        self.assertEqual(self.client.get('/reports/movements/',{**self.values,'direction':'all','format':'json'}).status_code,400)
        self.erp.movement_report.assert_not_called()
        self.erp.actor.return_value['role']='requester'
        self.assertEqual(self.client.get('/reports/movements/',self.values).status_code,403)
