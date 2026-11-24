import base64
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid
from portal.local_gateway import create_server, OneCRuntime, LocalERPError


class GatewayTransportTests(unittest.TestCase):
    """Transport tests use a stub; actual 1C evidence is produced by verify_erp.py."""
    def setUp(self):
        self.runtime=Mock()
        self.runtime.invoke.return_value=(200,{'api_version':1,'data':{'system':'1c-enterprise'}})
        self.server=create_server(self.runtime,'portal','private-test-password')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
        self.headers={'Authorization':'Basic '+base64.b64encode(b'portal:private-test-password').decode(),
            'X-Portal-Actor':base64.b64encode('Тестовый'.encode()).decode(),'Content-Type':'application/json'}

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)

    def test_exact_actor_body_and_command_key_forwarded(self):
        body=b'{"reason": "x", "id": "y"}'
        key=str(uuid.uuid4())
        with urlopen(Request(self.url+'/requests',data=body,headers={**self.headers,'Idempotency-Key':key}),timeout=3) as response:
            self.assertEqual(response.status,200)
        self.assertEqual(self.runtime.invoke.call_args.args[0],{'method':'POST','path':'/requests','actor':'Тестовый','body':body.decode(),'key':key})

    def test_auth_origin_host_route_and_key_rejected_before_runtime(self):
        for path,headers,data,code in [('/health',{'Authorization':'bad'},None,401),
            ('/health',{'Origin':'https://foreign.invalid'},None,403),
            ('/health',{'Host':'foreign.invalid'},None,403),
            ('/unknown',{},None,404),('/requests',{},b'{}',400)]:
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(self.url+path,headers={**self.headers,**headers},data=data),timeout=3)
            self.assertEqual(caught.exception.code,code);caught.exception.close()
        self.runtime.invoke.assert_not_called()

    def test_runtime_failure_is_generic_and_no_credentials_in_reply(self):
        self.runtime.invoke.side_effect=LocalERPError('private diagnostic')
        with self.assertRaises(HTTPError) as caught:
            urlopen(Request(self.url+'/health',headers=self.headers),timeout=3)
        self.assertEqual(caught.exception.code,503)
        content=caught.exception.read();caught.exception.close()
        self.assertNotIn(b'private',content)


class RuntimeTransportTests(unittest.TestCase):
    def test_fixed_private_directory_correlation_and_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=root/'.local/1c/qa-test';base.mkdir(parents=True);(base/'1Cv8.1CD').touch()
            binary=root/'binary';binary.touch()
            runtime=OneCRuntime('qa-test',root,binary,allow_gui=True)
            def execute(*args,**kwargs):
                payload=json.loads((runtime.directory/'request.json').read_text())
                (runtime.directory/'response.json').write_text(json.dumps({'request_id':payload['request_id'],'status':200,'result':{'api_version':1,'data':{}}}))
                return Mock(returncode=0)
            with patch('portal.local_gateway.subprocess.run',side_effect=execute):
                self.assertEqual(runtime.invoke({'method':'GET','path':'/health','actor':'a'})[0],200)
            self.assertFalse((runtime.directory/'request.json').exists())
            self.assertFalse((runtime.directory/'response.json').exists())
            self.assertEqual(runtime.directory.stat().st_mode & 0o777,0o700)
            with self.assertRaises(LocalERPError):OneCRuntime('../outside',root,binary)
