import math
from types import SimpleNamespace
from unittest.mock import Mock
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied,ValidationError
from django.test import TestCase
from portal.commands import command_state,send_command
from portal.integration import ERPUnavailable
from portal.models import PendingCommand


class CommandStorageTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('command-storage')
        self.request=SimpleNamespace(user=self.user)

    def test_capacity_preserves_every_draft_and_existing_form_remains_usable(self):
        keys=[command_state(self.request,f'draft:{n}')['key'] for n in range(20)]
        with self.assertRaises(ValidationError):command_state(self.request,'overflow')
        self.assertEqual(set(str(key) for key in PendingCommand.objects.values_list('key',flat=True)),set(keys))
        self.assertEqual(command_state(self.request,'draft:0')['key'],keys[0])

    def test_disabled_user_cannot_create_or_freeze_command(self):
        state=command_state(self.request,'sample')
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):command_state(self.request,'another')
        callback=Mock()
        with self.assertRaises(PermissionDenied):send_command(self.request,'sample',state['key'],{'x':1},callback)
        callback.assert_not_called();self.assertIsNone(PendingCommand.objects.get().payload)

    def test_replay_uses_original_order_and_bool_is_not_integer(self):
        state=command_state(self.request,'sample');original={'z':True,'a':'first'}
        def uncertain(key,payload):raise ERPUnavailable('Lost')
        with self.assertRaises(ERPUnavailable):send_command(self.request,'sample',state['key'],original,uncertain)
        callback=Mock(return_value={'ok':True})
        with self.assertRaises(ValidationError):send_command(self.request,'sample',state['key'],{'a':'first','z':1},callback)
        callback.assert_not_called()
        send_command(self.request,'sample',state['key'],{'a':'first','z':True},callback)
        self.assertEqual(list(callback.call_args.args[1]),['z','a'])

    def test_invalid_payload_key_and_corrupt_saved_payload_never_reach_backend(self):
        state=command_state(self.request,'sample');callback=Mock()
        for payload in [[],{'x':float('nan')},{'x':'a'*131073},{'x':object()}]:
            with self.assertRaises(ValidationError):send_command(self.request,'sample',state['key'],payload,callback)
        for key in ['я'*36,'bad',None]:
            with self.assertRaises(ValidationError):send_command(self.request,'sample',key,{'x':1},callback)
        self.assertIsNone(PendingCommand.objects.get().payload)
        PendingCommand.objects.update(payload=['corrupt'])
        with self.assertRaises(ValidationError):command_state(self.request,'sample')
        callback.assert_not_called();self.assertTrue(PendingCommand.objects.exists())
