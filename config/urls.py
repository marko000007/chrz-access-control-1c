from django.contrib import admin
from django.urls import include,path
from portal import views
from portal.requests import request_list,request_create
from portal import workflow
from portal.request_detail import request_detail
from portal.reports import movement_report
from portal.pass_detail import pass_detail
from portal.visitors import visitor_list,visitor_create
from portal.presence import presence
from portal.lookup import lookup
from portal.pending import pending,dismiss
from portal.local_status import local_status
urlpatterns = [path("local/status/",local_status,name="local_status"),path("pending/",pending,name="pending_commands"),path("pending/<int:pk>/dismiss/",dismiss,name="dismiss_pending"),path("lookup/",lookup,name="record_lookup"),path("reports/presence/",presence,name="presence"),path("visitors/",visitor_list,name="visitor_list"),path("visitors/new/",visitor_create,name="visitor_create"),path("passes/<uuid:pk>/",pass_detail,name="pass_detail"),path("reports/movements/",movement_report,name="movement_report"),path("requests/<uuid:pk>/",request_detail,name="request_detail"),path("passes/",workflow.pass_list,name="pass_list"),path("events/",workflow.event_list,name="event_list"),path("requests/<uuid:pk>/issue/",workflow.pass_issue,name="pass_issue"),path("requests/<uuid:pk>/<slug:action>/",workflow.request_action,name="request_action"),path("passes/<uuid:pk>/<slug:action>/",workflow.pass_action,name="pass_action"),path("requests/",request_list,name="request_list"),path("requests/new/",request_create,name="request_create"),path("workspace/",views.workspace,name="workspace"),path("",views.home,name="home"),path("dashboard/",views.dashboard,name="dashboard"),path("accounts/",include("django.contrib.auth.urls")),path("admin/",admin.site.urls)]
