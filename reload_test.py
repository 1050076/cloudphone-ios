# 查 WS 连接状态：polyfill 注入后 WS 可能已经断开且不会自动重连，需要 reload 页面
# 方案：注入 polyfill -> location.reload() -> 等 12s -> 检查验证码按钮状态和 WS
import asyncio, json
from pymobiledevice3.services.webinspector import WebinspectorService
from pymobiledevice3.lockdown import create_using_usbmux

POLYFILL = open(r"E:\Android\app\cloudphone-ios\Sources\gzip_polyfill.js", encoding="utf-8").read()

CHECK = """
(function () {
  var hasBtn = !!document.querySelector('img[src*="captcha"], canvas, [class*="captcha"], [class*="code"] img');
  var html = document.body ? document.body.innerText.slice(0, 300) : '(no body)';
  window.__check = 'WS类存在: ' + (typeof WebSocket) + ' | CompressionStream: ' + (typeof CompressionStream) + '\\n页面文本: ' + html;
  'OK'
})();
"""

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

    # 第一阶段：注入 polyfill 并 reload，让页面在新环境下重新初始化
    session = await service.inspector_session(target.application, target.page)
    await session.runtime_enable()
    print("注入 polyfill...")
    await session.runtime_evaluate(POLYFILL, return_by_value=True)
    print("reload 页面...")
    await session.runtime_evaluate("location.reload(); 'OK'", return_by_value=True)
    await asyncio.sleep(12)

    # reload 后重新 attach
    target = await find_target(service)
    if not target:
        print("reload 后找不到页面")
        return
    session = await service.inspector_session(target.application, target.page)
    await session.runtime_enable()

    r = await val(session, "typeof CompressionStream + ' | ' + location.href")
    print("reload后:", r)
    r = await val(session, CHECK.replace('window.__check = ', 'window.__check = ') if False else "(function(){var t=document.body?document.body.innerText.slice(0,200):'(no body)';return 'CS:'+typeof CompressionStream+' | '+t;})()")
    print("页面状态:", r)

asyncio.run(main())
