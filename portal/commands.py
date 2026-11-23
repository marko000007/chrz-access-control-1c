"""Сохраняет точную команду до отправки; подтверждённый отказ освобождает форму."""
import hmac
from functools import wraps
from django.core.exceptions import ValidationError
from django.http import HttpResponseBadRequest
from .integration import ERPConflict, ERPForbidden, ERPRejected
from .models import PendingCommand


def command_capacity(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except ValidationError as exc:
            return HttpResponseBadRequest(" ".join(exc.messages), content_type="text/plain; charset=utf-8")
    return wrapped


def command_state(request, context):
    record = PendingCommand.objects.filter(owner=request.user, context=context).first()
    if record is None:
        if PendingCommand.objects.filter(owner=request.user).count() >= 20:
            unused = PendingCommand.objects.filter(owner=request.user, payload__isnull=True).order_by("created_at").first()
            if unused is None:
                raise ValidationError("Сначала завершите ранее отправленные команды.")
            unused.delete()
        record, created = PendingCommand.objects.get_or_create(owner=request.user, context=context)
    return {"key":str(record.key), "payload":record.payload}


def clear_command(request, context, key):
    PendingCommand.objects.filter(owner=request.user, context=context, key=key).delete()


def send_command(request, context, key, payload, callback):
    state = command_state(request, context)
    if not hmac.compare_digest(str(key), state["key"]):
        raise ValidationError("Форма устарела. Откройте действие заново.")
    PendingCommand.objects.filter(owner=request.user, context=context, key=state["key"], payload__isnull=True).update(payload=payload)
    record = PendingCommand.objects.filter(owner=request.user, context=context, key=state["key"]).first()
    if record is None:
        raise ValidationError("Команда уже подтверждена. Обновите список.")
    if record.payload != payload:
        raise ValidationError("Результат предыдущей команды не подтверждён. Повторите её без изменений.")
    try:
        result = callback(state["key"], payload)
    except (ERPConflict, ERPForbidden, ERPRejected):
        clear_command(request, context, state["key"])
        raise
    clear_command(request, context, state["key"])
    return result
