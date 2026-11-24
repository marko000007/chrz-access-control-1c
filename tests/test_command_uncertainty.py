from types import SimpleNamespace
from unittest.mock import Mock
from django.contrib.auth import get_user_model
from django.test import TestCase
from portal.commands import command_state,send_command
from portal.integration import ERPUnavailable,ERPForbidden,ERPConflict,ERPRejected
from portal.models import PendingCommand


class UncertainCommandTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('uncertain-command')
        self.request=SimpleNamespace(user=self.user)
        self.context='visitor:create';self.payload={'name':'Visitor','company':'Demo'}
        self.key=command_state(self.request,self.context)['key']

    def test_permission_change_after_lost_response_preserves_original_key(self):
        uncertain=Mock(side_effect=ERPUnavailable('lost'))
        with self.assertRaises(ERPUnavailable):send_command(self.request,self.context,self.key,self.payload,uncertain)
        denied=Mock(side_effect=ERPForbidden('role revoked'))
        with self.assertRaises(ERPForbidden):send_command(self.request,self.context,self.key,self.payload,denied)
        self.assertEqual(command_state(self.request,self.context),{'key':self.key,'payload':self.payload})
        confirmed=Mock(return_value={'id':'same-native-result'})
        self.assertEqual(send_command(self.request,self.context,self.key,self.payload,confirmed),{'id':'same-native-result'})
        for callback in [uncertain,denied,confirmed]:self.assertEqual(callback.call_args.args,(self.key,self.payload))
        self.assertFalse(PendingCommand.objects.filter(owner=self.user,context=self.context).exists())

    def test_conflict_after_unknown_result_is_retained_for_resolution(self):
        PendingCommand.objects.filter(owner=self.user,context=self.context).update(payload=self.payload)
        with self.assertRaises(ERPConflict):send_command(self.request,self.context,self.key,self.payload,Mock(side_effect=ERPConflict('conflict')))
        self.assertEqual(command_state(self.request,self.context)['key'],self.key)
        self.assertEqual(PendingCommand.objects.get().payload,self.payload)

    def test_fresh_confirmed_refusal_does_not_leave_an_uncertain_command(self):
        for error in [ERPForbidden('denied'),ERPRejected('rejected')]:
            key=command_state(self.request,self.context)['key']
            with self.assertRaises(type(error)):send_command(self.request,self.context,key,self.payload,Mock(side_effect=error))
            self.assertFalse(PendingCommand.objects.filter(owner=self.user,context=self.context).exists())
