from django.contrib.auth import get_user_model
from django.test import TestCase


class PrivateCacheTests(TestCase):
    def test_private_pages_login_and_logout_cannot_be_cached(self):
        self.assertIn('no-store',self.client.get('/accounts/login/')['Cache-Control'])
        user=get_user_model().objects.create_user('cache-operator');self.client.force_login(user)
        for path in ['/pending/','/pending/export.json','/lookup/']:
            response=self.client.get(path)
            self.assertIn('private',response['Cache-Control']);self.assertIn('no-store',response['Cache-Control'])
            self.assertIn('Cookie',response['Vary'])
        self.assertIn('no-store',self.client.post('/accounts/logout/')['Cache-Control'])
        self.assertEqual(self.client.get('/pending/').status_code,302)
