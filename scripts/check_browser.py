"""Chrome acceptance of the real local portal and 1C business cycle."""
import argparse
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
            requester=signed_in('demo.requester')
            requester.goto(url+'/requests/new/')
            for name in ['visitor_id','host_id','checkpoint_id','purpose_id']:
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
            guard.goto(url+f'/passes/{pass_id}/out/')
            confirm(guard);guard.wait_for_url('**/passes/')
            assert 'Отозван' in guard.locator('tbody').inner_text() and 'Снаружи' in guard.locator('tbody').inner_text()
            checks.append('browser_revocation_and_exit');shot(guard,'passes-desktop.png')
            guard.goto(url+'/events/')
            assert guard.locator('tbody tr').count()==2
            checks.append('browser_two_events');shot(guard,'events-desktop.png')
            response=requester.goto(url+f'/requests/{identifier}/approve/')
            assert response.status==403;checks.append('browser_requester_cannot_approve')
            mobile=signed_in('demo.guard',390,844)
            for path,name in [('/passes/','passes-mobile.png'),('/events/','events-mobile.png'),('/requests/','requests-mobile.png')]:
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
