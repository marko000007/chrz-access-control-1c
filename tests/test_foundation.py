from django.contrib.auth import get_user_model
from django.test import TestCase,Client


class FoundationTests(TestCase):
    def test_private_cabinet_requires_login_and_keeps_separate_cookies(self):
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertEqual(self.client.get('/dashboard/').status_code,302)
        user=get_user_model().objects.create_user('operator')
        self.client.force_login(user)
        self.assertContains(self.client.get('/dashboard/'),'operator')
        self.assertIn('chrz_portal_session',self.client.cookies)
        self.assertEqual(self.client.get('/accounts/logout/').status_code,405)

    def test_login_post_requires_csrf(self):
        self.assertEqual(Client(enforce_csrf_checks=True).post('/accounts/login/',{}).status_code,403)
