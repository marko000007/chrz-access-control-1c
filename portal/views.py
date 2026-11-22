from django.contrib.auth.decorators import login_required
from django.shortcuts import render


def home(request):
    return render(request,"portal/home.html")


@login_required
def dashboard(request):
    return render(request,"portal/dashboard.html")
