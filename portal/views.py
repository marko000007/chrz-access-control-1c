from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .integration import get_client, ERPUnavailable


def home(request):
    return render(request,"portal/home.html")


@login_required
def dashboard(request):
    try:
        health=get_client().health(request.user.get_username())
        status="Ответ сервиса 1С получен по контракту API v1."
    except ERPUnavailable as exc:
        status=str(exc)
    return render(request,"portal/dashboard.html",{"integration_status":status})


from .permissions import erp_roles,ROLE_LABELS


@erp_roles("admin","requester","approver","guard")
def workspace(request):
    return render(request,"portal/workspace.html",{"profile":request.erp_profile,"role_label":ROLE_LABELS[request.erp_profile["role"]]})
