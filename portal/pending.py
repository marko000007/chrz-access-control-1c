"""Локальные неподтверждённые команды; просмотр не запускает1С."""
from uuid import UUID
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect,render
from django.urls import reverse
from .models import PendingCommand


def resume_link(context):
    if context=='request:new':return reverse('request_create'),'Создание заявки'
    if context=='visitor:create':return reverse('visitor_create'),'Создание посетителя'
    parts=context.split(':')
    try:
        if len(parts)==2 and parts[0]=='issue':
            return reverse('pass_issue',args=[UUID(parts[1])]),'Выдача пропуска'
        if len(parts)==3 and parts[0]=='request' and parts[2] in {'approve','reject','cancel'}:
            return reverse('request_action',args=[UUID(parts[1]),parts[2]]),'Решение по заявке'
        if len(parts)==3 and parts[0]=='pass' and parts[2] in {'in','out','revoke'}:
            return reverse('pass_action',args=[UUID(parts[1]),parts[2]]),'Действие с пропуском'
    except (ValueError,AttributeError):
        pass
    return None,'Неизвестный контекст старой формы'


class DismissForm(forms.Form):
    key=forms.UUIDField(widget=forms.HiddenInput)


@login_required
def pending(request):
    rows=[]
    for item in PendingCommand.objects.filter(owner=request.user).order_by('created_at','pk'):
        link,label=resume_link(item.context)
        rows.append({'item':item,'url':link,'label':label,'awaiting':item.payload is not None})
    return render(request,'portal/pending.html',{'rows':rows,'awaiting':sum(row['awaiting'] for row in rows)})


@login_required
def dismiss(request,pk):
    if request.method!='POST':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['POST'])
    record=PendingCommand.objects.filter(owner=request.user,pk=pk).first()
    if record is None:raise Http404
    form=DismissForm(request.POST)
    if not form.is_valid():
        messages.error(request,'Некорректная форма удаления. Обновите список.')
    else:
        removed,_=PendingCommand.objects.filter(owner=request.user,pk=pk,key=form.cleaned_data['key'],payload__isnull=True).delete()
        if removed:messages.success(request,'Неотправленная форма убрана. Учёт в1С не менялся.')
        else:messages.error(request,'Форма изменилась или ожидает подтверждения результата. Она сохранена для безопасного повтора.')
    return redirect('pending_commands')


@login_required
def export_pending(request):
    """Личный диагностический снимок; не подтверждение выполнения и не импорт команд."""
    import hashlib
    from django.db import transaction
    from django.http import JsonResponse
    from django.utils import timezone
    from .commands import canonical_payload,lock_owner,LIMIT
    from django.core.exceptions import ValidationError
    with transaction.atomic():
        lock_owner(request.user)
        items=list(PendingCommand.objects.filter(owner=request.user).order_by('created_at','pk')[:LIMIT+1])
        if len(items)>LIMIT:
            return JsonResponse({'error':'Очередь превышает предел20. Частичная выгрузка не формируется.'},status=409)
        rows=[]
        try:
            for item in items:
                payload_hash=hashlib.sha256(canonical_payload(item.payload).encode('utf-8')).hexdigest() if item.payload is not None else None
                rows.append({'context':item.context,'key':str(item.key),'created_at':item.created_at.isoformat(),
                    'state':'unknown' if item.payload is not None else 'draft','payload':item.payload,'payload_sha256':payload_hash})
        except ValidationError:
            return JsonResponse({'error':'Повреждено содержимое одной из команд. Очередь сохранена; выгрузка не сформирована.'},status=409)
    response=JsonResponse({'schema_version':1,'actor':request.user.get_username(),'generated_at':timezone.now().isoformat(),
        'hash_method':'SHA-256 of UTF-8 JSON with sorted keys; diagnostic representation, not the original wire bytes.',
        'execution_status':'Unknown commands are not proof of execution or rejection in 1C. Export does not send or cancel commands.',
        'commands':rows},json_dumps_params={'ensure_ascii':False})
    response['Content-Disposition']='attachment; filename="pending-commands.json"'
    response['Cache-Control']='private, no-store'
    response['X-Content-Type-Options']='nosniff'
    return response
