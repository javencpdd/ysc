#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""源地址绑定中继：绕过本机路由 metric 劫持（WLAN 3 metric 50 < WLAN 55）。

背景：本机 USB 网卡(WLAN 3, 192.168.0.194, 连 M20 的 Tenda_FCFA20)上线后，
Windows 把默认路由判给了它，去往 192.168.1.x(Lite3 网段)的流量被送进错误网卡。
route add 需要管理员权限，故用本中继：
  * 出站 socket bind 到 192.168.2.47（Intel 网卡，YSC-JYML-aw3bal-5G）→ 强制正确网卡；
  * 192.168.2.x → 192.168.1.x 由 120 做 SNAT，console 看到的源是 192.168.1.120
    （在 allowed_cidrs=192.168.1.0/24 内）⇒ CIDR 白名单不受影响。
两个监听口：
  127.0.0.1:2222 -> 192.168.1.103:22    （SSH）
  127.0.0.1:8090 -> 192.168.1.103:8090  （HTTP，给浏览器用）
零系统改动，杀掉进程即撤销。
"""
import select
import socket
import threading

BIND_SRC = ("192.168.2.47", 0)
RELAYS = [
    ("127.0.0.1", 2222, "192.168.1.103", 22),
    ("127.0.0.1", 8090, "192.168.1.103", 8090),
]


def pump(a, b):
    try:
        while True:
            readable, _, _ = select.select([a, b], [], [], 300)
            if not readable:
                break
            for sock in readable:
                data = sock.recv(65536)
                if not data:
                    return
                (b if sock is a else a).sendall(data)
    except OSError:
        pass
    finally:
        for sock in (a, b):
            try:
                sock.close()
            except OSError:
                pass


def serve(listen_host, listen_port, target_host, target_port):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((listen_host, listen_port))
    srv.listen(32)
    print("relay %s:%d -> %s:%d (src %s)" % (listen_host, listen_port,
                                             target_host, target_port, BIND_SRC[0]),
          flush=True)
    while True:
        client, addr = srv.accept()
        try:
            upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            upstream.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            upstream.bind(BIND_SRC)          # 关键：强制出站网卡
            upstream.connect((target_host, target_port))
        except OSError as exc:
            print("connect failed: %r" % exc, flush=True)
            try:
                client.close()
            except OSError:
                pass
            continue
        threading.Thread(target=pump, args=(client, upstream), daemon=True).start()


if __name__ == "__main__":
    for lh, lp, th, tp in RELAYS:
        threading.Thread(target=serve, args=(lh, lp, th, tp), daemon=True).start()
    threading.Event().wait()
