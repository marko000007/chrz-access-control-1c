from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import render
from .permissions import erp_roles
from .integration import ERPForbidden, ERPMissing, ERPUnavailable


@erp_roles("admin","requester","approver","guard")
def pass_detail(request, pk):
    try:
        item=request.erp_client.pass_detail(request.user.get_username(),str(pk))
        if request.erp_profile["role"]=="requester" and item["requester_login"]!=request.user.get_username():raise ERPForbidden
    except ERPForbidden:raise PermissionDenied from None
    except ERPMissing:raise Http404 from None
    except ERPUnavailable as exc:return render(request,"portal/unavailable.html",{"reason":str(exc)},status=503)
    item["current"]=item["starts_at"]<=item["snapshot_at"]<item["ends_at"]
    return render(request,"portal/pass_detail.html",{"item":item})
