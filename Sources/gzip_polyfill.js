// gzip_polyfill.js — 纯 JS 实现 CompressionStream('gzip') / DecompressionStream('gzip')
// 供 iOS < 16.4 的 WKWebView 注入使用。
// 支持: gzip 压缩(stored/deflate-stored，不压缩但格式合法)、gzip 解压(stored + fixed-huffman + 动态 huffman)。
(function () {
  if (typeof CompressionStream !== 'undefined' && typeof DecompressionStream !== 'undefined') return;

  // ---------- bit reader ----------
  function BitReader(bytes) {
    this.bytes = bytes; this.pos = 0; this.bitbuf = 0; this.bitcnt = 0;
  }
  BitReader.prototype.bits = function (n) {
    var v = 0;
    while (this.bitcnt < n) {
      if (this.pos >= this.bytes.length) throw new Error('unexpected EOF');
      this.bitbuf |= this.bytes[this.pos++] << this.bitcnt;
      this.bitcnt += 8;
    }
    v = this.bitbuf & ((1 << n) - 1);
    this.bitbuf >>>= n; this.bitcnt -= n;
    return v;
  };
  BitReader.prototype.align = function () { this.bitcnt = 0; this.bitbuf = 0; };

  // ---------- huffman decode ----------
  function buildTable(lengths) {
    // canonical huffman: 返回 {counts, symbols}
    var counts = new Array(16);
    for (var i = 0; i < 16; i++) counts[i] = 0;
    for (var i = 0; i < lengths.length; i++) counts[lengths[i]]++;
    counts[0] = 0;
    var offs = new Array(16); offs[0] = 0;
    for (var i = 1; i < 16; i++) offs[i] = offs[i - 1] + counts[i - 1];
    var symbols = new Array(lengths.length);
    for (var i = 0; i < lengths.length; i++) {
      if (lengths[i] !== 0) symbols[offs[lengths[i]]++] = i;
    }
    return { counts: counts, symbols: symbols };
  }

  function decodeSymbol(reader, table) {
    var code = 0, first = 0, index = 0;
    for (var len = 1; len < 16; len++) {
      code |= reader.bits(1);
      var count = table.counts[len];
      if (code - first < count) return table.symbols[index + (code - first)];
      index += count; first += count; first <<= 1; code <<= 1;
    }
    throw new Error('invalid huffman code');
  }

  var LEN_BASE = [3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258];
  var LEN_EXTRA = [0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0];
  var DIST_BASE = [1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577];
  var DIST_EXTRA = [0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13];

  function inflate(data) {
    var reader = new BitReader(data);
    var out = [];
    do {
      var bfinal = reader.bits(1);
      var btype = reader.bits(2);
      if (btype === 0) {
        reader.align();
        var len = reader.bytes[reader.pos] | (reader.bytes[reader.pos + 1] << 8); reader.pos += 4;
        for (var i = 0; i < len; i++) out.push(reader.bytes[reader.pos++]);
      } else if (btype === 1 || btype === 2) {
        var litTable, distTable;
        if (btype === 1) {
          var lit = new Array(288), i;
          for (i = 0; i < 144; i++) lit[i] = 8;
          for (i = 144; i < 256; i++) lit[i] = 9;
          for (i = 256; i < 280; i++) lit[i] = 7;
          for (i = 280; i < 288; i++) lit[i] = 8;
          litTable = buildTable(lit);
          distTable = buildTable(new Array(30).fill(5));
        } else {
          var hlit = reader.bits(5) + 257;
          var hdist = reader.bits(5) + 1;
          var hclen = reader.bits(4) + 4;
          var order = [16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15];
          var cl = new Array(19).fill(0);
          for (var i = 0; i < hclen; i++) cl[order[i]] = reader.bits(3);
          var clTable = buildTable(cl);
          var lens = [];
          while (lens.length < hlit + hdist) {
            var sym = decodeSymbol(reader, clTable);
            if (sym < 16) lens.push(sym);
            else if (sym === 16) { var prev = lens[lens.length - 1]; var rep = reader.bits(2) + 3; while (rep--) lens.push(prev); }
            else if (sym === 17) { var rep = reader.bits(3) + 3; while (rep--) lens.push(0); }
            else { var rep = reader.bits(7) + 11; while (rep--) lens.push(0); }
          }
          litTable = buildTable(lens.slice(0, hlit));
          distTable = buildTable(lens.slice(hlit));
        }
        for (;;) {
          var sym = decodeSymbol(reader, litTable);
          if (sym < 256) out.push(sym);
          else if (sym === 256) break;
          else {
            var li = sym - 257;
            if (li < 0 || li >= LEN_BASE.length) throw new Error('bad length symbol');
            var length = LEN_BASE[li] + reader.bits(LEN_EXTRA[li]);
            var dsym = decodeSymbol(reader, distTable);
            var dist = DIST_BASE[dsym] + reader.bits(DIST_EXTRA[dsym]);
            for (var j = 0; j < length; j++) out.push(out[out.length - dist]);
          }
        }
      } else {
        throw new Error('invalid deflate block type 3');
      }
    } while (!bfinal);
    return new Uint8Array(out);
  }

  // ---------- crc32 / adler32 ----------
  var CRC_TABLE = (function () {
    var t = new Uint32Array(256);
    for (var n = 0; n < 256; n++) {
      var c = n;
      for (var k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
      t[n] = c >>> 0;
    }
    return t;
  })();
  function crc32(bytes) {
    var c = 0xFFFFFFFF;
    for (var i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  }
  function adler32(bytes) {
    var a = 1, b = 0;
    for (var i = 0; i < bytes.length; i++) { a = (a + bytes[i]) % 65521; b = (b + a) % 65521; }
    return ((b << 16) | a) >>> 0;
  }

  // ---------- deflate (stored blocks; valid, uncompressed) ----------
  function deflateStore(bytes) {
    var chunks = [], pos = 0;
    if (bytes.length === 0) chunks.push(new Uint8Array([0x01, 0x00, 0x00, 0xFF, 0xFF]));
    while (pos < bytes.length) {
      var take = Math.min(65535, bytes.length - pos);
      var last = (pos + take >= bytes.length) ? 1 : 0;
      var b = new Uint8Array(5 + take);
      b[0] = last;
      b[1] = take & 0xFF; b[2] = (take >> 8) & 0xFF;
      b[3] = (~take) & 0xFF; b[4] = ((~take) >> 8) & 0xFF;
      b.set(bytes.subarray(pos, pos + take), 5);
      chunks.push(b); pos += take;
    }
    var total = 0; chunks.forEach(function (c) { total += c.length; });
    var out = new Uint8Array(total), o = 0;
    chunks.forEach(function (c) { out.set(c, o); o += c.length; });
    return out;
  }

  function gzipCompress(bytes) {
    var header = new Uint8Array([0x1F, 0x8B, 0x08, 0x00, 0, 0, 0, 0, 0x00, 0xFF]);
    var body = deflateStore(bytes);
    var trailer = new Uint8Array(8);
    var crc = crc32(bytes), sz = bytes.length >>> 0;
    for (var i = 0; i < 4; i++) { trailer[i] = (crc >>> (8 * i)) & 0xFF; trailer[4 + i] = (sz >>> (8 * i)) & 0xFF; }
    var out = new Uint8Array(header.length + body.length + 8);
    out.set(header, 0); out.set(body, header.length); out.set(trailer, header.length + body.length);
    return out;
  }

  function gunzip(bytes) {
    if (bytes.length < 18 || bytes[0] !== 0x1F || bytes[1] !== 0x8B) throw new Error('not gzip');
    var flags = bytes[3], pos = 10;
    if (flags & 4) { var xlen = bytes[pos] | (bytes[pos + 1] << 8); pos += 2 + xlen; }
    if (flags & 8) { while (pos < bytes.length && bytes[pos] !== 0) pos++; pos++; }
    if (flags & 16) { while (pos < bytes.length && bytes[pos] !== 0) pos++; pos++; }
    if (flags & 2) pos += 2;
    return inflate(bytes.subarray(pos, bytes.length - 8));
  }

  function zlibDecompress(bytes) {
    // 裸 zlib 流 (CMF/FLG + deflate + adler32)
    var cmf = bytes[0], flg = bytes[1];
    if ((cmf & 0x0F) !== 8) throw new Error('not zlib');
    if (((cmf << 8) | flg) % 31 !== 0) throw new Error('bad zlib header');
    return inflate(bytes.subarray(2, bytes.length - 4));
  }

  function zlibCompress(bytes) {
    var header = new Uint8Array([0x78, 0x9C]);
    var body = deflateStore(bytes);
    var trailer = new Uint8Array(4);
    var ad = adler32(bytes);
    for (var i = 0; i < 4; i++) trailer[i] = (ad >>> (8 * i)) & 0xFF;
    var out = new Uint8Array(2 + body.length + 4);
    out.set(header, 0); out.set(body, 2); out.set(trailer, 2 + body.length);
    return out;
  }

  // ---------- Stream 类 ----------
  function toU8(chunk) {
    if (chunk instanceof Uint8Array) return chunk;
    if (chunk instanceof ArrayBuffer) return new Uint8Array(chunk);
    if (ArrayBuffer.isView(chunk)) return new Uint8Array(chunk.buffer, chunk.byteOffset, chunk.byteLength);
    return new TextEncoder().encode(String(chunk));
  }

  function makeStream(format, transform) {
    function StreamClass() {
      var chunks = [];
      var readable = null, writable = null, controller = null;
      var self = this;
      function ensure() {
        if (readable) return;
        writable = new WritableStream({
          write: function (chunk) { chunks.push(toU8(chunk)); },
          abort: function (e) { if (controller) controller.error(e); },
          close: function () {
            var total = 0; chunks.forEach(function (c) { total += c.length; });
            var all = new Uint8Array(total), o = 0;
            chunks.forEach(function (c) { all.set(c, o); o += c.length; });
            try {
              var res = transform(all, format);
              controller.enqueue(res);
              controller.close();
            } catch (e) { controller.error(e); }
          }
        });
        readable = new ReadableStream({
          start: function (c) { controller = c; }
        });
      }
      Object.defineProperty(self, 'readable', { get: function () { ensure(); return readable; } });
      Object.defineProperty(self, 'writable', { get: function () { ensure(); return writable; } });
    }
    return StreamClass;
  }

  function checkFormat(fmt) {
    if (fmt !== 'gzip' && fmt !== 'deflate' && fmt !== 'deflate-raw') {
      throw new TypeError('Unsupported compression format: ' + fmt);
    }
  }

  var CompressionStreamImpl = makeStream(null, function (all, fmt) { return null; });
  // 分别构造：transform 需要知道 format，改用闭包包装
  function makeCtor(formats) {
    return function (format) {
      checkFormat(format);
      var transform;
      if (format === 'gzip') transform = gzipCompress;
      else if (format === 'deflate') transform = zlibCompress;
      else transform = deflateStore;
      // 造一个绑定 format 的实例
      var stream = makeStream(format, function () { return null; }).call ? new (makeStream(format, function (all) { return transform(all); }))() : null;
      return stream;
    };
  }

  window.CompressionStream = function (format) {
    checkFormat(format);
    var transform = format === 'gzip' ? gzipCompress : (format === 'deflate' ? zlibCompress : deflateStore);
    return new (makeStream(format, transform))();
  };
  window.DecompressionStream = function (format) {
    checkFormat(format);
    var transform = format === 'gzip' ? gunzip : (format === 'deflate' ? zlibDecompress : inflate);
    return new (makeStream(format, transform))();
  };
})();
