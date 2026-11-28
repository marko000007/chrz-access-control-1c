from datetime import timedelta
import uuid
from unittest.mock import Mock,patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from portal.integration import ERPClient,ERPUnavailable,ERPMissing


class PassCardTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('pass.requester');self.client.force_login(self.user)
        self.erp=Mock();self.erp.actor.return_value={'actor':self.user.username,'role':'requester'}
        self.identifier=str(uuid.uuid4());now=timezone.now()
        self.card={'id':self.identifier,'request_id':str(uuid.uuid4()),'checkpoint_id':str(uuid.uuid4()),'visitor':'<img>',
            'checkpoint':'Точка','host':'Принимающий','purpose':'Учебное посещение','requester_login':self.user.username,
            'state':'revoked','position':'outside','starts_at':now-timedelta(hours=1),'ends_at':now+timedelta(hours=1),
            'issued_at':now-timedelta(minutes=30),'issued_by':'guard','revoked_at':now,'revoked_by':'guard',
            'revoke_reason':'<script>Учебный отзыв</script>','snapshot_at':now}
        self.erp.pass_detail.return_value=self.card
        self.patch=patch('portal.permissions.get_client',return_value=self.erp);self.patch.start();self.addCleanup(self.patch.stop)

    def test_card_print_snapshot_and_private_scope(self):
        response=self.client.get(f'/passes/{self.identifier}/')
        self.assertContains(response,'Отозван');self.assertContains(response,'Распечатать сведения')
        self.assertContains(response,'&lt;script&gt;Учебный отзыв&lt;/script&gt;')
        self.erp.movement.assert_not_called();self.erp.revoke_pass.assert_not_called()
        self.card['requester_login']='another'
        self.assertEqual(self.client.get(f'/passes/{self.identifier}/').status_code,403)
        self.erp.pass_detail.side_effect=ERPMissing()
        self.assertEqual(self.client.get(f'/passes/{self.identifier}/').status_code,404)

    def test_client_rejects_inconsistent_revocation_snapshot(self):
        wire={key:(value.isoformat() if hasattr(value,'isoformat') else value) for key,value in self.card.items()}
        client=ERPClient('http://127.0.0.1:12345','test','test')
        with patch.object(client,'request',return_value={'item':wire}):
            self.assertEqual(client.pass_detail('actor',self.identifier)['state'],'revoked')
            wire['revoked_at']=None
            with self.assertRaises(ERPUnavailable):client.pass_detail('actor',self.identifier)

    def test_revocation_must_fit_snapshot_and_have_author_and_reason(self):
        client=ERPClient('http://127.0.0.1:12345','fixture','fixture')
        wire={key:value.isoformat() if hasattr(value,'isoformat') else value for key,value in self.card.items()}
        for changes in [{'revoked_by':''},{'revoke_reason':' '},
            {'revoked_at':(self.card['issued_at']-timedelta(seconds=1)).isoformat()},
            {'snapshot_at':(self.card['revoked_at']-timedelta(seconds=1)).isoformat()},
            {'issued_at':(self.card['snapshot_at']+timedelta(seconds=1)).isoformat()}]:
            with patch.object(client,'request',return_value={'item':{**wire,**changes}}),self.assertRaises(ERPUnavailable):
                client.pass_detail('actor',self.identifier)
