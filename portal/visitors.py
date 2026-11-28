from django import forms
from django.shortcuts import render
from .permissions import erp_roles
from .commands import command_capacity,command_state
from .workflow import CommandForm,execute_form,unavailable
from .integration import ERPUnavailable


class VisitorForm(CommandForm):
    name=forms.CharField(label="ФИО посетителя",max_length=150)
    company=forms.CharField(label="Организация посетителя",max_length=150,required=False)

    def clean(self):
        values=super().clean()
        if any(any(char in value for char in "\n\r\t") for key,value in values.items() if key in {"name","company"}):
            raise forms.ValidationError("Уберите управляющие символы из ФИО и организации.")
        return values


class VisitorSearchForm(forms.Form):
    q=forms.CharField(label='ФИО, организация или ID содержит',max_length=150,required=False)


@erp_roles("admin","requester","approver","guard")
def visitor_list(request):
    form=VisitorSearchForm(request.GET)
    if not form.is_valid():return render(request,'portal/visitors.html',{'form':form,'items':[]},status=400)
    try:items=request.erp_client.references(request.user.get_username())["visitors"]
    except ERPUnavailable as exc:return unavailable(request,exc)
    total=len(items);query=form.cleaned_data['q'].casefold()
    if query:items=[row for row in items if any(query in row.get(key,'').casefold() for key in ['name','company','id'])]
    return render(request,'portal/visitors.html',{'items':items,'form':form,'source_count':total,'found':len(items),
        'can_create':request.erp_profile['role']=='admin'})


@erp_roles("admin")
@command_capacity
def visitor_create(request):
    context="visitor:create";state=command_state(request,context)
    form=VisitorForm(request.POST if request.method=="POST" else None,initial={**(state["payload"] or {}),"command_key":state["key"]})
    if request.method=="POST" and form.is_valid():
        response=execute_form(request,context,form,{key:form.cleaned_data[key] for key in ["name","company"]},
            lambda key,data:request.erp_client.create_visitor(request.user.get_username(),data,key),"visitor_list")
        if response:return response
    return render(request,"portal/visitor_form.html",{"form":form,"pending":command_state(request,context)["payload"] is not None})
