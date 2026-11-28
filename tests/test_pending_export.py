import hashlib
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from portal.commands import canonical_payload
from portal.models import PendingCommand


class PendingExportTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('export-owner')
        self.other=get_user_model().objects.create_user('export-other')
        self.client.force_login(self.user)
        self.own=PendingCommand.objects.create(owner=self.user,context='visitor:create',payload={'name':'Личный пример','company':'Учебная'})
        self.draft=PendingCommand.objects.create(owner=self.user,context='request:new')
        PendingCommand.objects.create(owner=self.other,context='visitor:create',payload={'name':'FOREIGN_PRIVATE'})

    def test_export_is_own_consistent_and_readonly_without_rpc(self):
        with patch('portal.permissions.get_client') as client:
            response=self.client.get('/pending/export.json');client.assert_not_called()
        self.assertEqual(response.status_code,200)
        data=response.json();self.assertEqual(data['actor'],self.user.username)
        self.assertEqual(len(data['commands']),2)
        self.assertNotIn('FOREIGN_PRIVATE',response.content.decode())
        row=next(row for row in data['commands'] if row['key']==str(self.own.key))
        self.assertEqual(row['payload_sha256'],hashlib.sha256(canonical_payload(self.own.payload).encode()).hexdigest())
        self.assertEqual(row['state'],'unknown')
        self.assertIsNone(next(row for row in data['commands'] if row['key']==str(self.draft.key))['payload_sha256'])
        self.assertIn('no-store',response['Cache-Control']);self.assertIn('private',response['Cache-Control'])
        self.assertIn('attachment;',response['Content-Disposition'])
        self.assertEqual(PendingCommand.objects.count(),3)

    def test_corruption_or_over_capacity_rejects_whole_export_without_deletion(self):
        PendingCommand.objects.filter(pk=self.own.pk).update(payload=['damaged'])
        self.assertEqual(self.client.get('/pending/export.json').status_code,409)
        self.assertEqual(PendingCommand.objects.count(),3)
        PendingCommand.objects.filter(pk=self.own.pk).update(payload={})
        PendingCommand.objects.bulk_create([PendingCommand(owner=self.user,context='extra:'+str(n)) for n in range(19)])
        self.assertEqual(self.client.get('/pending/export.json').status_code,409)
        self.assertEqual(PendingCommand.objects.filter(owner=self.user).count(),21)

    def test_anonymous_user_cannot_download_queue(self):
        self.client.logout()
        self.assertEqual(self.client.get('/pending/export.json').status_code,302)
