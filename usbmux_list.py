# usbmuxd 协议版本：带版本头（v1.0 tag=1）+ Listen，iTunes 风格握手
import socket, plistlib, struct

def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("EOF")
        buf += chunk
    return buf

def send_msg(sock, tag, payload_plist):
    body = plistlib.dumps(payload_plist, fmt=plistlib.FMT_BINARY)
    # header: version(4B=1.0) = 0x00 0x00 0x00 0x01? 实际: u32 version=1, u32 type? no:
    # usbmuxd header: u32 length(total), u32 version=1, u32 type=8(XML)? — 用标准:
    #   total_len(4) + version(4, =1) + message_type(4, 1=plist) + tag(4) + payload
    total = 16 + len(body)
    hdr = struct.pack("<IIII", total, 1, 8, tag)
    # type 8 是 PLIST 消息 (MESSAGE_PLIST)
    sock.sendall(hdr + body)

def recv_msg(sock):
    total = struct.unpack("<I", recv_exact(sock, 4))[0]
    version, mtype, tag = struct.unpack("<III", recv_exact(sock, 12))
    body = recv_exact(sock, total - 16) if total > 16 else b""
    return mtype, tag, (plistlib.loads(body) if body else {})

s = socket.create_connection(("127.0.0.1", 27015), timeout=5)
send_msg(s, 1, {"MessageType": "Listen"})
mtype, tag, resp = recv_msg(s)
print("Listen resp: mtype=", mtype, "result=", resp.get("Number"))
send_msg(s, 2, {"MessageType": "ListDevices"})
mtype, tag, resp = recv_msg(s)
devs = resp.get("DeviceList", [])
print("设备数:", len(devs))
for d in devs:
    p = d.get("Properties", {})
    print("-", p.get("SerialNumber"), "| type=", p.get("ConnectionType"), "| DeviceID=", p.get("DeviceID"), "| LocationID=", hex(p.get("LocationID", 0)))
s.close()
