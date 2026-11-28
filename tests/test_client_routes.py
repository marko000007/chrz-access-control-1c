from unittest.mock import patch
from django.test import SimpleTestCase
from portal.integration import ERPClient


class ClientRouteTests(SimpleTestCase):
    def test_unknown_and_encoded_routes_never_reach_transport(self):
        client=ERPClient('http://localhost','operator','fixture')
        with patch.object(client.opener,'open') as transport:
            for path in ['/../health','/%2e%2e/health','/health?x=1','/health#x','//host/health','/health\\x','/unknown','/health\n',None,12]:
                with self.subTest(path=path),self.assertRaises(ValueError):client.request('GET',path,'actor')
            with self.assertRaises(ValueError):client.request('GET','/health','actor',{})
            with self.assertRaises(ValueError):client.request('POST','/requests','actor',None)
            transport.assert_not_called()
