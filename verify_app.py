# 验证新包：检查 gzip_polyfill 是否在目标 WebView 里生效
# 通过 webinspector 附加到 CloudPhone 的 WebView，执行 typeof CompressionStream
import asyncio
from pymobiledevice3.services.webinspector import WebinspectorService
from pymobiledevice3.lockdown import create_using_usbmux

async def main():
    lockdown = await create_using_usbmux()
    service = WebinspectorService(lockdown=lockdown)
    await service.connect()
    app_pages = []
    target = None
    for i in range(60):
        try:
            app_pages = await service.get_open_application_pages(timeout=1.0)
        except Exception:
            app_pages = []
        cands = [ap for ap in app_pages if 'cloudphone' in ap.application.name.lower() or 'cloudphone' in ap.application.bundle.lower()]
        if cands:
            target = cands[0]
            break
        await asyncio.sleep(0.5)
    if not target:
        print("找不到 CloudPhone 的可调试页面。当前列表:")
        for ap in app_pages:
            print(" -", ap.application.name, ap.application.bundle, "|", ap.page.web_title)
        return
    print("页面:", target.application.bundle, "|", target.page.web_title, "|", target.page.web_url)
    session = await service.inspector_session(target.application, target.page)
    await session.runtime_enable()
    r = await session.runtime_evaluate("typeof CompressionStream + '/' + typeof DecompressionStream + '/' + location.href", return_by_value=True)
    print("结果:", r)

asyncio.run(main())
