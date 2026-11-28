"""Проверка отчётов Chrome → Django → HTTP → настоящая отдельная база 1С."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading
from wsgiref.simple_server import make_server, WSGIRequestHandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def verify(base_name, output, browser_packages=None, allow_gui=False):
    if not allow_gui:
        raise SystemExit('Проверка открывает окна 1С. Требуется явный --allow-gui-1c.')
    if browser_packages:
        sys.path.append(str(browser_packages))
    from playwright.sync_api import sync_playwright
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    from django.conf import settings
    with tempfile.TemporaryDirectory(prefix='chrz-assignment-browser-') as folder:
        settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': str(Path(folder)/'portal.sqlite3')}}
        import django
        django.setup()
        from django.core.management import call_command
        from django.contrib.auth import get_user_model
        from django.contrib.staticfiles.handlers import StaticFilesHandler
        from django.core.wsgi import get_wsgi_application
        from portal.local_gateway import OneCRuntime, create_server
        from portal.integration import ERPClient, ERPForbidden
        from portal.assignment_reports import REPORTS
        call_command('migrate', interactive=False, verbosity=0)
        password = secrets.token_urlsafe(24)
        get_user_model().objects.create_user('assignment.1.guard', password=password)
        runtime = OneCRuntime(base_name, allow_gui=True)
        gateway = create_server(runtime, 'assignment-check', password)
        thread = threading.Thread(target=gateway.serve_forever, daemon=True); thread.start()
        settings.ERP_BASE_URL = f'http://127.0.0.1:{gateway.server_port}'
        settings.ERP_USERNAME = 'assignment-check'; settings.ERP_PASSWORD = password; settings.ERP_TIMEOUT = 30
        class Quiet(WSGIRequestHandler):
            def log_message(self, *args): pass
        server = make_server('127.0.0.1', 0, StaticFilesHandler(get_wsgi_application()), handler_class=Quiet)
        web = threading.Thread(target=server.serve_forever, daemon=True); web.start()
        output.mkdir(parents=True, exist_ok=True)
        checks = []
        try:
            client = ERPClient(settings.ERP_BASE_URL, settings.ERP_USERNAME, settings.ERP_PASSWORD, 30)
            try:
                client.request('GET', '/reports/assignment/AssetBalance/20261128/20261128', 'assignment.1.requester')
            except ERPForbidden: checks.append('native_requester_report_403')
            else: raise AssertionError('1С разрешила отчёт заявителю')
            with sync_playwright() as p:
                browser = p.chromium.launch(channel='chrome', headless=True)
                try:
                    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                    page.set_default_timeout(60000); page.set_default_navigation_timeout(60000)
                    errors = []; page.on('pageerror', lambda e: errors.append(str(e)))
                    url = f'http://127.0.0.1:{server.server_port}'
                    page.goto(url+'/accounts/login/')
                    page.locator('#id_username').fill('assignment.1.guard'); page.locator('#id_password').fill(password)
                    page.locator('main form button').click(); page.wait_for_url('**/dashboard/')
                    page.goto(url+'/reports/assignment/')
                    for name in REPORTS:
                        page.locator('#id_report').select_option(name)
                        page.locator('#id_start').fill('2026-11-28'); page.locator('#id_end').fill('2026-11-28')
                        page.get_by_role('button', name='Сформировать', exact=True).click()
                        page.wait_for_load_state()
                        assert page.locator('tbody tr').count() >= 10
                        assert page.locator('thead th').count() >= 3
                        checks.append('browser_native_'+name)
                    page.screenshot(path=str(output/'desktop.png'), full_page=True)
                    with page.expect_download() as download:
                        page.get_by_role('link', name='Скачать CSV').click()
                    csv_text = Path(download.value.path()).read_text(encoding='utf-8-sig')
                    assert 'ООО «ЧРЗ»' in csv_text and len(csv_text.splitlines()) >= 12
                    checks.append('browser_csv_actual_report')
                    page.emulate_media(media='print')
                    assert not page.locator('main form').is_visible()
                    checks.append('print_hides_controls')
                    page.emulate_media(media='screen'); page.set_viewport_size({'width': 390, 'height': 844})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    page.screenshot(path=str(output/'mobile.png'), full_page=True)
                    checks.append('mobile_no_page_overflow')
                    assert not errors
                finally:
                    browser.close()
        finally:
            server.shutdown(); server.server_close(); web.join(timeout=3)
            gateway.shutdown(); gateway.server_close(); thread.join(timeout=3)
    sources = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in (ROOT/'one_c/configuration').rglob('*') if p.is_file()}
    result = {'ok': True, 'checks': checks, 'source_sha256': sources,
              'limits': ['Учебная 1С, файловый адаптер с явным разрешением окон; не серверная публикация.']}
    (output/'acceptance.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print('Пройдено проверок:', len(checks))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-name', required=True)
    parser.add_argument('--output', type=Path, default=Path('reports/assignment-browser-v1'))
    parser.add_argument('--browser-packages', type=Path)
    parser.add_argument('--allow-gui-1c', action='store_true')
    args = parser.parse_args()
    verify(args.base_name, args.output, args.browser_packages, args.allow_gui_1c)
