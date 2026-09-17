# 检查那个 blob img 的来源与 WebCodecs 可用性，判断黑屏在哪一环
import asyncio, json
from pymobiledevice3.services.webinspector import WebinspectorService
from pymobiledevice3.lockdown import create_using_usbmux

async def val(session, exp):
    r = await session.runtime_evaluate(exp, return_by_value=True)
    if isinstance(r, str):
        try:
            r = json.loads(r)
        except Exception:
            return r
    try:
        return r.get('result', {}).get('value')
    except Exception:
        return r

async def find_target(service):
    for i in range(60):
        try:
            app_pages = await service.get_open_application_pages(timeout=1.0)
        except Exception:
            app_pages = []
        cands = [ap for ap in app_pages if 'cloudphone' in ap.application.bundle.lower()]
        if cands:
            return cands[0]
        await asyncio.sleep(0.5)
    return None

async def main():
    lockdown = await create_using_usbmux()
    service = WebinspectorService(lockdown=lockdown)
    await service.connect()
    target = await find_target(service)
    if not target:
        print("找不到 CloudPhone 页面")
        return
    print("页面:", target.page.web_url)
    session = await service.inspector_session(target.application, target.page)
    await session.runtime_enable()
    for exp in (
        "'VideoDecoder='+typeof VideoDecoder+' Enc='+typeof VideoEncoder+' OffCanvas='+typeof OffscreenCanvas+' ImageDecoder='+typeof ImageDecoder+' MSE='+typeof MediaSource+' MMS='+typeof ManagedMediaSource+' CS='+typeof CompressionStream",
        # 找到 blob img 并监听其 error/load 事件 10 秒，看是否持续更新
        "(function(){var imgs=[...document.querySelectorAll('img[src^=\"blob:\"]')];if(!imgs.length)return 'no blob img';var im=imgs[0];window.__imgEv=[];im.addEventListener('error',function(){window.__imgEv.push('error@'+Date.now())});im.addEventListener('load',function(){window.__imgEv.push('load@'+Date.now()+' '+im.naturalWidth+'x'+im.naturalHeight)});return 'watching '+im.src.slice(0,50);})()",
    ):
        r = await val(session, exp)
        print('>>', r)
    # 轮询事件
    for i in range(10):
        await asyncio.sleep(2)
        r = await val(session, "JSON.stringify(window.__imgEv||[])")
        print('[t+', (i + 1) * 2, 's]', r)
        if r and r != '[]' and i >= 3:
            break

asyncio.run(main())
