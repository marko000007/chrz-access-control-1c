from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from .integration import ERPForbidden,ERPUnavailable,get_client

ROLE_LABELS={"admin":"Администратор","requester":"Заявитель","approver":"Согласующий","guard":"Сотрудник проходной"}


def erp_roles(*roles):
    def decorate(view):
        @login_required
        @wraps(view)
        def wrapped(request,*args,**kwargs):
            try:
                client=get_client()
                profile=client.actor(request.user.get_username())
            except ERPForbidden:
                raise PermissionDenied("1С не разрешила доступ.") from None
            except ERPUnavailable as exc:
                return render(request,"portal/unavailable.html",{"reason":str(exc)},status=503)
            if profile['role'] not in roles:
                raise PermissionDenied("Требуется другая роль в системе 1С.")
            request.erp_client=client
            request.erp_profile=profile
            return view(request,*args,**kwargs)
        return wrapped
    return decorate
