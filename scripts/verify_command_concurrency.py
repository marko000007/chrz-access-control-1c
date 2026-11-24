"""Изолированная файловая SQLite: параллельные технические команды без1С/RPC."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

WORKER = r'''
import json,threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection,close_old_connections
from portal.commands import command_state,send_command
from portal.integration import ERPUnavailable
from portal.models import PendingCommand
u=get_user_model().objects.create_user('concurrency-fixture')
r=SimpleNamespace(user=u)
checks=[]
def threaded(action):
    close_old_connections()
    try:return action()
    finally:close_old_connections()
for i in range(19):command_state(r,'old:'+str(i))
barrier=threading.Barrier(2)
def competing(number):
    barrier.wait(timeout=5)
    try:return command_state(r,'new:'+str(number))['key']
    except ValidationError:return 'capacity'
with ThreadPoolExecutor(max_workers=2) as pool:
    results=list(pool.map(lambda n:threaded(lambda:competing(n)),range(2)))
assert results.count('capacity')==1,results
assert PendingCommand.objects.filter(owner=u).count()==20
assert PendingCommand.objects.filter(owner=u,context__startswith='old:').count()==19
checks.append('two_connections_enforce_capacity_without_eviction')
PendingCommand.objects.all().delete()
barrier=threading.Barrier(2)
def shared():
    barrier.wait(timeout=5);return command_state(r,'same')['key']
with ThreadPoolExecutor(max_workers=2) as pool:
    results=list(pool.map(lambda n:threaded(shared),range(2)))
assert len(set(results))==1 and PendingCommand.objects.count()==1
checks.append('two_connections_share_one_context_and_uuid')
entered=threading.Event();released=threading.Event()
def uncertain(key,payload):
    assert not connection.in_atomic_block and connection.get_autocommit()
    entered.set();assert released.wait(5)
    raise ERPUnavailable('Explicit simulated lost response; no native invocation')
def first():
    try:send_command(r,'same',results[0],{'reason':'original'},uncertain)
    except ERPUnavailable:return 'unknown'
with ThreadPoolExecutor(max_workers=2) as pool:
    future=pool.submit(threaded,first)
    try:
        assert entered.wait(5)
        try:
            threaded(lambda:send_command(r,'same',results[0],{'reason':'changed'},lambda *args:(_ for _ in ()).throw(AssertionError('second callback reached'))))
        except ValidationError:pass
        else:raise AssertionError('changed payload was accepted')
    finally:released.set()
    assert future.result(timeout=5)=='unknown'
assert command_state(r,'same')['payload']=={'reason':'original'}
checks.extend(['changed_payload_blocked_while_first_response_unknown','callback_runs_after_sqlite_commit'])
assert connection.settings_dict['OPTIONS']['transaction_mode']=='IMMEDIATE'
print(json.dumps({'status':'passed','checks':checks,'backend':'isolated file SQLite','native_1c_execution':False,'rpc_requests':0}))
'''


def verify(app_python,output):
    root=Path(__file__).resolve().parents[1]
    app_python=Path(os.path.abspath(app_python));sources={}
    names=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
    with tempfile.TemporaryDirectory(prefix='portal-concurrency-') as folder:
        target=Path(folder)
        for name in filter(None,names):
            source=root/name
            if source.is_symlink():raise RuntimeError('Source symlink')
            destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
            sources[name]=hashlib.sha256(source.read_bytes()).hexdigest()
        env={k:v for k,v in os.environ.items() if k not in {'PYTHONPATH','PYTHONHOME','ONE_C_ALLOW_GUI'}}
        env.update(ERP_BASE_URL='',ERP_USERNAME='',ERP_PASSWORD='')
        def run(*args):
            result=subprocess.run([str(app_python),'main.py',*args],cwd=target,env=env,text=True,capture_output=True,timeout=45)
            if result.returncode:raise RuntimeError(result.stdout+result.stderr)
            return result.stdout
        run('migrate','--noinput')
        result=json.loads(run('shell','-c',WORKER).splitlines()[-1])
    result['source_sha256']=sources
    result['limitations']=['Technical queue concurrency only. No business-data simulation, native platform launch or native acceptance.']
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('File SQLite concurrency passed:',len(result['checks']),'checks')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-python',default='.venv/bin/python')
    parser.add_argument('--output',type=Path,default=Path('reports/queue-concurrency-v1.json'))
    args=parser.parse_args();verify(args.app_python,args.output)
