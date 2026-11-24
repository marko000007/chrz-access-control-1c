"""Сначала устойчиво фиксирует точную команду; сетевой обмен выполняется без блокировки БД."""
import hmac
import json
from uuid import UUID
from functools import wraps
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpResponseBadRequest
from .integration import ERPConflict, ERPForbidden, ERPRejected
from .models import PendingCommand
from .command_lock import sending_slot

LIMIT=20


def command_capacity(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except ValidationError as exc:
            return HttpResponseBadRequest(" ".join(exc.messages), content_type="text/plain; charset=utf-8")
    return wrapped


def lock_owner(user):
    if not get_user_model().objects.select_for_update().get(pk=user.pk).is_active:
        raise PermissionDenied('Учётная запись отключена.')


def canonical_payload(payload):
    if not isinstance(payload,dict):raise ValidationError('Команда должна быть JSON-объектом.')
    try:
        if any(not isinstance(key,str) for key in payload):raise ValueError
        value=json.dumps(payload,sort_keys=True,allow_nan=False,ensure_ascii=False)
        if len(value.encode('utf-8'))>128*1024:raise ValueError
    except (ValueError,TypeError,OverflowError,RecursionError):
        raise ValidationError('Некорректная или слишком большая сохранённая команда. Она не отправлена.') from None
    return value


def locked_record(request,context):
    if not isinstance(context,str) or not 1<=len(context)<=100 or any(ord(c)<32 for c in context):
        raise ValidationError('Некорректный контекст формы.')
    record=PendingCommand.objects.filter(owner=request.user,context=context).first()
    if record is None:
        if PendingCommand.objects.filter(owner=request.user).count()>=LIMIT:
            raise ValidationError('Достигнут предел 20 форм. Завершите отправленные команды или уберите неотправленные на странице «Неподтверждённые команды».')
        record=PendingCommand.objects.create(owner=request.user,context=context)
    if record.payload is not None:canonical_payload(record.payload)
    return record


@transaction.atomic
def command_state(request, context):
    lock_owner(request.user)
    record=locked_record(request,context)
    return {'key':str(record.key),'payload':record.payload}


@transaction.atomic
def clear_command(request, context, key):
    get_user_model().objects.select_for_update().get(pk=request.user.pk)
    PendingCommand.objects.filter(owner=request.user, context=context, key=key).delete()


@transaction.atomic
def prepare_command(request,context,key,payload):
    lock_owner(request.user)
    try:key=str(UUID(str(key)))
    except (ValueError,TypeError,AttributeError):
        raise ValidationError('Некорректный ключ команды. Откройте действие заново.') from None
    encoded=canonical_payload(payload)
    record=locked_record(request,context)
    if not hmac.compare_digest(key,str(record.key)):
        raise ValidationError('Форма устарела. Откройте действие заново.')
    unknown_before_retry=record.payload is not None
    if unknown_before_retry and canonical_payload(record.payload)!=encoded:
        raise ValidationError('Результат предыдущей команды не подтверждён. Повторите её без изменений.')
    if record.payload is None:
        record.payload=payload
        record.save(update_fields=['payload'])
    # Сохраняем и порядок полей первоначального тела:1С сверяет SHA точного JSON.
    return str(record.key),record.payload,unknown_before_retry


def send_command(request, context, key, payload, callback):
    with sending_slot(request.user):
        frozen_key,frozen_payload,unknown_before_retry=prepare_command(request,context,key,payload)
        try:
            result=callback(frozen_key,frozen_payload)
        except (ERPConflict, ERPForbidden, ERPRejected):
            # Любой текущий отказ не устанавливает исход предыдущей потерянной попытки.
            if not unknown_before_retry:
                clear_command(request,context,frozen_key)
            raise
        clear_command(request,context,frozen_key)
        return result
