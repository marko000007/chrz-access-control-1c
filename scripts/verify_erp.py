"""Real loopback HTTP → 1C integration in a separate owned verification base."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from portal.local_gateway import OneCRuntime, create_server
from portal.integration import ERPClient, ERPConflict, ERPForbidden


def verify(name, report_path):
    if not name.startswith('qa-'):
        raise SystemExit('Используйте отдельное имя с префиксом qa-')
    base=ROOT/'.local/1c'/name
    marker=base/'verification-base.txt'
    if base.exists() and not marker.is_file():
        raise SystemExit('Существующая база без маркера проверки не изменяется')
    def command(operation):
        subprocess.run([sys.executable,str(ROOT/'scripts/one_c.py'),operation,'--base-name',name],cwd=ROOT,check=True)
    if not base.exists():
        command('create');marker.write_text('chrz-owned-verification-base\n')
    for operation in ['load','check','smoke']:command(operation)
    runtime=OneCRuntime(name)
    assert runtime.invoke({'operation':'setup','actor':'demo.admin'})[0]==200
    password=secrets.token_urlsafe(32)
    server=create_server(runtime,'verification',password)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    client=ERPClient(f'http://127.0.0.1:{server.server_port}','verification',password,timeout=30)
    checks=[]
    try:
        assert client.health('demo.admin')['system']=='1c-enterprise';checks.append('real_1c_health')
        assert client.actor('demo.approver')['role']=='approver';checks.append('authoritative_1c_role')
        references=client.references('demo.requester')
        assert all(references.values());checks.append('real_1c_references')
        before=client.requests('demo.requester')
        start=(datetime.now(timezone.utc)-timedelta(minutes=1)).replace(microsecond=0)
        end=start+timedelta(hours=1)
        offset=timezone(timedelta(hours=4))
        payload={'visitor_id':references['visitors'][0]['id'],'host_id':references['employees'][0]['id'],
            'checkpoint_id':references['checkpoints'][0]['id'],'purpose_id':references['purposes'][0]['id'],
            'starts_at':start.astimezone(offset).isoformat(),'ends_at':end.astimezone(offset).isoformat()}
        key=str(uuid.uuid4())
        first=client.create_request('demo.requester',payload,key)
        assert first==client.create_request('demo.requester',payload,key)
        after=client.requests('demo.requester')
        assert len(after)==len(before)+1;checks.append('one_creation_after_exact_http_repeat')
        created=next(item for item in after if item['id']==first['id'])
        assert created['starts_at']==start and created['ends_at']==end;checks.append('offset_datetime_roundtrip')
        try:client.create_request('demo.requester',{**payload,'ends_at':(end+timedelta(minutes=1)).isoformat()},key)
        except ERPConflict:checks.append('changed_payload_conflict_409')
        else:raise AssertionError('Changed payload was accepted')
        try:client.create_request('demo.guard',payload,str(uuid.uuid4()))
        except ERPForbidden:checks.append('guard_cannot_create_request')
        else:raise AssertionError('Wrong role was accepted')
        foreign=client.create_request('demo.admin',payload,str(uuid.uuid4()))
        assert foreign['id'] not in {item['id'] for item in client.requests('demo.requester')};checks.append('requester_scope_isolation')
        decision={'id':first['id'],'expected_status':'submitted','reason':'Вымышленное решение проверки'}
        key=str(uuid.uuid4())
        result=client.request('POST','/requests/approve','demo.approver',decision,key)
        assert result['status']=='approved'
        assert result==client.request('POST','/requests/approve','demo.approver',decision,key);checks.append('approval_and_durable_repeat')
    finally:
        server.shutdown();server.server_close();thread.join(3)
    sources={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((ROOT/'one_c/configuration').rglob('*')) if path.is_file()}
    result={'status':'passed','data_origin':'synthetic','base_name':name,
        'transport':'Python loopback HTTP adapter -> private fixed-file RPC -> actual 1C runtime',
        'native_http_service':False,'business_rules_and_storage':'1c-enterprise',
        'checks':checks,'source_sha256':sources,
        'limitations':['Educational local file mode; not native 1C HTTP service or multiuser platform authentication.',
            'Transport fixtures are separate from these actual runtime checks.']}
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('Реальная HTTP-интеграция с локальной1С проверена:',len(checks),'проверок')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-name',default='qa-http-20261123')
    parser.add_argument('--report',type=Path,default=Path('reports/1c-http-v1.json'))
    args=parser.parse_args();verify(args.base_name,args.report.resolve())
