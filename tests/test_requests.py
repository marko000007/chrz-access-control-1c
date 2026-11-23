import uuid
from datetime import timedelta
from unittest.mock import Mock,patch
from django.contrib.auth import get_user_model
from django.test import TestCase,Client
from django.utils import timezone
from portal.integration import ERPUnavailable,ERPForbidden


class RequestPortalTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('requester')
        self.client.force_login(self.user)
        self.remote=Mock()
        self.remote.actor.return_value={'actor':'requester','role':'requester'}
        self.identifiers=[str(uuid.uuid4()) for _ in range(4)]
        self.remote.references.return_value={kind:[{'id':identifier,'name':'Учебная запись'}] for kind,identifier in zip(['visitors','employees','checkpoints','purposes'],self.identifiers)}
        self.remote.create_request.return_value={'id':str(uuid.uuid4()),'status':'submitted'}
        self.remote.requests.return_value=[]
        patcher=patch('portal.permissions.get_client',return_value=self.remote);patcher.start();self.addCleanup(patcher.stop)
        self.client.get('/requests/new/')
        self.key=self.client.get('/requests/new/').context['form']['command_key'].value()
        date=(timezone.localdate()+timedelta(days=1)).isoformat()
        self.payload=dict(zip(['visitor_id','host_id','checkpoint_id','purpose_id'],self.identifiers))
        self.payload.update(starts_at=date+'T10:00',ends_at=date+'T11:00',command_key=self.key)

    def test_creation_uses_server_actor_and_invalid_fields_never_reach_backend(self):
        self.assertEqual(self.client.post('/requests/new/',{**self.payload,'visitor_id':str(uuid.uuid4())}).status_code,400)
        self.assertEqual(self.client.post('/requests/new/',{**self.payload,'ends_at':self.payload['starts_at']}).status_code,400)
        self.remote.create_request.assert_not_called()
        self.assertEqual(self.client.post('/requests/new/',{**self.payload,'actor':'admin','status':'approved'}).status_code,302)
        actor,payload,key=self.remote.create_request.call_args.args
        self.assertEqual(actor,'requester');self.assertEqual(key,self.key)
        self.assertNotIn('actor',payload);self.assertNotIn('status',payload)
        self.assertNotEqual(self.client.get('/requests/new/').context['form']['command_key'].value(),self.key)

    def test_uncertain_result_keeps_same_command_and_rejects_changed_payload(self):
        self.remote.create_request.side_effect=[ERPUnavailable('Ответ не получен'),{'id':str(uuid.uuid4()),'status':'submitted'}]
        self.assertEqual(self.client.post('/requests/new/',self.payload).status_code,503)
        self.assertEqual(self.client.get('/requests/new/').context['form']['command_key'].value(),self.key)
        self.assertEqual(self.client.post('/requests/new/',{**self.payload,'ends_at':self.payload['ends_at'].replace('11:00','12:00')}).status_code,400)
        self.assertEqual(self.remote.create_request.call_count,1)
        self.assertEqual(self.client.post('/requests/new/',self.payload).status_code,302)
        self.assertEqual(self.remote.create_request.call_args_list[0].args,self.remote.create_request.call_args_list[1].args)
        self.assertEqual(self.client.post('/requests/new/',self.payload).status_code,400)
        self.assertEqual(self.remote.create_request.call_count,2)

    def test_requester_does_not_render_foreign_rows_and_guard_cannot_create(self):
        self.remote.requests.return_value=[{'requester_login':'another','visitor':'SECRET VISITOR'}]
        response=self.client.get('/requests/')
        self.assertEqual(response.status_code,503)
        self.assertNotContains(response,'SECRET VISITOR',status_code=503)
        self.remote.actor.return_value={'actor':'requester','role':'guard'}
        self.assertEqual(self.client.get('/requests/new/').status_code,403)

    def test_revocation_at_write_and_csrf_are_enforced(self):
        self.remote.create_request.side_effect=ERPForbidden('Отозвано')
        self.assertEqual(self.client.post('/requests/new/',self.payload).status_code,403)
        client=Client(enforce_csrf_checks=True);client.force_login(self.user)
        self.assertEqual(client.post('/requests/new/',self.payload).status_code,403)
