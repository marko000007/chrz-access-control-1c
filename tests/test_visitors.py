import uuid
from unittest.mock import Mock,patch
from django.contrib.auth import get_user_model
from django.test import TestCase,Client
from portal.models import PendingCommand
from portal.integration import ERPUnavailable


class VisitorCatalogTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('visitor.admin');self.client.force_login(self.user)
        self.erp=Mock();self.erp.actor.return_value={'actor':self.user.username,'role':'admin'}
        self.erp.references.return_value={'visitors':[{'id':str(uuid.uuid4()),'name':'<img>','company':'<b>Организация</b>'}]}
        self.patch=patch('portal.permissions.get_client',return_value=self.erp);self.patch.start();self.addCleanup(self.patch.stop)

    def test_uncertain_catalog_command_replays_without_changed_content(self):
        response=self.client.get('/visitors/new/');key=response.context['form']['command_key'].value()
        self.erp.create_visitor.assert_not_called()
        data={'name':'Учебный посетитель','company':'Учебная организация','command_key':key}
        self.erp.create_visitor.side_effect=ERPUnavailable('Ответ потерян')
        self.assertEqual(self.client.post('/visitors/new/',data).status_code,200)
        self.assertTrue(PendingCommand.objects.filter(owner=self.user,payload__isnull=False).exists())
        self.assertEqual(self.client.post('/visitors/new/',{**data,'company':'Изменение'}).status_code,200)
        self.assertEqual(self.erp.create_visitor.call_count,1)
        self.erp.create_visitor.side_effect=None
        self.assertEqual(self.client.post('/visitors/new/',data).status_code,302)
        self.assertFalse(PendingCommand.objects.filter(owner=self.user,payload__isnull=False).exists())
        self.assertEqual(self.erp.create_visitor.call_count,2)

    def test_roles_private_fields_and_csrf(self):
        response=self.client.get('/visitors/');self.assertContains(response,'&lt;img&gt;');self.assertContains(response,'&lt;b&gt;Организация&lt;/b&gt;')
        self.erp.actor.return_value['role']='requester';self.assertEqual(self.client.get('/visitors/new/').status_code,403)
        self.erp.actor.return_value['role']='admin'
        client=Client(enforce_csrf_checks=True);client.force_login(self.user)
        self.assertEqual(client.post('/visitors/new/',{}).status_code,403)
        self.erp.create_visitor.assert_not_called()
