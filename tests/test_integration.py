import json
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from django.test import SimpleTestCase
from portal.integration import ERPClient,ERPNotConfigured,ERPUnavailable,ERPForbidden


class Handler(BaseHTTPRequestHandler):
    mode='ok'
    observed={}
    def log_message(self,*args):pass
    def do_GET(self):
        type(self).observed=dict(self.headers)
        if self.mode=='redirect':
            self.send_response(302);self.send_header('Location','https://example.invalid/steal');self.end_headers();return
        if self.mode=='forbidden':
            self.send_response(403);self.end_headers();return
        payload=json.dumps({'api_version':1,'data':{'system':'1c-enterprise'}}).encode() if self.mode=='ok' else b'not JSON'
        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(payload)


class IntegrationTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass();cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}/hs/access/v1'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();super().tearDownClass()

    def test_real_http_contract_and_actor_header(self):
        Handler.mode='ok'
        client=ERPClient(self.url,'test-user','test-password')
        self.assertEqual(client.health('Оператор')['system'],'1c-enterprise')
        self.assertTrue(Handler.observed['Authorization'].startswith('Basic '))
        self.assertNotEqual(Handler.observed['X-Portal-Actor'],'Оператор')

    def test_redirect_errors_and_bad_json_fail_closed(self):
        client=ERPClient(self.url,'test-user','test-password')
        for mode,error in [('redirect',ERPUnavailable),('invalid',ERPUnavailable),('forbidden',ERPForbidden)]:
            Handler.mode=mode
            with self.assertRaises(error):client.health('operator')

    def test_remote_plain_http_and_embedded_credentials_are_rejected(self):
        for url in ['http://remote.example/hs/access','https://user:password@example.com/hs/access','https://example.com/x?secret=x']:
            with self.assertRaises(ERPNotConfigured):ERPClient(url,'test','test')
