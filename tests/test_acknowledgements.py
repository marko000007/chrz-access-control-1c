from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from portal.commands import command_state,send_command
from portal.integration import ERPClient,ERPUnavailable
from portal.models import PendingCommand


class AcknowledgementTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('ack-owner')
        self.request=SimpleNamespace(user=self.user)
        self.erp=ERPClient('http://127.0.0.1:12345','fixture','fixture')
        self.identifier=str(uuid4());self.other=str(uuid4())

    def test_wrong_revocation_ack_keeps_frozen_command_for_safe_retry(self):
        context='pass:'+self.identifier+':revoke';state=command_state(self.request,context)
        payload={'id':self.identifier,'reason':'Учебный отзыв'}
        callback=lambda key,body:self.erp.revoke_pass(self.user.username,self.identifier,body['reason'],key)
        with patch.object(self.erp,'request',return_value={'id':self.other,'state':'revoked','position':'inside'}):
            with self.assertRaises(ERPUnavailable):send_command(self.request,context,state['key'],payload,callback)
        self.assertEqual(command_state(self.request,context),{'key':state['key'],'payload':payload})
        with patch.object(self.erp,'request',return_value={'id':self.identifier,'state':'revoked','position':'inside'}):
            self.assertEqual(send_command(self.request,context,state['key'],payload,callback)['id'],self.identifier)
        self.assertFalse(PendingCommand.objects.exists())

    def test_nil_and_malformed_identifiers_are_not_confirmed(self):
        for identifier in ['00000000-0000-0000-0000-000000000000','bad',None,1]:
            with patch.object(self.erp,'request',return_value={'id':identifier,'status':'submitted'}):
                with self.assertRaises(ERPUnavailable):self.erp.create_request('actor',{},str(uuid4()))
            with patch.object(self.erp,'request',return_value={'id':identifier,'state':'active','position':'outside'}):
                with self.assertRaises(ERPUnavailable):self.erp.issue_pass('actor',self.identifier,str(uuid4()))

    def test_duplicate_request_rows_and_nil_reference_are_rejected(self):
        row={'id':self.identifier,'visitor':'Fixture','requester_login':'actor','status':'submitted',
            'starts_at':'2026-11-24T08:00:00+00:00','ends_at':'2026-11-24T09:00:00+00:00'}
        with patch.object(self.erp,'request',return_value={'items':[row,row]}):
            with self.assertRaises(ERPUnavailable):self.erp.requests('actor')
        refs={kind:[] for kind in ['visitors','employees','checkpoints','purposes']}
        refs['visitors']=[{'id':'00000000-0000-0000-0000-000000000000','name':'Fixture'}]
        with patch.object(self.erp,'request',return_value=refs):
            with self.assertRaises(ERPUnavailable):self.erp.references('actor')
