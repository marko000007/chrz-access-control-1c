from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render
from .permissions import erp_roles
from .integration import ERPForbidden, ERPMissing, ERPUnavailable


@erp_roles("admin","requester","approver","guard")
def request_detail(request, pk):
    try:
        item=request.erp_client.request_detail(request.user.get_username(),str(pk))
        if request.erp_profile["role"]=="requester" and item["requester_login"]!=request.user.get_username():
            raise ERPForbidden
        if request.erp_profile["role"]=="guard" and item["status"]!="approved":
            raise ERPForbidden
    except ERPForbidden:raise PermissionDenied from None
    except ERPMissing:raise Http404 from None
    except ERPUnavailable as exc:return render(request,"portal/unavailable.html",{"reason":str(exc)},status=503)
    item["status_label"]={"submitted":"На согласовании","approved":"Согласована","rejected":"Отклонена","cancelled":"Отменена"}[item["status"]]
    return render(request,"portal/request_detail.html",{"item":item})
