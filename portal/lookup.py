"""Открытие известной карточки без поиска в последних ста записях."""
from django import forms
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect,render


class LookupForm(forms.Form):
    kind=forms.ChoiceField(label='Тип записи',choices=[('request','Заявка'),('pass','Пропуск')])
    identifier=forms.UUIDField(label='ID записи',help_text='UUID из карточки, журнала или ранее сохранённой ссылки.')


@login_required
def lookup(request):
    form=LookupForm(request.POST if request.method=='POST' else None)
    if request.method=='POST' and form.is_valid():
        route='request_detail' if form.cleaned_data['kind']=='request' else 'pass_detail'
        return redirect(route,pk=form.cleaned_data['identifier'])
    return render(request,'portal/lookup.html',{'form':form})
