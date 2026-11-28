from django.test import SimpleTestCase
from portal.integration import ERPClient,ERPNotConfigured


class ClientSettingsTests(SimpleTestCase):
    def test_malformed_configuration_returns_controlled_error(self):
        for url in ['http://[bad','http://127.0.0.1:bad','http://127.0.0.1:0','http://127.0.0.1:99999','http://localhost/ path','http://localhost/\npath',None,12]:
            with self.subTest(url=url),self.assertRaises(ERPNotConfigured):ERPClient(url,'operator','fixture')
        for user,password in [('a:b','p'),('a\nb','p'),(12,'p'),('a',12)]:
            with self.assertRaises(ERPNotConfigured):ERPClient('http://localhost',user,password)

    def test_valid_local_prefix_and_ipv6_are_kept(self):
        for url in ['http://localhost:8045/api','http://[::1]:8045/api','https://example.invalid/api']:
            self.assertEqual(ERPClient(url,'operator','fixture').base_url,url)
