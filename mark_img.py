# 黑屏修复实验：给 blob img 打上白色背景做区分实验 —— 若黑屏区域变白，说明是同一元素
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

    # 给所有 blob 图加红色边框+白底，方便肉眼确认 img 实际显示区域
    js = """
(function(){
  var imgs=[...document.querySelectorAll('img[src^=\"blob:\"]')];
  imgs.forEach(function(im){
    im.style.background='#fff';
    im.style.outline='3px solid red';
    im.style.opacity='1';
    im.style.visibility='visible';
  });
  return 'styled '+imgs.length+' blob imgs';
})()
"""
    r = await val(session, js)
    print('>>', r, '（请看手机：图上是否出现红框/白底？原来黑的区域有没有变化？）')

asyncio.run(main())
