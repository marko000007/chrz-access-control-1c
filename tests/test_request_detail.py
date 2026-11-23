from datetime import timedelta
import uuid
from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from portal.integration import ERPClient, ERPMissing


class RequestCardTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('card.requester');self.client.force_login(self.user)
        self.erp=Mock();self.erp.actor.return_value={'actor':self.user.username,'role':'requester'}
        self.identifier=str(uuid.uuid4());now=timezone.now()
        self.card={'id':self.identifier,'requester_login':self.user.username,'visitor':'<script>','host':'Сотрудник',
            'purpose':'Учебное посещение','checkpoint':'Проходная','status':'rejected','starts_at':now,'ends_at':now+timedelta(hours=1),
            'created_at':now,'decision_at':now,'decision_by':'approver','decision_reason':'<b>Отказ по учебной причине</b>'}
        self.erp.request_detail.return_value=self.card
        self.patch=patch('portal.permissions.get_client',return_value=self.erp);self.patch.start();self.addCleanup(self.patch.stop)

    def test_card_displays_reason_and_escapes_without_mutation(self):
        response=self.client.get(f'/requests/{self.identifier}/')
        self.assertContains(response,'Отклонена');self.assertContains(response,'&lt;script&gt;')
        self.assertContains(response,'&lt;b&gt;Отказ по учебной причине&lt;/b&gt;')
        self.erp.decide_request.assert_not_called()
        self.erp.request_detail.side_effect=ERPMissing()
        self.assertEqual(self.client.get(f'/requests/{self.identifier}/').status_code,404)

    def test_client_validates_dates_scope_and_backend_boundary(self):
        self.card['requester_login']='someone-else'
        response=self.client.get(f'/requests/{self.identifier}/');self.assertEqual(response.status_code,403)
        self.assertNotContains(response,'Учебное посещение',status_code=403)
        client=ERPClient('http://127.0.0.1:12345','test','test')
        wire={key:value.isoformat() if hasattr(value,'isoformat') else value for key,value in self.card.items()}
        with patch.object(client,'request',return_value={'item':wire}):
            self.assertEqual(client.request_detail('actor',self.identifier)['visitor'],'<script>')
            wire['decision_at']=None
            from portal.integration import ERPUnavailable
            with self.assertRaises(ERPUnavailable):client.request_detail('actor',self.identifier)
