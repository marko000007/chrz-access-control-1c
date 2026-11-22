from unittest.mock import patch,Mock
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import TestCase,RequestFactory
from portal.integration import ERPUnavailable
from portal.permissions import erp_roles


class PermissionTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('operator',is_staff=True)
        self.client.force_login(self.user)

    def test_backend_role_is_authoritative_and_actor_cannot_be_spoofed(self):
        remote=Mock();remote.actor.return_value={'actor':'operator','role':'guard'}
        with patch('portal.permissions.get_client',return_value=remote):
            response=self.client.get('/workspace/',{'actor':'administrator','role':'admin'})
        self.assertContains(response,'Сотрудник проходной')
        remote.actor.assert_called_once_with('operator')

    def test_unavailable_backend_does_not_grant_local_staff_access(self):
        with patch('portal.permissions.get_client',side_effect=ERPUnavailable('Нет связи')):
            self.assertEqual(self.client.get('/workspace/').status_code,503)

    def test_wrong_role_is_denied_before_view_runs(self):
        request=RequestFactory().get('/gate/');request.user=self.user
        remote=Mock();remote.actor.return_value={'actor':'operator','role':'requester'}
        view=Mock(return_value=HttpResponse('secret'))
        with patch('portal.permissions.get_client',return_value=remote),self.assertRaises(PermissionDenied):
            erp_roles('guard')(view)(request)
        view.assert_not_called()
