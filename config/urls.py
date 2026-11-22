from django.contrib import admin
from django.urls import include,path
from portal import views
from portal.requests import request_list,request_create
urlpatterns = [path("requests/",request_list,name="request_list"),path("requests/new/",request_create,name="request_create"),path("workspace/",views.workspace,name="workspace"),path("",views.home,name="home"),path("dashboard/",views.dashboard,name="dashboard"),path("accounts/",include("django.contrib.auth.urls")),path("admin/",admin.site.urls)]
