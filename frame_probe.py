# 验证修复：进入黑屏设备页后，给 blob 图加 object-fit/背景，并检查 webp 帧实际内容
import asyncio, json, base64
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

    # 抓最近一帧 webp 转 dataURL 采样（取中心+角落像素亮度）
    js = """
(function(){
  var imgs=[...document.querySelectorAll('img[src^=\"blob:\"]')];
  if(!imgs.length)return 'no blob img';
  var im=imgs[0];
  var c=document.createElement('canvas');
  c.width=im.naturalWidth||200; c.height=im.naturalHeight||440;
  var ctx=c.getContext('2d');
  ctx.drawImage(im,0,0,c.width,c.height);
  function lum(x,y){var d=ctx.getImageData(x,y,1,1).data;return (d[0]+d[1]+d[2])/3|0;}
  var w=c.width,h=c.height;
  var pts=[lum(w>>1,h>>1),lum(w>>1,2),lum(w>>1,h-3),lum(2,h>>1),lum(w-3,h>>1)];
  return 'size:'+w+'x'+h+' 亮度[中心,上,下,左,右]:'+pts.join(',');
})()
"""
    for i in range(3):
        r = await val(session, js)
        print('帧采样:', r)
        await asyncio.sleep(2)

asyncio.run(main())
