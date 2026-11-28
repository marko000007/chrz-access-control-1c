"""Закрытый оперативный снимок посетителей, ещё не отметивших выход."""
import csv
import io
from datetime import timezone
from django import forms
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from .permissions import erp_roles
from .integration import ERPForbidden,ERPRejected,ERPUnavailable
from .reports import csv_cell


class PresenceFilter(forms.Form):
    visitor=forms.CharField(label='Посетитель содержит',max_length=150,required=False)
    checkpoint=forms.CharField(label='Точка содержит',max_length=150,required=False)
    state=forms.ChoiceField(label='Состояние пропуска',required=False,choices=[('', 'Все'),('active','Действующий по статусу'),('revoked','Отозван'),('expired','Срок истёк')])


def select_presence(report,values):
    rows=[]
    for row in report['items']:
        if any(values.get(key) and values[key].casefold() not in row[key].casefold() for key in ['visitor','checkpoint']):continue
        state=values.get('state')
        if state=='expired' and row['ends_at']>report['generated_at']:continue
        if state in {'active','revoked'} and row['state']!=state:continue
        rows.append(row)
    return {**report,'items':rows,'total':len(rows),'revoked':sum(row['state']=='revoked' for row in rows),
        'expired':sum(row['ends_at']<=report['generated_at'] for row in rows),'source_total':report['total'],'filters':values}


def presence_csv(report):
    stream=io.StringIO(newline='');writer=csv.writer(stream,delimiter=';')
    writer.writerow(['Тип строки','ID пропуска','Посетитель','Точка','Статус пропуска','ОкончаниеUTC',
                     'Срок истёк','Всего в выборке','Отозваны','С истёкшим сроком','СформированоUTC', 'Всего в исходном снимке','Фильтр посетителя','Фильтр точки','Фильтр состояния'])
    stamp=report['generated_at'].astimezone(timezone.utc).isoformat()
    writer.writerow(['Итоги','','','','','', '',report['total'],report['revoked'],report['expired'],stamp,report.get('source_total',report['total']),*[csv_cell(report.get('filters',{}).get(key,'')) for key in ['visitor','checkpoint','state']]])
    for row in report['items']:
        writer.writerow([csv_cell(value) for value in ['Посетитель',row['id'],row['visitor'],row['checkpoint'],
            'Отозван' if row['state']=='revoked' else 'Действует',row['ends_at'].astimezone(timezone.utc).isoformat(),
            'Да' if row['ends_at']<=report['generated_at'] else 'Нет','','','',stamp,'','','','']])
    response=HttpResponse('\ufeff'+stream.getvalue(),content_type='text/csv; charset=utf-8')
    response['Content-Disposition']='attachment; filename="visitors-inside.csv"'
    response['Cache-Control']='private, no-store'
    return response


@erp_roles('admin','guard')
def presence(request):
    form=PresenceFilter(request.GET)
    if not form.is_valid():return render(request,'portal/presence.html',{'form':form},status=400)
    try:
        report=request.erp_client.presence_report(request.user.get_username())
    except ERPForbidden:
        raise PermissionDenied from None
    except (ERPRejected,ERPUnavailable) as exc:
        return render(request,'portal/unavailable.html',{'reason':str(exc)},status=503)
    report=select_presence(report,form.cleaned_data)
    if request.GET.get('format')=='csv':
        return presence_csv(report)
    params=request.GET.copy();params['format']='csv'
    return render(request,'portal/presence.html',{'report':report,'form':form,'export_query':params.urlencode()})
