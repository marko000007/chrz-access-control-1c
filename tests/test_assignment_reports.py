from datetime import date
from unittest.mock import Mock, patch
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase
from portal.integration import ERPClient, ERPUnavailable


class AssignmentReportViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('report.guard')
        self.client.force_login(self.user)
        self.erp = Mock()
        self.erp.actor.return_value = {'actor': self.user.username, 'role': 'guard'}
        self.erp.assignment_report.return_value = {'name': 'AssetBalance', 'title': 'Остатки',
            'columns': ['Ценность', 'Количество'], 'rows': [['<script>alert(1)</script>', '7']]}
        self.values = {'report': 'AssetBalance', 'start': '2026-11-28', 'end': '2026-11-28'}
        p = patch('portal.permissions.get_client', return_value=self.erp); p.start(); self.addCleanup(p.stop)

    def test_render_escapes_data_and_csv_protects_formulas(self):
        response = self.client.get('/reports/assignment/', self.values)
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertIn('no-store', response['Cache-Control'])
        self.erp.assignment_report.return_value['rows'][0][0] = '=1+1'
        response = self.client.get('/reports/assignment/', {**self.values, 'format': 'csv'})
        self.assertIn("'=1+1", response.content.decode('utf-8-sig'))
        self.assertIn('attachment', response['Content-Disposition'])

    def test_forbidden_role_and_invalid_input_do_not_read_report(self):
        self.erp.actor.return_value['role'] = 'requester'
        self.assertEqual(self.client.get('/reports/assignment/', self.values).status_code, 403)
        self.erp.assignment_report.assert_not_called()
        self.erp.actor.return_value['role'] = 'guard'
        for values in [{**self.values, 'report': '../Secret'}, {**self.values, 'end': '2026-12-29'}]:
            self.client.get('/reports/assignment/', values)
        self.erp.assignment_report.assert_not_called()

    def test_unavailable_backend_is_explicit(self):
        self.erp.assignment_report.side_effect = ERPUnavailable('Сервис недоступен')
        self.assertEqual(self.client.get('/reports/assignment/', self.values).status_code, 503)


class AssignmentReportContractTests(SimpleTestCase):
    def test_ragged_oversized_or_wrong_named_report_is_rejected(self):
        client = ERPClient('http://127.0.0.1:12345', 'test', 'test')
        good = {'name': 'AssetBalance', 'title': 'Остатки', 'columns': ['Ценность', 'Количество'], 'rows': [['Тест', '7']]}
        with patch.object(client, 'request', return_value=good):
            self.assertEqual(client.assignment_report('guard', 'AssetBalance', date(2026, 11, 28), date(2026, 11, 28)), good)
        for bad in [{**good, 'name': 'IncidentSummary'}, {**good, 'rows': [['Тест']]},
                    {**good, 'rows': good['rows']*1001}, {**good, 'rows': [['Тест', 7]]}]:
            with self.subTest(bad=bad.get('name')), patch.object(client, 'request', return_value=bad):
                with self.assertRaises(ERPUnavailable):
                    client.assignment_report('guard', 'AssetBalance', date(2026, 11, 28), date(2026, 11, 28))

    def test_report_name_is_allowlisted_before_transport(self):
        client = ERPClient('http://127.0.0.1:12345', 'test', 'test')
        with patch.object(client.opener, 'open') as transport:
            with self.assertRaises(ValueError): client.request('GET', '/reports/assignment/Secret/20261128/20261128', 'guard')
            transport.assert_not_called()
