import json
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from unittest.mock import patch
from django.test import SimpleTestCase
from portal.integration import ERPClient,ERPUnavailable
from portal.protocol import strict_json


class WireHandler(BaseHTTPRequestHandler):
    status=200
    payload=b'{"api_version":1,"data":{"system":"1c-enterprise"}}'
    def log_message(self,*args):pass
    def do_GET(self):
        self.send_response(self.status);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(self.payload)


class JSONContractTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass();cls.server=ThreadingHTTPServer(('127.0.0.1',0),WireHandler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();super().tearDownClass()

    def test_ambiguous_nonfinite_deep_and_non_utf8_json_are_rejected(self):
        for raw in [b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}',b'{"x":1e999}', '['*2000+']'*2000,b'\xff']:
            with self.subTest(raw=str(raw)[:50]),self.assertRaises((ValueError,UnicodeError)):strict_json(raw)
        self.assertEqual(strict_json(b'\xef\xbb\xbf{"x":1}'),{'x':1})

    def test_real_http_requires_final_status_and_unambiguous_envelope(self):
        client=ERPClient(f'http://127.0.0.1:{self.server.server_port}','fixture','fixture')
        cases=[(202,b'{"api_version":1,"data":{"system":"1c-enterprise"}}'),
            (200,b'{"api_version":1,"data":{"system":"1c-enterprise"},"error":"failed"}'),
            (200,b'{"api_version":1,"api_version":1,"data":{}}'),
            (200,b'{"api_version":1,"data":{"value":NaN}}')]
        for status,payload in cases:
            WireHandler.status=status;WireHandler.payload=payload
            with self.subTest(status=status,payload=payload),self.assertRaises(ERPUnavailable):client.health('actor')
        WireHandler.status=200;WireHandler.payload=b'{"api_version":1,"data":{"system":"1c-enterprise"},"error":""}'
        self.assertEqual(client.health('actor')['system'],'1c-enterprise')

    def test_malformed_role_returns_controlled_unavailable(self):
        client=ERPClient('http://127.0.0.1:12345','fixture','fixture')
        for value in [[],{},None,True]:
            with patch.object(client,'request',return_value={'actor':'actor','role':value}),self.assertRaises(ERPUnavailable):client.actor('actor')
