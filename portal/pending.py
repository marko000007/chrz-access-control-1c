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
