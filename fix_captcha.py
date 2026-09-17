# 在手机 Safari 登录页上注入 CompressionStream/DecompressionStream polyfill，
# 然后触发验证码请求，验证修复是否生效
import asyncio
from pymobiledevice3.services.webinspector import WebinspectorService
from pymobiledevice3.lockdown import create_using_usbmux

LOGIN_URL = "https://www.oj8kclub.com/mobile.html#/login"

# 纯 JS 的 gzip(仅存储无压缩块)+gunzip polyfill，实现 CompressionStream/DecompressionStream 接口
POLYFILL = r"""
(function () {
  if (typeof CompressionStream !== 'undefined' && typeof DecompressionStream !== 'undefined') {
    window.__polyfillNeeded = false;
    return;
  }
  window.__polyfillNeeded = true;

  function crc32Table() {
    if (crc32Table.t) return crc32Table.t;
    var t = new Uint32Array(256);
    for (var n = 0; n < 256; n++) {
      var c = n;
      for (var k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      t[n] = c >>> 0;
    }
    crc32Table.t = t;
    return t;
  }
  function crc32(bytes) {
    var t = crc32Table(), c = 0xFFFFFFFF;
    for (var i = 0; i < bytes.length; i++) c = t[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  }
  function adler32(bytes) {
    var a = 1, b = 0;
    for (var i = 0; i < bytes.length; i++) { a = (a + bytes[i]) % 65521; b = (b + a) % 65521; }
    return ((b << 16) | a) >>> 0;
  }

  // stored deflate blocks: 每 65535 字节一个块
  function deflateStore(bytes) {
    var chunks = [];
    var pos = 0;
    if (bytes.length === 0) {
      chunks.push(new Uint8Array([0x01, 0x00, 0x00, 0xFF, 0xFF]));
    }
    while (pos < bytes.length) {
      var take = Math.min(65535, bytes.length - pos);
      var last = (pos + take >= bytes.length) ? 1 : 0;
      var b = new Uint8Array(5 + take);
      b[0] = last; // BFINAL + BTYPE=00
      b[1] = take & 0xFF; b[2] = take >> 8;
      b[3] = (~take) & 0xFF; b[4] = ((~take) >> 8) & 0xFF;
      b.set(bytes.subarray(pos, pos + take), 5);
      chunks.push(b);
      pos += take;
    }
    var total = 0; chunks.forEach(function (c) { total += c.length; });
    var out = new Uint8Array(total); var o = 0;
    chunks.forEach(function (c) { out.set(c, o); o += c.length; });
    return out;
  }

  // 解析 deflate（支持 stored + fixed-huffman），输出原字节
  function inflate(data) {
    var bits = [], n = data.length;
    // 转成比特流（LSB first）
    var pos = 0, bitpos = 0, cur = 0;
    function readBit() {
      if (bitpos === 0) { cur = data[pos++]; bitpos = 8; }
      var b = cur & 1; cur >>= 1; bitpos--;
      return b;
    }
    function readBits(cnt) {
      var v = 0;
      for (var i = 0; i < cnt; i++) v |= readBit() << i;
      return v;
    }
    var out = [];
    // fixed huffman 表
    var lenBase = [3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258];
    var lenExtra = [0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0];
    var distBase = [1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577];
    var distExtra = [0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13];
    function buildFixed() {
      var lit = new Array(288), i;
      for (i = 0; i < 144; i++) lit[i] = { bits: 8, code: 0x30 + i };
      for (i = 144; i < 256; i++) lit[i] = { bits: 9, code: 0x190 + i - 144 };
      for (i = 256; i < 280; i++) lit[i] = { bits: 7, code: i - 256 };
      for (i = 280; i < 288; i++) lit[i] = { bits: 8, code: 0xC0 + i - 280 };
      return lit;
    }
    function decodeSymbol(lit) {
      // 逐位构建 code
      var code = 0, len = 0;
      for (;;) {
        code = (code << 1) | readBit(); len++;
        for (var i = 0; i < lit.length; i++) {
          if (lit[i] && lit[i].bits === len && lit[i].code === code) return i;
        }
        if (len > 15) throw new Error('bad code');
      }
    }
    var fixed = null;
    for (;;) {
      var bfinal = readBit();
      var btype = readBits(2);
      if (btype === 0) {
        // stored：跳到字节边界
        bitpos = 0;
        var LEN = data[pos] | (data[pos+1] << 8); pos += 2;
        var NLEN = data[pos] | (data[pos+1] << 8); pos += 2;
        for (var j = 0; j < LEN; j++) out.push(data[pos++]);
      } else if (btype === 1) {
        if (!fixed) fixed = buildFixed();
        for (;;) {
          var sym = decodeSymbol(fixed);
          if (sym < 256) out.push(sym);
          else if (sym === 256) break;
          else {
            var li = sym - 257;
            var length = lenBase[li] + readBits(lenExtra[li]);
            var dsym = decodeSymbol(fixed); // 5bit 距离码，固定表里 0-29
            var dist = distBase[dsym] + readBits(distExtra[dsym]);
            for (var j = 0; j < length; j++) out.push(out[out.length - dist]);
          }
        }
      } else {
        throw new Error('dynamic huffman not supported in polyfill');
      }
      if (bfinal) break;
    }
    return new Uint8Array(out);
  }

  function makeStreamClass(name, transform) {
    function StreamClass() {
      var readable = null, writable = null;
      var self = this;
      function ensure() {
        if (readable) return;
        var chunks = [];
        var controller = null;
        writable = new WritableStream({
          write: function (chunk) {
            var u8;
            if (chunk instanceof Uint8Array) u8 = chunk;
            else if (chunk instanceof ArrayBuffer) u8 = new Uint8Array(chunk);
            else if (ArrayBuffer.isView(chunk)) u8 = new Uint8Array(chunk.buffer, chunk.byteOffset, chunk.byteLength);
            else u8 = new TextEncoder().encode(String(chunk));
            chunks.push(u8);
          },
          close: function () {
            var total = 0; chunks.forEach(function (c) { total += c.length; });
            var all = new Uint8Array(total); var o = 0;
            chunks.forEach(function (c) { all.set(c, o); o += c.length; });
            controller.enqueue(transform(all));
            controller.close();
          }
        });
        readable = new ReadableStream({
          start: function (c) { controller = c; }
        });
      }
      Object.defineProperty(this, 'readable', { get: function () { ensure(); return readable; } });
      Object.defineProperty(this, 'writable', { get: function () { ensure(); return writable; } });
    }
    window[name] = StreamClass;
  }

  function gzipCompress(bytes) {
    // gzip header
    var header = new Uint8Array([0x1F, 0x8B, 0x08, 0x00, 0, 0, 0, 0, 0x00, 0xFF]);
    var deflated = deflateStore(bytes);
    var trailer = new Uint8Array(8);
    var crc = crc32(bytes), sz = bytes.length >>> 0;
    for (var i = 0; i < 4; i++) { trailer[i] = (crc >>> (8 * i)) & 0xFF; trailer[4 + i] = (sz >>> (8 * i)) & 0xFF; }
    var out = new Uint8Array(header.length + deflated.length + 8);
    out.set(header, 0); out.set(deflated, header.length); out.set(trailer, header.length + deflated.length);
    return out;
  }

  function gunzip(bytes) {
    if (bytes[0] !== 0x1F || bytes[1] !== 0x8B) throw new Error('not gzip');
    var flags = bytes[3];
    var pos = 10;
    if (flags & 4) { var xlen = bytes[pos] | (bytes[pos+1] << 8); pos += 2 + xlen; }
    if (flags & 8) { while (bytes[pos] !== 0) pos++; pos++; }
    if (flags & 16) { while (bytes[pos] !== 0) pos++; pos++; }
    if (flags & 2) pos += 2;
    var inflated = inflate(bytes.subarray(pos, bytes.length - 8));
    return inflated;
  }

  makeStreamClass('CompressionStream', function (all) {
    // 根据 format 判断 —— 我们只注册 gzip 用法；页面只用 gzip
    return gzipCompress(all);
  });
  makeStreamClass('DecompressionStream', function (all) {
    return gunzip(all);
  });

  // 记录 zlib 头（ CMF/FLG），DecompressionStream 需要处理裸 zlib：页面用 gzip 就不用管
  window.__polyfillReady = true;
})();
"""

