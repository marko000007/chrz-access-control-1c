"""Локальная диагностика файлов и режима обмена без запуска платформы и RPC."""
import json
import os
from pathlib import Path
import re
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from .local_gateway import ROOT,DEFAULT_BINARY,gui_launch_enabled


def collect_status(root=ROOT):
    root=Path(root);config_path=root/'.local/local-erp.json'
    configured=config_path.is_file();valid=False;base_name=None
    if configured:
        try:
            if config_path.stat().st_size>65536:raise ValueError
            config=json.loads(config_path.read_text())
            base=config.get('base_name')
            if not isinstance(base,str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,39}',base):raise ValueError
            if any(not isinstance(config.get(key),str) or not config[key] for key in ['username','password']):raise ValueError
            if type(config.get('port')) is not int or not 0<=config['port']<=65535:raise ValueError
            valid=True;base_name=base
        except (OSError,ValueError,TypeError,AttributeError):
            pass
    return {'configuration_exists':configured,'configuration_valid':valid,'base_name':base_name,
            'database_file_exists':bool(valid and (root/'.local/1c'/base_name/'1Cv8.1CD').is_file()),
            'platform_file_exists':Path(os.getenv('ONE_C_BINARY',str(DEFAULT_BINARY))).is_file(),
            'gui_enabled':gui_launch_enabled(),'native_connection_tested':False}


@login_required
def local_status(request):
    if not request.user.is_staff:raise PermissionDenied
    response=render(request,'portal/local_status.html',{'status':collect_status()})
    response['Cache-Control']='private, no-store'
    return response
