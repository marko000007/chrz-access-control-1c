from datetime import timedelta, timezone as dt_timezone
import csv
import io
from urllib.parse import urlencode
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django import forms
from django.shortcuts import render
from django.utils import timezone
from .permissions import erp_roles
from .integration import ERPForbidden, ERPRejected, ERPUnavailable
from django.core.exceptions import PermissionDenied


class ReportPeriod(forms.Form):
    direction=forms.ChoiceField(label='Направление',required=False,choices=[('', 'Все'),('in','Вход'),('out','Выход')])
    visitor=forms.CharField(label='Посетитель содержит',max_length=150,required=False)
    checkpoint=forms.CharField(label='Точка содержит',max_length=150,required=False)
    actor=forms.CharField(label='Автор отметки содержит',max_length=150,required=False)
    start=forms.DateField(label="Начало периода (UTC)",widget=forms.DateInput(format="%Y-%m-%d",attrs={"type":"date"}))
    end=forms.DateField(label="Конец периода включительно (UTC)",widget=forms.DateInput(format="%Y-%m-%d",attrs={"type":"date"}))

    def clean(self):
        data=super().clean()
        if data.get("start") and data.get("end"):
            if not 0<=(data["end"]-data["start"]).days<31 or not 1900<=data["start"].year<=data["end"].year<=2100:
                raise forms.ValidationError("Выберите от1 до31 дней в1900–2100годах.")
        return data


def csv_cell(value):
    value=str(value)
    probe=value.lstrip()
    return "'"+value if value[:1] in {"=","+","-","@","\t","\r","\n"} or probe[:1] in {"=","+","-","@"} else value


def report_csv(report, start, end):
    stream=io.StringIO(newline="");writer=csv.writer(stream,delimiter=";")
    writer.writerow(["ID события","ВремяUTC","Направление","Посетитель","Точка","Автор отметки","Заявитель","ID пропуска","СформированоUTC"])
    for item in report["items"]:
        row=[item["id"],item["occurred_at"].astimezone(dt_timezone.utc).isoformat(),
            "Вход" if item["direction"]=="in" else "Выход",item["visitor"],item["checkpoint"],item["actor"],
            item["requester_login"],item["pass_id"],report["generated_at"].astimezone(dt_timezone.utc).isoformat()]
        writer.writerow([csv_cell(value) for value in row])
    response=HttpResponse("\ufeff"+stream.getvalue(),content_type="text/csv; charset=utf-8")
    response["Content-Disposition"]=f'attachment; filename="movements-{start:%Y-%m-%d}-{end:%Y-%m-%d}.csv"'
    response["Cache-Control"]="private, no-store"
    return response


def filtered_report(report,values):
    items=[]
    for row in report['items']:
        if values.get('direction') and row['direction']!=values['direction']:continue
        if any(values.get(key) and values[key].casefold() not in row[key].casefold() for key in ['visitor','checkpoint','actor']):continue
        items.append(row)
    return {**report,'items':items,'count_in':sum(row['direction']=='in' for row in items),
            'count_out':sum(row['direction']=='out' for row in items),
            'source_count':len(report['items']),'source_count_in':report['count_in'],'source_count_out':report['count_out'],
            'filters':{key:values.get(key,'') for key in ['direction','visitor','checkpoint','actor']}}


@erp_roles("admin","guard")
def movement_report(request):
    today=timezone.now().date()
    form=ReportPeriod(request.GET if request.GET else {"start":today-timedelta(days=6),"end":today})
    report=None;query=""
    if form.is_valid():
        try:
            source=request.erp_client.movement_report(request.user.get_username(),**{key:form.cleaned_data[key] for key in ['start','end']})
            report=filtered_report(source,form.cleaned_data)
            query=urlencode({key:value.isoformat() if hasattr(value,'isoformat') else value for key,value in form.cleaned_data.items()})
        except ERPForbidden:raise PermissionDenied from None
        except ERPRejected as exc:form.add_error(None,str(exc))
        except ERPUnavailable as exc:return render(request,"portal/unavailable.html",{"reason":str(exc)},status=503)
    if request.GET.get("format")=="csv":
        if report is None:return HttpResponseBadRequest("Отчёт не сформирован: проверьте период и ограничения.")
        return report_csv(report,form.cleaned_data["start"],form.cleaned_data["end"])
    if request.GET.get('format')=='json':
        if report is None:return JsonResponse({'error':'Отчёт не сформирован.'},status=400)
        response=JsonResponse({'schema_version':1,**report},json_dumps_params={'ensure_ascii':False})
        response['Content-Disposition']='attachment; filename="movement-report.json"';response['Cache-Control']='private, no-store'
        return response
    return render(request,"portal/report.html",{"form":form,"report":report,"query":query})
