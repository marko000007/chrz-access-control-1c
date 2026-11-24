from uuid import uuid4
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase,Client
from portal.models import PendingCommand
from portal.pending import resume_link


class PendingViewTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('pending-view');self.other=get_user_model().objects.create_user('pending-other')
        self.client.force_login(self.user)

    def test_only_own_metadata_and_safe_fixed_links_are_shown_without_rpc(self):
        own=PendingCommand.objects.create(owner=self.user,context='request:new',payload={'secret':'RAW_PAYLOAD'})
        PendingCommand.objects.create(owner=self.other,context='visitor:create',payload={'name':'FOREIGN'})
        with patch('portal.permissions.get_client') as erp:
            response=self.client.get('/pending/')
            self.assertContains(response,'Создание заявки');self.assertNotContains(response,'FOREIGN');self.assertNotContains(response,'RAW_PAYLOAD')
            erp.assert_not_called()
        identifier=uuid4();self.assertEqual(resume_link(f'issue:{identifier}')[0],f'/requests/{identifier}/issue/')
        self.assertIsNone(resume_link('https://evil.invalid')[0]);self.assertIsNone(resume_link('pass:bad:out')[0])

    def test_only_matching_unfrozen_command_can_be_dismissed(self):
        draft=PendingCommand.objects.create(owner=self.user,context='visitor:create')
        frozen=PendingCommand.objects.create(owner=self.user,context='request:new',payload={'x':1})
        self.assertEqual(self.client.get(f'/pending/{draft.pk}/dismiss/').status_code,405)
        self.client.post(f'/pending/{draft.pk}/dismiss/',{'key':uuid4()})
        self.assertTrue(PendingCommand.objects.filter(pk=draft.pk).exists())
        self.client.post(f'/pending/{frozen.pk}/dismiss/',{'key':frozen.key})
        self.assertTrue(PendingCommand.objects.filter(pk=frozen.pk).exists())
        self.client.post(f'/pending/{draft.pk}/dismiss/',{'key':draft.key})
        self.assertFalse(PendingCommand.objects.filter(pk=draft.pk).exists())

    def test_foreign_command_and_csrf_are_protected(self):
        foreign=PendingCommand.objects.create(owner=self.other,context='request:new')
        self.assertEqual(self.client.post(f'/pending/{foreign.pk}/dismiss/',{'key':foreign.key}).status_code,404)
        own=PendingCommand.objects.create(owner=self.user,context='request:new')
        client=Client(enforce_csrf_checks=True);client.force_login(self.user)
        self.assertEqual(client.post(f'/pending/{own.pk}/dismiss/',{'key':own.key}).status_code,403)
        self.assertTrue(PendingCommand.objects.filter(pk=own.pk).exists())
