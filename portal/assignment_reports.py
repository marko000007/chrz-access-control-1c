"""Пять предметных отчётов; таблицы рассчитывает платформа 1С."""
import csv
import io
from urllib.parse import urlencode
from django import forms
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from .permissions import erp_roles
from .integration import ERPForbidden, ERPRejected, ERPUnavailable
from .reports import ReportPeriod, csv_cell

REPORTS = {'VisitJournal': 'Журнал посещений', 'ActivePasses': 'Действующие пропуска',
           'RequestDecisions': 'Решения по заявкам', 'AssetBalance': 'Остатки ценностей',
           'IncidentSummary': 'Нарушения за период'}


class AssignmentPeriod(ReportPeriod):
    report = forms.ChoiceField(label='Отчёт', choices=list(REPORTS.items()))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for key in ['direction', 'visitor', 'checkpoint', 'actor']:
            self.fields.pop(key)


@erp_roles('admin', 'guard')
def assignment_reports(request):
    today = timezone.now().date()
    form = AssignmentPeriod(request.GET or None, initial={'report': 'VisitJournal', 'start': today, 'end': today})
    report = None
    if request.GET and form.is_valid():
        values = form.cleaned_data
        try:
            report = request.erp_client.assignment_report(request.user.get_username(), values['report'], values['start'], values['end'])
        except ERPForbidden:
            raise PermissionDenied('1С не разрешила доступ.') from None
        except ERPRejected:
            form.add_error(None, '1С отклонила отчёт: сократите период или проверьте данные.')
        except ERPUnavailable as exc:
            return render(request, 'portal/unavailable.html', {'reason': str(exc)}, status=503)
        if report:
            report['display_rows'] = [list(zip(report['columns'], row)) for row in report['rows']]
        if report and request.GET.get('format') == 'csv':
            stream = io.StringIO(newline=''); writer = csv.writer(stream, delimiter=';')
            writer.writerow(['ООО «ЧРЗ»', report['title'], str(values['start']), str(values['end'])])
            writer.writerow([csv_cell(c) for c in report['columns']])
            writer.writerows([[csv_cell(c) for c in row] for row in report['rows']])
            response = HttpResponse('\ufeff'+stream.getvalue(), content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="{values["report"]}.csv"'
            return response
    query = urlencode({key: value for key, value in request.GET.items() if key != 'format'})
    return render(request, 'portal/assignment_reports.html', {'form': form, 'report': report, 'query': query})
