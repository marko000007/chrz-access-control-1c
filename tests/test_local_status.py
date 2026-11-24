import json,os,tempfile
from pathlib import Path
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase,Client
from portal.local_status import collect_status


class LocalStatusTests(TestCase):
    def test_file_checks_never_expose_credentials_or_accept_outside_base(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'.local').mkdir()
            config=root/'.local/local-erp.json'
            config.write_text(json.dumps({'base_name':'development','username':'SECRET_LOGIN','password':'SECRET_PASSWORD','port':0}))
            base=root/'.local/1c/development';base.mkdir(parents=True);(base/'1Cv8.1CD').touch()
            with patch.dict(os.environ,{'ONE_C_ALLOW_GUI':'0'}),patch('subprocess.run') as launch:
                result=collect_status(root);self.assertTrue(result['configuration_valid']);self.assertTrue(result['database_file_exists'])
                self.assertFalse(result['gui_enabled']);self.assertFalse(result['native_connection_tested']);launch.assert_not_called()
            self.assertNotIn('SECRET',json.dumps(result))
            config.write_text(json.dumps({'base_name':'../../outside','username':'a','password':'b','port':0}))
            self.assertFalse(collect_status(root)['configuration_valid'])

    def test_only_staff_can_view_and_no_rpc_is_performed(self):
        staff=get_user_model().objects.create_user('local-operator',is_staff=True)
        self.client.force_login(staff)
        with patch('portal.permissions.get_client') as erp,patch('subprocess.run') as launch:
            response=self.client.get('/local/status/')
            self.assertContains(response,'Подключение к1С здесь не проверялось')
            self.assertEqual(response['Cache-Control'],'private, no-store');erp.assert_not_called();launch.assert_not_called()
        normal=get_user_model().objects.create_user('local-ordinary');self.client.force_login(normal)
        self.assertEqual(self.client.get('/local/status/').status_code,403)
        self.assertEqual(Client().get('/local/status/').status_code,302)
