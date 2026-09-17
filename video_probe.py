# 精简版：直接 eval 表达式取值（不用 IIFE + return），检查视频链路关键信息
import asyncio, json
from pymobiledevice3.services.webinspector import WebinspectorService
from pymobiledevice3.lockdown import create_using_usbmux

EXPR = ("['connMode='+localStorage.getItem('connMode'),"
        "'CS='+typeof CompressionStream,"
        "'VDec='+typeof VideoDecoder,"
        "'Offscreen='+typeof OffscreenCanvas,"
        "'MSE='+typeof MediaSource+'/'+typeof ManagedMediaSource,"
        "'RTC='+typeof RTCPeerConnection,"
        "'loc='+location.href].join(' | ')")

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
    print("页面:", target.page.web_title, "|", target.page.web_url)
    session = await service.inspector_session(target.application, target.page)
    await session.runtime_enable()
    for exp in (EXPR,
                "typeof admin",
                "document.querySelectorAll('canvas').length + ' canvas / ' + document.querySelectorAll('img').length + ' img'",
                "[...document.querySelectorAll('img')].slice(0,6).map(function(i){return (i.dataset.id||i.className||'img')+' '+i.naturalWidth+'x'+i.naturalHeight+' '+(i.src||'').slice(0,50)}).join('\\n')"):
        r = await val(session, exp)
        print('>>', r)

asyncio.run(main())
