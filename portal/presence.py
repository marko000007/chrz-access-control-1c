"""Закрытый оперативный снимок посетителей, ещё не отметивших выход."""
import csv
import io
from datetime import timezone
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from .permissions import erp_roles
from .integration import ERPForbidden,ERPRejected,ERPUnavailable
from .reports import csv_cell


def presence_csv(report):
    stream=io.StringIO(newline='');writer=csv.writer(stream,delimiter=';')
    writer.writerow(['Тип строки','ID пропуска','Посетитель','Точка','Статус пропуска','ОкончаниеUTC',
                     'Срок истёк','Всего внутри','Отозваны','С истёкшим сроком','СформированоUTC'])
    stamp=report['generated_at'].astimezone(timezone.utc).isoformat()
    writer.writerow(['Итоги','','','','','', '',report['total'],report['revoked'],report['expired'],stamp])
    for row in report['items']:
        writer.writerow([csv_cell(value) for value in ['Посетитель',row['id'],row['visitor'],row['checkpoint'],
            'Отозван' if row['state']=='revoked' else 'Действует',row['ends_at'].astimezone(timezone.utc).isoformat(),
            'Да' if row['ends_at']<=report['generated_at'] else 'Нет','','','',stamp]])
    response=HttpResponse('\ufeff'+stream.getvalue(),content_type='text/csv; charset=utf-8')
    response['Content-Disposition']='attachment; filename="visitors-inside.csv"'
    response['Cache-Control']='private, no-store'
    return response


@erp_roles('admin','guard')
def presence(request):
    try:
        report=request.erp_client.presence_report(request.user.get_username())
    except ERPForbidden:
        raise PermissionDenied from None
    except (ERPRejected,ERPUnavailable) as exc:
        return render(request,'portal/unavailable.html',{'reason':str(exc)},status=503)
    if request.GET.get('format')=='csv':
        return presence_csv(report)
    return render(request,'portal/presence.html',{'report':report})
