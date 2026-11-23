from io import StringIO
import json
from pathlib import Path
import tempfile
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings


class LocalDemoTests(TestCase):
    def test_generated_credentials_permissions_and_repeat(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(BASE_DIR=Path(folder)):
            call_command('prepare_local_demo',stdout=StringIO())
            path=Path(folder)/'.local/demo-accounts.json'
            credentials=json.loads(path.read_text())
            self.assertEqual(len(credentials),4)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
            for name,password in credentials.items():
                user=get_user_model().objects.get(username=name)
                self.assertTrue(user.check_password(password))
                self.assertEqual(user.is_staff,name=='demo.admin')
            call_command('prepare_local_demo',stdout=StringIO())
            self.assertEqual(json.loads(path.read_text()),credentials)
            self.assertEqual(get_user_model().objects.count(),4)

    def test_existing_login_password_and_privileges_preserved(self):
        user=get_user_model().objects.create_user('demo.admin',password='existing-private')
        old=user.password
        with tempfile.TemporaryDirectory() as folder, override_settings(BASE_DIR=Path(folder)):
            call_command('prepare_local_demo',stdout=StringIO())
            user.refresh_from_db()
            self.assertEqual(user.password,old)
            self.assertFalse(user.is_staff)
            self.assertNotIn('demo.admin',json.loads((Path(folder)/'.local/demo-accounts.json').read_text()))
