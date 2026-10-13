#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
免交互 SSH 执行器 (paramiko)。
用法:
  python sshx.py <cmd> [timeout]
从环境变量 SSHPASS 读取密码（未设置则报错，仓库内不保存任何密码）。
"""
import sys
import os

import paramiko

HOST = "192.168.0.196"
PORT = 22
USER = "user"
PASSWORD = os.environ.get("SSHPASS", "")
if not PASSWORD:
    sys.exit("请通过环境变量 SSHPASS 提供密码（仓库内不保存任何密码）")


def run(cmd: str, timeout: int = 60):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        HOST, port=PORT, username=USER, password=PASSWORD,
        timeout=15, banner_timeout=20, auth_timeout=20,
        allow_agent=False, look_for_keys=False,
    )
    try:
        stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        rc = stdout.channel.recv_exit_status()
        return rc, out, err
    finally:
        client.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: sshx.py <cmd> [timeout]")
        sys.exit(2)
    cmd = sys.argv[1]
    tmo = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    rc, out, err = run(cmd, tmo)
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write("[stderr]\n" + err)
    sys.stdout.write(f"\n[exit={rc}]\n")
