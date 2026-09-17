# 向正在运行的 CloudPhone WebView 注入 gzip polyfill，然后重触发验证码
import asyncio
from pymobiledevice3.services.webinspector import WebinspectorService
from pymobiledevice3.lockdown import create_using_usbmux

POLYFILL = open(r"E:\Android\app\cloudphone-ios\Sources\gzip_polyfill.js", encoding="utf-8").read()

CAPTCHA_TRIGGER = """
(function () {
  try {
    var admin = window.admin;
    if (admin && admin.loginCtl && admin.loginCtl.getCaptcha) {
      window.__captchaResult = '已发起';
      admin.loginCtl.getCaptcha({}).then(function (r) {
        window.__captchaResult = '成功: ' + JSON.stringify(r).slice(0, 120);
      }).catch(function (e) {
        window.__captchaResult = '失败: ' + (e && e.message ? e.message : String(e));
      });
    } else {
      window.__captchaResult = '未找到 admin.loginCtl';
    }
  } catch (e) { window.__captchaResult = '异常: ' + e.message; }
  })();
  'OK'
"""

async def main():
    lockdown = await create_using_usbmux()
    service = WebinspectorService(lockdown=lockdown)
    await service.connect()
    target = None
    for i in range(60):
        try:
            app_pages = await service.get_open_application_pages(timeout=1.0)
        except Exception:
            app_pages = []
        cands = [ap for ap in app_pages if 'cloudphone' in ap.application.bundle.lower()]
        if cands:
            target = cands[0]
            break
        await asyncio.sleep(0.5)
    if not target:
        print("找不到 CloudPhone 页面")
        return
    print("页面:", target.page.web_title, "|", target.page.web_url)
    session = await service.inspector_session(target.application, target.page)
    await session.runtime_enable()

    # 注入 polyfill
    await session.runtime_evaluate(POLYFILL, return_by_value=True)
    r = await session.runtime_evaluate("typeof CompressionStream + '/' + typeof DecompressionStream", return_by_value=True)
    print("注入后:", r)

    # 触发验证码
    await session.runtime_evaluate(CAPTCHA_TRIGGER, return_by_value=True)
    for i in range(15):
        await asyncio.sleep(2)
        r = await session.runtime_evaluate("window.__captchaResult || ''", return_by_value=True)
        v = r.get('result', {}).get('value', '') if isinstance(r, dict) else ''
        if v and v != '已发起':
            print("====== 验证码结果 ======")
            print(v)
            break
    else:
        print("15 次轮询仍无结果")

asyncio.run(main())
