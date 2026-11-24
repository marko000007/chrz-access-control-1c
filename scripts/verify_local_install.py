"""Build an isolated copy, install dependencies, create empty 1C, and exercise Chrome."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen
import venv

ROOT=Path(__file__).resolve().parents[1]


def verify(report_path, browser_python, allow_gui=False):
    if not allow_gui:raise SystemExit("Нативная установка отключена: она открывает окна1С. Автоматически не запускать.")
    names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    sources={}
    screenshots=report_path.parent/report_path.stem.replace('local-install','local-visual')
    with tempfile.TemporaryDirectory(prefix='chrz-install-') as folder:
        target=Path(folder)
        for name in filter(None,names):
            source=ROOT/name
            if source.is_symlink():raise RuntimeError('Комплект требует проверки символической ссылки')
            destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
            sources[name]=hashlib.sha256(source.read_bytes()).hexdigest()
        venv.EnvBuilder(with_pip=True).create(target/'.venv')
        python=target/'.venv/bin/python'
        env={key:value for key,value in os.environ.items() if key not in {'ERP_BASE_URL','ERP_USERNAME','ERP_PASSWORD','ERP_TIMEOUT','DATABASE_URL','DEBUG','SECRET_KEY','DJANGO_SETTINGS_MODULE','PYTHONPATH','PYTHONHOME'}}
        with (target/'acceptance.log').open('w+') as log:
            def run(*args, timeout=180):
                completed=subprocess.run([str(python),*args],cwd=target,env=env,stdout=log,stderr=log,timeout=timeout)
                if completed.returncode:
                    log.seek(0);raise RuntimeError(log.read()[-5000:])
            run('-m','pip','install','-r','requirements.txt')
            run('-m','pip','check')
            run('main.py','test','tests','--verbosity','1')
            run('run_local.py','--setup-demo','--check','--allow-gui-1c')
            run('main.py','makemigrations','--check','--dry-run')
            with socket.socket() as listener:
                listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
            server=subprocess.Popen([str(python),str(target/'run_local.py'),'--allow-gui-1c','--port',str(port)],cwd=ROOT.parent,env=env,stdout=log,stderr=log)
            try:
                deadline=time.monotonic()+30
                while True:
                    try:
                        with urlopen(f'http://127.0.0.1:{port}/',timeout=2) as response:assert response.status==200
                        break
                    except (URLError,TimeoutError):
                        if server.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Локальный портал не запустился')
                        time.sleep(.2)
                with urlopen(f'http://127.0.0.1:{port}/static/portal/app.css',timeout=3) as response:assert response.status==200
                completed=subprocess.run([str(browser_python),str(ROOT/'scripts/check_browser.py'),'--url',f'http://127.0.0.1:{port}',
                    '--accounts',str(target/'.local/demo-accounts.json'),'--allow-gui-1c','--output',str(screenshots)],cwd=target,env=env,stdout=log,stderr=log,timeout=420)
                if completed.returncode:
                    log.seek(0);raise RuntimeError(log.read()[-6000:])
            finally:
                server.terminate()
                try:server.wait(timeout=15)
                except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
            log.seek(0);transcript=log.read()
        versions=subprocess.check_output([str(python),'-m','pip','freeze'],cwd=target,env=env,text=True).splitlines()
    result={'status':'passed','source_sha256':sources,'dependencies':versions,'python':sys.version,
        'checks':['isolated_venv','empty_technical_database','full_test_suite','empty_1c_build','actual_1c_setup','loopback_http_css','chrome_business_cycle','mobile_layout'],
        'browser':json.loads((screenshots/'browser.json').read_text()),'verification_log_tail':transcript[-1700:],
        'limits':['Educational file-mode adapter; not native 1C HTTP service or multiuser 1C authentication.','Chrome acceptance does not cover every screen or all browsers.']}
    report_path.parent.mkdir(parents=True,exist_ok=True);report_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('Чистая локальная установка и браузерный цикл проверены:',report_path)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,default=Path('reports/local-install-v1.json'))
    parser.add_argument('--browser-python',type=Path,required=True,help='Python с Playwright и доступным каналом Chrome')
    parser.add_argument("--allow-gui-1c",action="store_true")
    args=parser.parse_args();verify(args.report.resolve(),Path(os.path.abspath(args.browser_python)),args.allow_gui_1c)
