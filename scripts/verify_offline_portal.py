"""Проверка только локальных технических страниц;1С и RPC не используются."""
import argparse,hashlib,json,os,secrets,shutil,socket,subprocess,tempfile,time
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError
from importlib.metadata import version
from playwright.sync_api import sync_playwright


def verify(app_python,output):
    root=Path(__file__).resolve().parents[1];app_python=Path(os.path.abspath(app_python));output.mkdir(parents=True,exist_ok=True)
    names=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0');sources={};checks=[];screens=[]
    password=secrets.token_urlsafe(24)
    env={key:value for key,value in os.environ.items() if key not in {'ERP_BASE_URL','ERP_USERNAME','ERP_PASSWORD','DATABASE_URL','SECRET_KEY','DJANGO_SETTINGS_MODULE','PYTHONPATH','PYTHONHOME'}}
    env.update(DEBUG='1',ALLOWED_HOSTS='127.0.0.1,localhost,testserver',ONE_C_ALLOW_GUI='0',ONE_C_BINARY='/no-platform-is-used-in-this-test')
    with tempfile.TemporaryDirectory(prefix='chrz-offline-') as folder:
        target=Path(folder)
        for name in filter(None,names):
            source=root/name
            if source.is_symlink():raise RuntimeError('Symlink in kit')
            destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
            sources[name]=hashlib.sha256(source.read_bytes()).hexdigest()
        def run(*args,input=None):
            return subprocess.run([str(app_python),*args],cwd=target,env=env,text=True,input=input,capture_output=True,check=True,timeout=60).stdout
        run('main.py','migrate','--noinput')
        seed="""import json,sys;from django.contrib.auth import get_user_model;from portal.models import PendingCommand;pwd=json.load(sys.stdin)['password'];u=get_user_model().objects.create_user('offline.operator',password=pwd,is_staff=True);o=get_user_model().objects.create_user('offline.other');PendingCommand.objects.create(owner=u,context='visitor:create');PendingCommand.objects.create(owner=u,context='request:new',payload={'secret':'RAW_PAYLOAD_NOT_PUBLIC'});PendingCommand.objects.create(owner=o,context='visitor:create',payload={'name':'FOREIGN_NOT_PUBLIC'})"""
        run('main.py','shell','-c',seed,input=json.dumps({'password':password}))
        with socket.socket() as listener:listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
        url=f'http://127.0.0.1:{port}'
        with (target/'server.log').open('w') as log:
            server=subprocess.Popen([str(app_python),str(target/'main.py'),'runserver',f'127.0.0.1:{port}','--noreload'],cwd=target,env=env,stdout=log,stderr=log)
            try:
                deadline=time.monotonic()+20
                while True:
                    try:
                        with urlopen(url,timeout=2) as response:assert response.status==200
                        break
                    except (URLError,TimeoutError):
                        if server.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Local portal failed')
                        time.sleep(.1)
                with sync_playwright() as p:
                    browser=p.chromium.launch(channel='chrome',headless=True)
                    context=browser.new_context(viewport={'width':1440,'height':1000},locale='ru-RU',timezone_id='Asia/Tbilisi')
                    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                    def visit(path):
                        response=page.goto(url+path);assert response.status==200,(path,response.status)
                    def shot(name):page.screenshot(path=str(output/name),full_page=True);screens.append(name)
                    page.goto(url+'/accounts/login/?next=/local/status/')
                    page.locator('#id_username').fill('offline.operator');page.locator('#id_password').fill(password)
                    page.locator('main form button').click();page.wait_for_url('**/local/status/')
                    assert 'Автоматический запуск окон1С отключён' in page.locator('main').inner_text()
                    checks.append('staff_status_without_native_connection');shot('local-status-desktop.png')
                    visit('/lookup/')
                    page.locator('#id_kind').select_option('pass');page.locator('#id_identifier').fill('not-a-uuid')
                    page.get_by_role('button',name='Открыть карточку',exact=True).click();assert page.locator('.errorlist').count()>0
                    checks.append('lookup_invalid_uuid_stays_local');visit('/lookup/');shot('lookup-desktop.png')
                    page.get_by_role('link',name='Незавершённые действия',exact=True).click();page.wait_for_url('**/pending/')
                    text=page.locator('main').inner_text();assert 'RAW_PAYLOAD_NOT_PUBLIC' not in text and 'FOREIGN_NOT_PUBLIC' not in text
                    assert 'Ожидают подтверждения результата: 1' in text
                    checks.append('own_pending_metadata_without_payload');shot('pending-desktop.png')
                    page.get_by_role('button',name='Убрать неотправленную форму',exact=True).click();page.wait_for_url('**/pending/')
                    assert page.get_by_role('button',name='Убрать неотправленную форму',exact=True).count()==0
                    assert 'Ожидает подтверждения результата' in page.locator('main').inner_text()
                    checks.append('dismiss_only_unsent_form')
                    run('main.py','shell','-c',"from portal.models import PendingCommand;assert PendingCommand.objects.filter(owner__username='offline.operator').count()==1;assert PendingCommand.objects.filter(owner__username='offline.other').count()==1")
                    page.set_viewport_size({'width':390,'height':844})
                    for path,name in [('/local/status/','local-status-mobile.png'),('/lookup/','lookup-mobile.png'),('/pending/','pending-mobile.png')]:
                        visit(path);assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1');shot(name)
                    checks.append('mobile_390_no_document_overflow');assert not errors,errors;checks.append('no_browser_page_errors')
                    browser_version=browser.version;context.close();browser.close()
            finally:
                server.terminate()
                try:server.wait(timeout=10)
                except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
    result={'status':'passed','browser':'Chrome '+browser_version,'playwright':version('playwright'),'checks':checks,'screenshots':screens,
            'source_sha256':sources,'viewports':[[1440,1000],[390,844]],'native_1c_executed':False,
            'limitations':['Only technical Django pages with fictional local users and pending commands. This does not verify new native 1C behavior or replace the earlier actual-runtime checks.']}
    (output/'browser.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('Offline local pages passed:',len(checks),'checks; native 1C not used')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--app-python',default='.venv/bin/python');parser.add_argument('--output',type=Path,default=Path('reports/local-offline-v1'))
    args=parser.parse_args();verify(args.app_python,args.output.resolve())
