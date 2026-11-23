from datetime import timedelta
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
    return render(request,"portal/report.html",{"form":form,"report":report})
