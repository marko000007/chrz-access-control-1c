from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from .commands import command_state, send_command, command_capacity
from .integration import ERPUnavailable, ERPForbidden, ERPConflict, ERPRejected, ERPMissing
from .permissions import erp_roles


class CommandForm(forms.Form):
    command_key = forms.UUIDField(widget=forms.HiddenInput)


class DecisionForm(CommandForm):
    expected_status = forms.CharField(max_length=12, widget=forms.HiddenInput)
    reason = forms.CharField(label="Причина / комментарий", max_length=150, required=False)


class RevocationForm(CommandForm):
    reason = forms.CharField(label="Причина отзыва", max_length=150)


def unavailable(request, error):
    if isinstance(error, ERPForbidden): raise PermissionDenied("1С отозвала доступ.") from None
    return render(request, "portal/unavailable.html", {"reason":str(error)}, status=503)


def execute_form(request, context, form, payload, callback, redirect_name):
    try:
        send_command(request, context, form.cleaned_data["command_key"], payload, callback)
    except ValidationError as exc:
        form.add_error(None, exc)
    except ERPForbidden:
        raise PermissionDenied("1С отозвала доступ.") from None
    except (ERPConflict, ERPRejected, ERPMissing) as exc:
        messages.error(request, str(exc))
        return redirect(redirect_name)
    except ERPUnavailable as exc:
        form.add_error(None, str(exc)+" Сохранённую команду можно повторить без изменений.")
    else:
        messages.success(request, "Команда подтверждена 1С. Показано актуальное состояние.")
        return redirect(redirect_name)
    return None


@erp_roles("admin", "requester", "approver")
@command_capacity
def request_action(request, pk, action):
    if action not in {"approve", "reject", "cancel"}: raise Http404
    role = request.erp_profile["role"]
    if action in {"approve", "reject"} and role not in {"admin", "approver"}: raise PermissionDenied
    if action == "cancel" and role not in {"admin", "requester"}: raise PermissionDenied
    try: item = request.erp_client.request_detail(request.user.get_username(), str(pk))
    except ERPMissing: raise Http404 from None
    except ERPUnavailable as exc: return unavailable(request, exc)
    if role == "requester" and item["requester_login"] != request.user.get_username(): raise PermissionDenied
    if action != "cancel" and item["requester_login"] == request.user.get_username():
        raise PermissionDenied("Собственную заявку согласовывает другой пользователь.")
    context = f"request:{pk}:{action}"
    state = command_state(request, context)
    if item["status"] != "submitted" and state["payload"] is None:
        messages.info(request, "Решение по заявке уже принято.")
        return redirect("request_list")
    initial = {"expected_status":"submitted", "reason":"", **(state["payload"] or {}), "command_key":state["key"]}
    form = DecisionForm(request.POST if request.method == "POST" else None, initial=initial)
    form.fields["reason"].required = action != "approve"
    if request.method == "POST" and form.is_valid():
        payload = {"id":str(pk), "expected_status":form.cleaned_data["expected_status"], "reason":form.cleaned_data["reason"]}
        response = execute_form(request, context, form, payload,
            lambda key,data:request.erp_client.decide_request(request.user.get_username(),data["id"],action,data["expected_status"],data["reason"],key), "request_list")
        if response: return response
    labels = {"approve":"Согласовать заявку", "reject":"Отклонить заявку", "cancel":"Отменить заявку"}
    return render(request, "portal/command.html", {"form":form, "heading":labels[action], "description":item["visitor"], "pending":command_state(request, context)["payload"] is not None})


@erp_roles("admin", "requester", "approver", "guard")
def pass_list(request):
    try:
        items = request.erp_client.passes(request.user.get_username())
        if request.erp_profile["role"] == "requester" and any(row["requester_login"] != request.user.get_username() for row in items):
            raise ERPUnavailable("1С вернула пропуск другой рабочей области.")
    except ERPUnavailable as exc: return unavailable(request, exc)
    now = timezone.now()
    for item in items:
        item["state_label"] = {"active":"Действующий", "revoked":"Отозван"}[item["state"]]
        item["position_label"] = {"inside":"Внутри", "outside":"Снаружи"}[item["position"]]
        item["current"] = item["starts_at"] <= now < item["ends_at"]
    return render(request, "portal/passes.html", {"items":items, "can_operate":request.erp_profile["role"] in {"admin", "guard"}})


@erp_roles("admin", "guard")
@command_capacity
def pass_issue(request, pk):
    try: item = request.erp_client.request_detail(request.user.get_username(), str(pk))
    except ERPMissing: raise Http404 from None
    except ERPUnavailable as exc: return unavailable(request, exc)
    context = f"issue:{pk}"
    state = command_state(request, context)
    if item["status"] != "approved" and state["payload"] is None: raise PermissionDenied("Нужна согласованная заявка.")
    form = CommandForm(request.POST if request.method == "POST" else None, initial={"command_key":state["key"]})
    if request.method == "POST" and form.is_valid():
        response = execute_form(request, context, form, {"request_id":str(pk)},
            lambda key,data:request.erp_client.issue_pass(request.user.get_username(),data["request_id"],key), "pass_list")
        if response: return response
    return render(request, "portal/command.html", {"form":form, "heading":"Выдать пропуск", "description":item["visitor"], "pending":command_state(request, context)["payload"] is not None})


@erp_roles("admin", "guard")
@command_capacity
def pass_action(request, pk, action):
    if action not in {"revoke", "in", "out"}: raise Http404
    try: item = request.erp_client.pass_detail(request.user.get_username(), str(pk))
    except ERPMissing: raise Http404 from None
    except ERPUnavailable as exc: return unavailable(request, exc)
    context = f"pass:{pk}:{action}"
    state = command_state(request, context)
    initial = {**(state["payload"] or {}), "command_key":state["key"]}
    form_type = RevocationForm if action == "revoke" else CommandForm
    form = form_type(request.POST if request.method == "POST" else None, initial=initial)
    if request.method == "POST" and form.is_valid():
        if action == "revoke":
            payload = {"id":str(pk), "reason":form.cleaned_data["reason"]}
            callback = lambda key,data:request.erp_client.revoke_pass(request.user.get_username(),data["id"],data["reason"],key)
        else:
            payload = {"pass_id":str(pk), "checkpoint_id":item["checkpoint_id"], "direction":action}
            callback = lambda key,data:request.erp_client.movement(request.user.get_username(),data["pass_id"],data["checkpoint_id"],data["direction"],key)
        response = execute_form(request, context, form, payload, callback, "pass_list")
        if response: return response
    labels = {"revoke":"Отозвать пропуск", "in":"Зарегистрировать вход", "out":"Зарегистрировать выход"}
    return render(request, "portal/command.html", {"form":form, "heading":labels[action], "description":item["visitor"]+" · "+item["checkpoint"], "pending":command_state(request, context)["payload"] is not None})


@erp_roles("admin", "requester", "approver", "guard")
def event_list(request):
    try:
        items = request.erp_client.events(request.user.get_username())
        if request.erp_profile["role"] == "requester" and any(row["requester_login"] != request.user.get_username() for row in items):
            raise ERPUnavailable("1С вернула чужие события.")
    except ERPUnavailable as exc: return unavailable(request, exc)
    return render(request, "portal/events.html", {"items":items})
