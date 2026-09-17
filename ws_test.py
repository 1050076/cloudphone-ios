# 测试 oj8kclub 的 /ws WebSocket：能否连接、能否请求验证码
import asyncio, json, sys

async def main():
    try:
        import websockets
    except ImportError:
        print("NO_LIB")
        return
    url = "wss://www.oj8kclub.com/ws"
    try:
        async with websockets.connect(url, additional_headers={
            "Origin": "https://www.oj8kclub.com",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
        }, open_timeout=15) as ws:
            print("CONNECTED")
            # 协议是二进制 TcpType_RText，先发个 JSON 试探；观察是否有任何回包/心跳
            try:
                for i in range(3):
                    msg = await asyncio.wait_for(ws.recv(), timeout=8)
                    if isinstance(msg, bytes):
                        print("RECV bytes:", msg[:80].hex(), "|", msg[:120])
                    else:
                        print("RECV text:", msg[:200])
            except asyncio.TimeoutError:
                print("NO_MESSAGE (connected but silent)")
    except Exception as e:
        print("FAIL:", type(e).__name__, str(e)[:300])

asyncio.run(main())
