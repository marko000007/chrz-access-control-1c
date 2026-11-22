from django.contrib import admin
from django.urls import include,path
from portal import views
urlpatterns = [path("",views.home,name="home"),path("dashboard/",views.dashboard,name="dashboard"),path("accounts/",include("django.contrib.auth.urls")),path("admin/",admin.site.urls)]
