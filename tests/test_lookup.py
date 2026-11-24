from uuid import uuid4
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase,Client


class LookupTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('lookup');self.client.force_login(self.user)

    def test_form_and_invalid_input_never_contact_erp(self):
        with patch('portal.permissions.get_client') as erp:
            self.assertContains(self.client.get('/lookup/'),'старых заявок')
            self.assertContains(self.client.post('/lookup/',{'kind':'request','identifier':'not-a-uuid'}),'Введите правильный UUID')
            self.assertEqual(self.client.post('/lookup/',{'kind':'https://evil.invalid','identifier':uuid4()}).status_code,200)
            erp.assert_not_called()

    def test_redirect_is_only_to_the_selected_existing_private_card(self):
        identifier=uuid4()
        for kind,part in [('request','requests'),('pass','passes')]:
            response=self.client.post('/lookup/',{'kind':kind,'identifier':str(identifier).upper()})
            self.assertEqual(response.status_code,302);self.assertEqual(response['Location'],f'/{part}/{identifier}/')
        anonymous=Client();self.assertEqual(anonymous.get('/lookup/').status_code,302)
        secured=Client(enforce_csrf_checks=True);secured.force_login(self.user)
        self.assertEqual(secured.post('/lookup/',{'kind':'pass','identifier':identifier}).status_code,403)
