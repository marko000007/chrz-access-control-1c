"""Chrome acceptance of the real local portal and 1C business cycle."""
import argparse
import csv
import io
from datetime import datetime, timedelta
import json
from importlib.metadata import version
from pathlib import Path
import re
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright


def check(url, accounts_path, output):
    accounts=json.loads(accounts_path.read_text())
    output.mkdir(parents=True,exist_ok=True)
    checks=[];screens=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        contexts=[]
        def signed_in(name, width=1440, height=1000):
            context=browser.new_context(viewport={'width':width,'height':height},locale='ru-RU',timezone_id='Asia/Tbilisi')
            contexts.append(context)
            page=context.new_page();page.set_default_timeout(60000);page.set_default_navigation_timeout(60000)
            page.goto(url+'/accounts/login/')
            page.locator('#id_username').fill(name);page.locator('#id_password').fill(accounts[name])
            page.locator('main form button').click()
            page.wait_for_url('**/dashboard/')
            return page
        def confirm(page):
            page.get_by_role('button',name='Подтвердить',exact=True).click()
        def shot(page,name):
            page.screenshot(path=str(output/name),full_page=True);screens.append(name)
        try:
            administrator=signed_in('demo.admin')
            administrator.goto(url+'/visitors/new/')
            administrator.locator('#id_name').fill('Браузерный вымышленный посетитель')
            administrator.locator('#id_company').fill('Учебная организация браузерной проверки')
            administrator.get_by_role('button',name='Записать в справочник',exact=True).click();administrator.wait_for_url('**/visitors/')
            visitor=administrator.locator('article').filter(has=administrator.get_by_role('heading',name='Браузерный вымышленный посетитель',exact=True))
            visitor_id=visitor.locator('.record-id').inner_text().strip()
            assert re.fullmatch(r'[a-f0-9-]{36}',visitor_id);checks.append('browser_native_visitor_created_by_admin')
            requester=signed_in('demo.requester')
            requester.goto(url+'/requests/new/')
            requester.locator('#id_visitor_id').select_option(visitor_id)
            for name in ['host_id','checkpoint_id','purpose_id']:
                requester.locator('#id_'+name).select_option(index=1)
            now=datetime.now(ZoneInfo('Asia/Tbilisi'))
            requester.locator('#id_starts_at').fill((now-timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M'))
            requester.locator('#id_ends_at').fill((now+timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M'))
            requester.get_by_role('button',name='Отправить на согласование',exact=True).click()
            requester.wait_for_url('**/requests/')
            cancel=requester.locator('tbody tr').first.locator('a[href$="/cancel/"]').get_attribute('href')
            identifier=re.search(r'/requests/([a-f0-9-]+)/',cancel).group(1)
            checks.append('browser_request_created_in_real_1c')
            shot(requester,'requests-desktop.png')
            approver=signed_in('demo.approver')
            approver.goto(url+f'/requests/{identifier}/approve/')
            approver.locator('#id_reason').fill('Вымышленное согласование браузерной проверки')
            confirm(approver);approver.wait_for_url('**/requests/')
            checks.append('browser_approval')
            requester.goto(url+f'/requests/{identifier}/')
            assert 'Вымышленное согласование браузерной проверки' in requester.locator('main').inner_text()
            checks.append('browser_request_decision_card');shot(requester,'request-card-desktop.png')
            guard=signed_in('demo.guard')
            guard.goto(url+f'/requests/{identifier}/issue/')
            confirm(guard);guard.wait_for_url('**/passes/')
            pass_id=guard.locator('tbody tr').first.locator('small').inner_text().strip()
            assert re.fullmatch(r'[a-f0-9-]{36}',pass_id)
            checks.append('browser_pass_issue')
            guard.goto(url+f'/passes/{pass_id}/in/')
            confirm(guard);guard.wait_for_url('**/passes/')
            assert 'Внутри' in guard.locator('tbody').inner_text();checks.append('browser_entry')
            guard.goto(url+f'/passes/{pass_id}/revoke/')
            guard.locator('#id_reason').fill('Вымышленный отзыв браузерной проверки')
            confirm(guard);guard.wait_for_url('**/passes/')
            guard.goto(url+'/reports/presence/')
            assert 'Внутри: 1' in guard.locator('main').inner_text() and 'Отозванных: 1' in guard.locator('main').inner_text()
            assert 'Браузерный вымышленный посетитель' in guard.locator('tbody').inner_text()
            shot(guard,'presence-desktop.png')
            with guard.expect_download() as result:guard.get_by_role('link',name='Скачать снимок CSV',exact=True).click()
            presence_csv=output/'presence-browser.csv';result.value.save_as(presence_csv)
            presence=list(csv.DictReader(io.StringIO(presence_csv.read_text(encoding='utf-8-sig')),delimiter=';'))
            assert len(presence)==2 and presence[0]['Всего внутри']=='1' and presence[1]['Статус пропуска']=='Отозван'
            checks.append('browser_revoked_inside_presence_and_csv')
            guard.set_viewport_size({'width':390,'height':844})
            assert guard.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1')
            shot(guard,'presence-mobile.png');guard.set_viewport_size({'width':1440,'height':1000})
            guard.goto(url+f'/passes/{pass_id}/out/')
            confirm(guard);guard.wait_for_url('**/passes/')
            assert 'Отозван' in guard.locator('tbody').inner_text() and 'Снаружи' in guard.locator('tbody').inner_text()
            checks.append('browser_revocation_and_exit');shot(guard,'passes-desktop.png')
            guard.goto(url+'/reports/presence/');assert 'Внутри: 0' in guard.locator('main').inner_text()
            assert requester.goto(url+'/reports/presence/').status==403
            checks.append('browser_presence_exit_and_role_403')
            guard.goto(url+'/events/')
            assert guard.locator('tbody tr').count()==2
            checks.append('browser_two_events');shot(guard,'events-desktop.png')
            guard.goto(url+f'/passes/{pass_id}/')
            assert 'Вымышленный отзыв браузерной проверки' in guard.locator('main').inner_text()
            checks.append('browser_pass_revocation_card');shot(guard,'pass-card-desktop.png')
            guard.set_viewport_size({'width':794,'height':1123});guard.emulate_media(media='print')
            guard.pdf(path=str(output/'pass-print.pdf'),format='A4',print_background=True,prefer_css_page_size=True)
            guard.locator('.pass-paper').screenshot(path=str(output/'pass-print-preview.png'));screens.append('pass-print-preview.png')
            guard.emulate_media(media='screen');guard.set_viewport_size({'width':1440,'height':1000})
            checks.append('browser_print_media_preview')
            first=now.astimezone(ZoneInfo('UTC')).date().isoformat();last=datetime.now(ZoneInfo('UTC')).date().isoformat()
            period=f'/reports/movements/?start={first}&end={last}'
            guard.goto(url+period);assert guard.locator('tbody tr').count()==2;shot(guard,'report-desktop.png')
            with guard.expect_download() as result:guard.get_by_role('link',name='Скачать журнал CSV',exact=True).click()
            exported=output/'events-browser.csv';result.value.save_as(exported)
            rows=list(csv.DictReader(io.StringIO(exported.read_text(encoding='utf-8-sig')),delimiter=';'))
            assert len(rows)==2 and {row['Направление'] for row in rows}=={'Вход','Выход'}
            checks.append('browser_native_period_report_and_csv')
            assert requester.goto(url+period).status==403;checks.append('browser_report_role_403')
            response=requester.goto(url+f'/requests/{identifier}/approve/')
            assert response.status==403;checks.append('browser_requester_cannot_approve')
            mobile=signed_in('demo.guard',390,844)
            for path,name in [('/passes/','passes-mobile.png'),('/events/','events-mobile.png'),('/requests/','requests-mobile.png'),(period,'report-mobile.png'),(f'/passes/{pass_id}/','pass-card-mobile.png'),(f'/requests/{identifier}/','request-card-mobile.png')]:
                mobile.goto(url+path)
                dimensions=mobile.evaluate('({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth})')
                assert dimensions['scroll']<=dimensions['width']+1,(path,dimensions)
                cells=mobile.locator('tbody td').evaluate_all('(cells)=>cells.map(cell=>({left:cell.getBoundingClientRect().left,right:cell.getBoundingClientRect().right}))')
                assert all(cell['left']>=0 and cell['right']<=dimensions['width']+1 for cell in cells),(path,cells)
                shot(mobile,name)
            checks.append('mobile_390_no_document_overflow')
            result={'status':'passed','playwright_version':version('playwright'),'browser':'Chrome '+browser.version,'viewports':[[1440,1000],[390,844]],
                'backend':'actual 1C via local adapter','checks':checks,'screenshots':screens,
                'limits':['Only the bundled simulated scenario and Chrome; not a full cross-browser or accessibility audit.']}
            (output/'browser.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
            print('Chrome local acceptance passed:',len(checks),'checks')
        finally:
            for context in contexts:context.close()
            browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True)
    parser.add_argument('--accounts',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();check(args.url,args.accounts,args.output)
