from datetime import timedelta, timezone as dt_timezone
import csv
import io
from django.http import HttpResponse, HttpResponseBadRequest
from django import forms
from django.shortcuts import render
from django.utils import timezone
from .permissions import erp_roles
from .integration import ERPForbidden, ERPRejected, ERPUnavailable
from django.core.exceptions import PermissionDenied


class ReportPeriod(forms.Form):
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


@erp_roles("admin","guard")
def movement_report(request):
    today=timezone.now().date()
    form=ReportPeriod(request.GET if request.GET else {"start":today-timedelta(days=6),"end":today})
    report=None
    if form.is_valid():
        try:report=request.erp_client.movement_report(request.user.get_username(),**form.cleaned_data)
        except ERPForbidden:raise PermissionDenied from None
        except ERPRejected as exc:form.add_error(None,str(exc))
        except ERPUnavailable as exc:return render(request,"portal/unavailable.html",{"reason":str(exc)},status=503)
    if request.GET.get("format")=="csv":
        if report is None:return HttpResponseBadRequest("Отчёт не сформирован: проверьте период и ограничения.")
        return report_csv(report,**form.cleaned_data)
    return render(request,"portal/report.html",{"form":form,"report":report})
