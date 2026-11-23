from datetime import timedelta
from unittest.mock import Mock, patch
import uuid
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, Client, RequestFactory
from django.utils import timezone
from portal.commands import command_state, send_command, clear_command
from portal.integration import ERPUnavailable
from portal.models import PendingCommand


class WorkflowViewTests(TestCase):
    """Boundary tests stub the backend; real HTTP/1C proof is separate."""
    def setUp(self):
        self.user=get_user_model().objects.create_user('operator')
        self.client.force_login(self.user)
        self.role='approver'
        self.erp=Mock()
        self.erp.actor.side_effect=lambda actor:{'actor':actor,'role':self.role}
        self.identifier=str(uuid.uuid4())
        self.erp.requests.return_value=[{'id':self.identifier,'visitor':'<script>Учебный</script>',
            'requester_login':'requester','status':'submitted','starts_at':timezone.now(),
            'ends_at':timezone.now()+timedelta(hours=1)}]
        self.erp.request_detail.side_effect=lambda actor,identifier:next(item for item in self.erp.requests.return_value if item['id']==str(identifier))
        self.patch=patch('portal.permissions.get_client',return_value=self.erp);self.patch.start();self.addCleanup(self.patch.stop)

    def test_get_is_readonly_and_uncertain_command_retries_exactly(self):
        path=f'/requests/{self.identifier}/approve/'
        response=self.client.get(path)
        self.assertContains(response,'&lt;script&gt;')
        key=response.context['form']['command_key'].value()
        self.erp.decide_request.assert_not_called()
        payload={'command_key':key,'expected_status':'submitted','reason':'Учебное решение'}
        self.erp.decide_request.side_effect=ERPUnavailable('Ответ потерян')
        self.assertEqual(self.client.post(path,payload).status_code,200)
        self.assertEqual(self.erp.decide_request.call_count,1)
        self.assertTrue(PendingCommand.objects.filter(owner=self.user,payload__isnull=False).exists())
        self.assertEqual(self.client.post(path,{**payload,'reason':'Изменённое решение'}).status_code,200)
        self.assertEqual(self.erp.decide_request.call_count,1)
        # The original mutation may already have succeeded; replay must still be available.
        self.erp.requests.return_value[0]['status']='approved'
        self.erp.decide_request.side_effect=None
        self.erp.decide_request.return_value={'id':self.identifier,'status':'approved'}
        self.assertEqual(self.client.post(path,payload).status_code,302)
        self.assertFalse(PendingCommand.objects.filter(owner=self.user,payload__isnull=False).exists())
        self.assertEqual(self.erp.decide_request.call_args.args[-1],key)

    def test_backend_role_and_requester_isolation_override_staff(self):
        self.user.is_staff=True;self.user.save(update_fields=['is_staff'])
        self.role='requester'
        self.assertEqual(self.client.get(f'/requests/{self.identifier}/approve/').status_code,403)
        self.erp.passes.return_value=[{'id':str(uuid.uuid4()),'requester_login':'other','visitor':'SECRET PERSON'}]
        response=self.client.get('/passes/')
        self.assertEqual(response.status_code,503)
        self.assertNotContains(response,'SECRET PERSON',status_code=503)
        self.erp.issue_pass.assert_not_called()

    def test_issue_confirmation_and_csrf(self):
        self.role='guard';self.erp.requests.return_value[0]['status']='approved'
        path=f'/requests/{self.identifier}/issue/'
        self.assertEqual(self.client.get(path).status_code,200)
        self.erp.issue_pass.assert_not_called()
        csrf_client=Client(enforce_csrf_checks=True);csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(path,{}).status_code,403)
        response=self.client.get(path)
        key=response.context['form']['command_key'].value()
        self.erp.issue_pass.return_value={'id':str(uuid.uuid4()),'state':'active','position':'outside'}
        self.assertEqual(self.client.post(path,{'command_key':key}).status_code,302)
        self.erp.issue_pass.assert_called_once_with(self.user.username,self.identifier,key)

    def test_lists_escape_content_and_render_actions(self):
        self.role='guard'
        now=timezone.now()
        self.erp.passes.return_value=[{'id':str(uuid.uuid4()),'checkpoint_id':str(uuid.uuid4()),
            'requester_login':'requester','visitor':'<img>','checkpoint':'Точка','state':'active',
            'position':'outside','starts_at':now-timedelta(minutes=1),'ends_at':now+timedelta(hours=1)}]
        response=self.client.get('/passes/')
        self.assertContains(response,'&lt;img&gt;')
        self.assertContains(response,'Действующий')
        self.assertContains(response,'Вход')
        self.erp.events.return_value=[]
        self.assertContains(self.client.get('/events/'),'Проходов пока нет')

    def test_existing_pass_links_to_state_instead_of_offering_duplicate_issue(self):
        self.role='guard'
        self.erp.requests.return_value[0]['status']='approved'
        self.erp.passes.return_value=[{'request_id':self.identifier,'id':str(uuid.uuid4())}]
        response=self.client.get('/requests/')
        self.assertContains(response,'Открыть пропуск')
        self.assertNotContains(response,'Выдать пропуск')

    def test_decision_uses_card_beyond_recent_list(self):
        self.erp.requests.side_effect=AssertionError('The recent list is not a record lookup')
        path=f'/requests/{self.identifier}/approve/'
        response=self.client.get(path);self.assertEqual(response.status_code,200)
        key=response.context['form']['command_key'].value()
        self.erp.decide_request.return_value={'id':self.identifier,'status':'approved'}
        self.assertEqual(self.client.post(path,{'command_key':key,'expected_status':'submitted','reason':'Учебное решение'}).status_code,302)
        self.erp.requests.assert_not_called();self.erp.request_detail.assert_called_with(self.user.username,self.identifier)

    def test_movement_uses_direct_card_and_missing_is_404(self):
        from portal.integration import ERPMissing
        self.role='guard';identifier=str(uuid.uuid4());checkpoint=str(uuid.uuid4())
        self.erp.passes.side_effect=AssertionError('The recent list is not a record lookup')
        self.erp.pass_detail.return_value={'id':identifier,'visitor':'Учебный посетитель','checkpoint':'Проходная','checkpoint_id':checkpoint}
        path=f'/passes/{identifier}/in/'
        response=self.client.get(path);self.assertEqual(response.status_code,200)
        key=response.context['form']['command_key'].value()
        self.assertEqual(self.client.post(path,{'command_key':key}).status_code,302)
        self.erp.movement.assert_called_once_with(self.user.username,identifier,checkpoint,'in',key)
        self.erp.passes.assert_not_called()
        self.erp.pass_detail.side_effect=ERPMissing()
        self.assertEqual(self.client.get(path).status_code,404)


