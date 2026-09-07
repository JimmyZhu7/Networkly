"""Read-only browser check for Save pending/success/failure feedback.

Set NETWORKLY_BASE_URL and NETWORKLY_BROWSER_AUTH (Playwright storage-state path).
All tracking POSTs are intercepted; no opportunity is saved by this check.
"""
import asyncio,json,os
from playwright.async_api import async_playwright
async def main():
 results=[]
 async with async_playwright() as p:
  for engine in ('chromium','webkit'):
   b=await getattr(p,engine).launch()
   for status in (200,500):
    c=await b.new_context(storage_state=os.environ['NETWORKLY_BROWSER_AUTH']);page=await c.new_page()
    async def intercept(route):
     await asyncio.sleep(.8)
     await route.fulfill(status=status,content_type='text/html',body='<span class="track"><button class="track-btn is-saved">Saved</button></span>' if status==200 else 'Test failure')
    await page.route('**/opportunities/*/track/',intercept)
    await page.goto(os.environ.get('NETWORKLY_BASE_URL','http://127.0.0.1:8000').rstrip('/')+'/opportunities/',wait_until='networkidle')
    button=page.locator('[data-pending-label="Saving…"]').first
    await button.click();await page.wait_for_timeout(100)
    assert await button.is_disabled()
    assert await button.get_attribute('aria-busy')=='true'
    assert 'Saving' in await button.inner_text()
    await page.wait_for_timeout(1100)
    if status==500:
     assert await button.is_enabled()
     assert (await button.inner_text()).strip()=='Save'
     assert await button.get_attribute('aria-busy') is None
    else: assert await page.locator('.track-btn.is-saved').count()>0
    results.append({'engine':engine,'status':status,'passed':True});await c.close()
   await b.close()
 print(json.dumps(results))
asyncio.run(main())