CAPTCHA_TRIGGER = """
(function () {
  // 点掉已有弹窗状态，重新触发页面初始化逻辑：直接刷新验证码模块
  window.__captchaFired = true;
  // 页面加载时自动请求过一次验证码；现在重新触发：调用 admin.loginCtl.getCaptcha
  try {
    var ks = Object.keys(window);
    var admin = window.admin;
    if (admin && admin.loginCtl && admin.loginCtl.getCaptcha) {
      admin.loginCtl.getCaptcha({}).then(function (r) {
        window.__captchaResult = '成功: ' + JSON.stringify(r).slice(0, 200);
      }).catch(function (e) {
        window.__captchaResult = '失败: ' + (e && e.message ? e.message : String(e));
      });
      window.__captchaResult = '已发起，等待回调';
    } else {
      window.__captchaResult = '未找到 window.admin.loginCtl';
    }
  } catch (e) { window.__captchaResult = '异常: ' + e.message; }
  'OK'
"""

async def eval_ok(session, exp):
    try:
        return await session.runtime_evaluate(exp, return_by_value=True)
    except Exception as e:
        return {"error": str(e)}

async def get_val(session, exp, timeout=15):
    for _ in range(timeout):
        r = await eval_ok(session, exp)
        try:
            v = r.get('result', {}).get('value', '')
        except Exception:
            v = ''
        if v:
            return v
        await asyncio.sleep(1)
    return '(超时未取到)'

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
    safari_ap = await find_safari(service)
    if not safari_ap:
        print("!! Safari 没有打开的页面")
        return
    print("Safari:", safari_ap.page.web_title, "|", safari_ap.page.web_url)
    session = await service.inspector_session(safari_ap.application, safari_ap.page)
    await session.console_enable()
    await session.runtime_enable()

    if "oj8kclub" not in (safari_ap.page.web_url or ""):
        await session.navigate_to_url(LOGIN_URL)
        await asyncio.sleep(8)
        safari_ap = await find_safari(service)
        session = await service.inspector_session(safari_ap.application, safari_ap.page)
        await session.console_enable()
        await session.runtime_enable()
        print("导航到:", safari_ap.page.web_url)

    # 1. 检查是否真的缺 CompressionStream
    r = await eval_ok(session, "typeof CompressionStream + '/' + typeof DecompressionStream")
    print("CompressionStream/DecompressionStream:", r if isinstance(r, str) else r.get('result', {}).get('value'))

    # 2. 注入 polyfill
    await eval_ok(session, POLYFILL)
    r = await eval_ok(session, "window.__polyfillNeeded + '/' + (window.__polyfillReady || false)")
    print("polyfill 注入:", r if isinstance(r, str) else r.get('result', {}).get('value'))

    # 3. 重新触发验证码
    await eval_ok(session, CAPTCHA_TRIGGER)
    for i in range(15):
        r = await eval_ok(session, "window.__captchaResult || '(尚未设置)'")
        v = r if isinstance(r, str) else r.get('result', {}).get('value', '')
        print(f"[{i}] __captchaResult = {v}")
        if v and v != '已发起，等待回调' and v != '(尚未设置)':
            break
        await asyncio.sleep(2)

asyncio.run(main())
