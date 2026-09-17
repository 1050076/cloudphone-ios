# 深挖：验证码触发后页面内部状态（admin 对象结构、WS 状态、报错位置）
import asyncio, json
from pymobiledevice3.services.webinspector import WebinspectorService
from pymobiledevice3.lockdown import create_using_usbmux

POLYFILL = open(r"E:\Android\app\cloudphone-ios\Sources\gzip_polyfill.js", encoding="utf-8").read()

PROBE = """
(function () {
  var out = [];
  out.push('typeof admin: ' + typeof admin);
  if (typeof admin !== 'undefined') {
    out.push('admin keys: ' + Object.keys(admin).slice(0, 30).join(','));
    if (admin.loginCtl) {
      out.push('loginCtl methods: ' + Object.getOwnPropertyNames(Object.getPrototypeOf(admin.loginCtl)).join(','));
    }
    if (admin.tool) out.push('admin.tool keys: ' + Object.keys(admin.tool).slice(0, 20).join(','));
    if (admin.sendInterface) out.push('sendInterface keys: ' + Object.keys(admin.sendInterface).join(','));
  }
  window.__probeResult = out.join('\\n');
  'OK'
})();
"""

CAPTCHA = """
(function () {
  try {
    window.__capLog = [];
    var log = function (m) { window.__capLog.push(m); };
    var admin = window.admin;
    if (!admin || !admin.loginCtl) { window.__capResult = 'no admin.loginCtl'; return; }
    log('发起 getCaptcha');
    admin.loginCtl.getCaptcha({}).then(function (r) {
      log('resolve: ' + JSON.stringify(r).slice(0, 100));
    }).catch(function (e) {
      log('reject: ' + (e && e.message ? e.message : String(e)) + ' | stack: ' + ((e && e.stack) ? e.stack.slice(0, 300) : ''));
    });
    window.__capResult = 'pending';
  } catch (e) { window.__capResult = 'throw: ' + e.message; }
})();
"""

def val(r):
    if isinstance(r, str):
        try:
            import json as _j
            r = _j.loads(r)
        except Exception:
            return r
    try:
        return r.get('result', {}).get('value')
    except Exception:
        return r

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
    session = await service.inspector_session(target.application, target.page)
    await session.runtime_enable()

    await session.runtime_evaluate(POLYFILL, return_by_value=True)
    r = await session.runtime_evaluate("typeof CompressionStream", return_by_value=True)
    print("polyfill:", val(r))

    await session.runtime_evaluate(PROBE, return_by_value=True)
    r = await session.runtime_evaluate("window.__probeResult", return_by_value=True)
    print("====== admin 结构 ======")
    print(val(r))

    await session.runtime_evaluate(CAPTCHA, return_by_value=True)
    last = ''
    for i in range(20):
        await asyncio.sleep(2)
        r = await session.runtime_evaluate("JSON.stringify({r: window.__capResult, log: window.__capLog})", return_by_value=True)
        last = val(r) or ''
        try:
            d = json.loads(last)
        except Exception:
            continue
        if isinstance(d, dict) and d.get('r') and d['r'] != 'pending':
            print("====== 结果 ======")
            print(d)
            return
    print("20 次轮询无终态，最后:", last)

asyncio.run(main())
