# 在手机 Safari 上打开登录页 → 跑 API 检查 → 跑 WS 测试，全程自动
import asyncio
from pymobiledevice3.services.webinspector import WebinspectorService
from pymobiledevice3.lockdown import create_using_usbmux

LOGIN_URL = "https://www.oj8kclub.com/mobile.html#/login"

JS_BODY = """
var out = [];
var m = /Version\\/(\\d+[\\d.]*)[\\s\\S]*Safari/.exec(navigator.userAgent);
out.push('WebKit版本: ' + (m ? m[1] : '?'));
out.push('当前页面: ' + location.href);
var missing = [];
var checks = [
  ['structuredClone', function(){return typeof structuredClone==='function'}],
  ['Array.at', function(){return typeof [].at==='function'}],
  ['Array.findLast', function(){return typeof [].findLast==='function'}],
  ['Object.hasOwn', function(){return typeof Object.hasOwn==='function'}],
  ['String.replaceAll', function(){return typeof ''.replaceAll==='function'}],
  ['Promise.allSettled', function(){return typeof Promise.allSettled==='function'}],
  ['Promise.any', function(){return typeof Promise.any==='function'}],
  ['Promise.withResolvers', function(){return typeof Promise.withResolvers==='function'}],
  ['crypto.randomUUID', function(){return typeof crypto.randomUUID==='function'}],
  ['ResizeObserver', function(){return typeof ResizeObserver==='function'}],
  ['IntersectionObserver', function(){return typeof IntersectionObserver==='function'}],
  ['requestIdleCallback', function(){return typeof requestIdleCallback==='function'}],
  ['OffscreenCanvas', function(){return typeof OffscreenCanvas==='function'}],
  ['VideoEncoder', function(){return typeof VideoEncoder==='function'}],
  ['ManagedMediaSource', function(){return typeof ManagedMediaSource==='function'}],
  ['RTCPeerConnection', function(){return typeof RTCPeerConnection==='function'}],
  ['BigInt', function(){return typeof BigInt==='function'}],
  ['AbortController', function(){return typeof AbortController==='function'}]
];
checks.forEach(function(c){ var ok=false; try{ok=c[1]()}catch(e){}; if(!ok) missing.push(c[0]); });
out.push(missing.length ? '缺失API: ' + missing.join(', ') : 'API全部齐备');
window.__diagResult = out.join('\\n');
window.__wsResult = '';
'OK'
"""

WS_JS = """
(function(){
  try {
    var ws = new WebSocket(location.origin.replace('http','ws') + '/ws');
    var lines = [];
    var done = false;
    function finish(){ if(!done){ done=true; window.__wsResult = lines.join('\\n'); } }
    var t = setTimeout(finish, 7000);
    ws.onopen = function(){
      clearTimeout(t); lines.push('WS: 连接成功 ' + location.origin.replace('http','ws') + '/ws');
      ws.onmessage = function(){ lines.push('WS: 收到回包'); };
      setTimeout(function(){ finish(); }, 2000);
    };
    ws.onclose = function(e){ if(done) return; clearTimeout(t); lines.push('WS: 连接失败 code='+e.code+' clean='+e.wasClean); finish(); };
    ws.onerror = function(){ lines.push('WS: onerror readyState='+ws.readyState); };
  } catch(e) { window.__wsResult = 'WS构造异常: ' + e.message; }
})()
"""

async def eval_ok(session, exp):
    try:
        return await session.runtime_evaluate(exp, return_by_value=True)
    except Exception as e:
        return {"error": str(e)}

async def find_safari(service):
    for i in range(60):
        try:
            app_pages = await service.get_open_application_pages(timeout=1.0)
        except Exception:
            app_pages = []
        cands = [ap for ap in app_pages if 'safari' in ap.application.name.lower()]
        if cands:
            return cands[0]
        await asyncio.sleep(0.5)
    return None

async def main():
    lockdown = await create_using_usbmux()
    service = WebinspectorService(lockdown=lockdown)
    await service.connect()
    print("查找 Safari...")
    safari_ap = await find_safari(service)
    if not safari_ap:
        print("!! Safari 没有打开的页面。")
        return
    print("Safari:", safari_ap.page.web_title, "|", safari_ap.page.web_url)
    session = await service.inspector_session(safari_ap.application, safari_ap.page)
    await session.console_enable()
    await session.runtime_enable()

    # 打开登录页
    if "oj8kclub" not in (safari_ap.page.web_url or ""):
        print("导航到登录页...")
        await session.navigate_to_url(LOGIN_URL)
        await asyncio.sleep(8)
        # 导航后原 page 句柄可能失效，重新找
        safari_ap = await find_safari(service)
        if not safari_ap:
            print("!! 导航后找不到 Safari 页面")
            return
        session = await service.inspector_session(safari_ap.application, safari_ap.page)
        await session.console_enable()
        await session.runtime_enable()
        print("现在在:", safari_ap.page.web_title, "|", safari_ap.page.web_url)

    print("执行 API 检查...")
    await eval_ok(session, JS_BODY)
    r2 = await eval_ok(session, "window.__diagResult")
    print("====== 诊断结果 ======")
    try:
        print(r2.get('result', {}).get('value', r2))
    except Exception:
        print(r2)

    print("执行 WS 测试（登录页同源，复现验证码场景）...")
    await eval_ok(session, WS_JS)
    for i in range(10):
        await asyncio.sleep(1)
        r3 = await eval_ok(session, "window.__wsResult || ''")
        try:
            val = r3.get('result', {}).get('value', '')
        except Exception:
            val = ''
        if val:
            print("====== WS测试 ======")
            print(val)
            break
    else:
        print("WS测试未取到结果")

asyncio.run(main())
