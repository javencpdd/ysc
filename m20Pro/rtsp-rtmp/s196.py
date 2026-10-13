#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在 196 主机上带 sudo 执行命令（paramiko 免交互）。
用法:
  python s196.py "<cmd>"            # 普通执行
  python s196.py -s "<cmd>"         # sudo 执行 (密码从 SSHPASS 读，未设置则报错)
  python s196.py -t <sec> "<cmd>"
"""
import os
import sys

import paramiko

HOST = os.environ.get("H196", "192.168.0.196")
PORT = 22
USER = os.environ.get("U196", "user")
PASSWORD = os.environ.get("SSHPASS", "")
if not PASSWORD:
    sys.exit("请通过环境变量 SSHPASS 提供密码（仓库内不保存任何密码）")


def run(cmd: str, use_sudo: bool = False, timeout: int = 60) -> tuple:
    if use_sudo:
        # printf '%s\n' '<pwd>' | sudo -S -p '' bash -c '<script>'
        cmd = ("printf %s %s | sudo -S -p '' bash -c %s"
               % (_shq("%s\\n"), _shq(PASSWORD), _shq(cmd)))
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, port=PORT, username=USER, password=PASSWORD,
                   timeout=15, banner_timeout=20, auth_timeout=20,
                   allow_agent=False, look_for_keys=False)
    try:
        stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        rc = stdout.channel.recv_exit_status()
        return rc, out, err
    finally:
        client.close()


def _shq(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


if __name__ == "__main__":
    args = sys.argv[1:]
    sudo = False
    tmo = 120
    while args and args[0] in ("-s", "-t"):
        if args[0] == "-s":
            sudo = True
            args.pop(0)
        else:
            args.pop(0)
            tmo = int(args.pop(0))
    rc, out, err = run(args[0], sudo, tmo)
    if out:
        sys.stdout.write(out)
    if err.strip():
        sys.stderr.write("[stderr] " + err[:2000] + "\n")
    sys.stdout.write("[exit=%d]\n" % rc)
    sys.exit(0)
