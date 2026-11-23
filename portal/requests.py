from datetime import datetime
from django import forms
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.shortcuts import redirect,render
from .integration import ERPUnavailable,ERPForbidden,ERPConflict,ERPRejected
from .commands import command_state, send_command, command_capacity
from django.core.exceptions import ValidationError
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
        for field in ["starts_at", "ends_at"]:
            if values.get(field) and values[field].microsecond:
                self.add_error(field, "1С хранит время с точностью до секунды.")
        if values.get("starts_at") and values.get("ends_at") and values["ends_at"]<=values["starts_at"]:
            self.add_error("ends_at","Окончание должно быть позже начала.")
        return values

    def payload(self):
        return {key:value.isoformat() if isinstance(value,datetime) else value for key,value in self.cleaned_data.items() if key!="command_key"}


@erp_roles("admin","requester","approver","guard")
def request_list(request):
    try:
        items=request.erp_client.requests(request.user.get_username())
        if request.erp_profile["role"]=="requester" and any(item["requester_login"]!=request.user.get_username() for item in items):
            raise ERPUnavailable("1С вернула заявку другой рабочей области.")
    except ERPForbidden:
        raise PermissionDenied("1С отозвала доступ.") from None
    except ERPUnavailable as exc:
        return render(request,"portal/unavailable.html",{"reason":str(exc)},status=503)
    issued = {}
    if request.erp_profile["role"] in {"admin", "guard"}:
        try:
            issued = {row["request_id"]:row["id"] for row in request.erp_client.passes(request.user.get_username())}
        except ERPUnavailable as exc:
            if isinstance(exc, ERPForbidden): raise PermissionDenied("1С отозвала доступ.") from None
            return render(request,"portal/unavailable.html",{"reason":str(exc)},status=503)
    for item in items:
        item["existing_pass_id"] = issued.get(item["id"])
        item["status_label"] = {"submitted":"Ожидает решения", "approved":"Согласована", "rejected":"Отклонена", "cancelled":"Отменена"}[item["status"]]
        item["can_decide"] = item["status"] == "submitted" and request.erp_profile["role"] in {"admin","approver"} and item["requester_login"] != request.user.get_username()
        item["can_cancel"] = item["status"] == "submitted" and (request.erp_profile["role"] == "admin" or (request.erp_profile["role"] == "requester" and item["requester_login"] == request.user.get_username()))
        item["can_issue"] = item["status"] == "approved" and request.erp_profile["role"] in {"admin","guard"} and not item["existing_pass_id"]
    return render(request,"portal/requests.html",{"items":items,"can_create":request.erp_profile["role"] in {"admin","requester"}})


@erp_roles("admin","requester")
@command_capacity
def request_create(request):
    try:
        references=request.erp_client.references(request.user.get_username())
    except ERPForbidden:
        raise PermissionDenied("1С отозвала доступ.") from None
    except ERPUnavailable as exc:
        return render(request,"portal/unavailable.html",{"reason":str(exc)},status=503)
    state = command_state(request, "request:new")
    key = state["key"]
    initial = dict(state["payload"] or {})
    for field in ["starts_at", "ends_at"]:
        if field in initial: initial[field] = datetime.fromisoformat(initial[field])
    initial["command_key"]=key
    form=NewRequestForm(request.POST if request.method=="POST" else None,references=references,initial=initial)
    status=200
    if request.method=="POST":
        status=400
        if form.is_valid():
            try:
                send_command(request, "request:new", form.cleaned_data["command_key"], form.payload(),
                    lambda nonce,payload:request.erp_client.create_request(request.user.get_username(),payload,nonce))
            except ValidationError as exc:
                form.add_error(None, exc)
            except ERPForbidden:
                raise PermissionDenied("1С отозвала доступ к отправке.") from None
            except ERPConflict as exc:
                form.add_error(None, str(exc));status=409
            except ERPRejected as exc:
                form.add_error(None, str(exc));status=400
            except ERPUnavailable as exc:
                form.add_error(None, str(exc));status=503
            else:
                messages.success(request,"1С подтвердила приём заявки на согласование.")
                return redirect("request_list")
    return render(request,"portal/request_form.html",{"form":form},status=status)