class DurableCommandTests(TestCase):
    def setUp(self):
        self.user=get_user_model().objects.create_user('recovery')
        self.request=RequestFactory().get('/');self.request.user=self.user

    def test_uncertainty_survives_new_browser_and_changed_payload_is_blocked(self):
        state=command_state(self.request,'sample')
        def uncertain(key,payload):raise ERPUnavailable('Unknown result')
        with self.assertRaises(ERPUnavailable):send_command(self.request,'sample',state['key'],{'id':'one'},uncertain)
        fresh=RequestFactory().get('/');fresh.user=self.user
        self.assertEqual(command_state(fresh,'sample'),{'key':state['key'],'payload':{'id':'one'}})
        with self.assertRaises(ValidationError):send_command(fresh,'sample',state['key'],{'id':'two'},Mock())

    def test_late_confirmation_does_not_delete_newer_command(self):
        first=command_state(self.request,'sample')
        later=[]
        def delayed(key,payload):
            clear_command(self.request,'sample',key)
            next_state=command_state(self.request,'sample');later.append(next_state['key'])
            PendingCommand.objects.filter(owner=self.user,context='sample',key=next_state['key']).update(payload={'next':True})
            return {'ok':True}
        send_command(self.request,'sample',first['key'],{'id':'one'},delayed)
        self.assertEqual(command_state(self.request,'sample'),{'key':later[0],'payload':{'next':True}})
