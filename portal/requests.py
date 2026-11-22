import hashlib
import hmac
import json
import uuid
from datetime import datetime
from django import forms
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.shortcuts import redirect,render
from .integration import ERPUnavailable,ERPForbidden,ERPConflict
from .permissions import erp_roles


class NewRequestForm(forms.Form):
    visitor_id=forms.ChoiceField(label="Посетитель")
    host_id=forms.ChoiceField(label="Принимающий сотрудник")
    checkpoint_id=forms.ChoiceField(label="Точка прохода")
    purpose_id=forms.ChoiceField(label="Цель посещения")
    starts_at=forms.DateTimeField(label="Начало",widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M",attrs={"type":"datetime-local"}))
    ends_at=forms.DateTimeField(label="Окончание",widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M",attrs={"type":"datetime-local"}))
    command_key=forms.UUIDField(widget=forms.HiddenInput)

    def __init__(self,*args,references,**kwargs):
        super().__init__(*args,**kwargs)
        for field,kind in [("visitor_id","visitors"),("host_id","employees"),("checkpoint_id","checkpoints"),("purpose_id","purposes")]:
            self.fields[field].choices=[("","Выберите значение"),*[(item["id"],item["name"]) for item in references[kind]]]

    def clean(self):
        values=super().clean()
        if values.get("starts_at") and values.get("ends_at") and values["ends_at"]<=values["starts_at"]:
            self.add_error("ends_at","Окончание должно быть позже начала.")
        return values

    def payload(self):
        return {key:value.isoformat() if isinstance(value,datetime) else value for key,value in self.cleaned_data.items() if key!="command_key"}


@erp_roles("admin","requester","approver")
def request_list(request):
    try:
        items=request.erp_client.requests(request.user.get_username())
        if request.erp_profile["role"]=="requester" and any(item["requester_login"]!=request.user.get_username() for item in items):
            raise ERPUnavailable("1С вернула заявку другой рабочей области.")
    except ERPForbidden:
        raise PermissionDenied("1С отозвала доступ.") from None
    except ERPUnavailable as exc:
        return render(request,"portal/unavailable.html",{"reason":str(exc)},status=503)
    return render(request,"portal/requests.html",{"items":items,"can_create":request.erp_profile["role"] in {"admin","requester"}})


@erp_roles("admin","requester")
def request_create(request):
    try:
        references=request.erp_client.references(request.user.get_username())
    except ERPForbidden:
        raise PermissionDenied("1С отозвала доступ.") from None
    except ERPUnavailable as exc:
        return render(request,"portal/unavailable.html",{"reason":str(exc)},status=503)
    key=request.session.get("request_create_key")
    if not isinstance(key,str):
        key=str(uuid.uuid4());request.session["request_create_key"]=key
    initial=dict(request.session.get("request_create_pending",{}))
    for field in ["starts_at","ends_at"]:
        if field in initial:initial[field]=datetime.fromisoformat(initial[field])
    initial["command_key"]=key
    form=NewRequestForm(request.POST if request.method=="POST" else None,references=references,initial=initial)
    status=200
    if request.method=="POST":
        status=400
        if form.is_valid():
            if not hmac.compare_digest(str(form.cleaned_data["command_key"]),key):
                form.add_error(None,"Форма устарела. Обновите страницу перед отправкой.")
            else:
                payload=form.payload()
                digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
                pending=request.session.get("request_create_digest")
                if pending is not None and not hmac.compare_digest(pending,digest):
                    form.add_error(None,"Предыдущая отправка не подтверждена. Повторите её с теми же данными и проверьте список заявок.")
                else:
                    request.session["request_create_digest"]=digest
                    request.session["request_create_pending"]=payload
                    request.session.save()
                    try:
                        request.erp_client.create_request(request.user.get_username(),payload,key)
                    except ERPForbidden:
                        raise PermissionDenied("1С отозвала доступ к отправке.") from None
                    except ERPConflict as exc:
                        form.add_error(None,str(exc));status=409
                    except ERPUnavailable as exc:
                        form.add_error(None,str(exc));status=503
                    else:
                        for field in ["request_create_key","request_create_digest","request_create_pending"]:request.session.pop(field,None)
                        messages.success(request,"1С подтвердила приём заявки на согласование.")
                        return redirect("request_list")
    return render(request,"portal/request_form.html",{"form":form},status=status)
