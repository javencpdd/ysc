#!/usr/bin/env python3
"""env 文件的**键级 upsert**（deploy/migrate-rename.sh 用它迁移身份派生键）。

语义与 deploy/render_env.py 的 ``_upsert`` 逐条对齐（同一个项目、两种入口）：
  · 生效行（非注释、非空、``KEY=`` 开头）：保留**第一处**并替换为新值，
    其余同键生效行删除——防止同键两行时 systemd 取到旧的那行；
  · 注释行、空行、缩进行原样保留（注释里提到的 KEY 不算生效）；
  · 文件里没有的键：末尾追加；``--header`` 给了就在追加段前写一行表头注释；
  · 输出始终 LF 行尾，且保证文件以换行结束；
  · 幂等：连续跑两次结果逐字相同。

用法：
    python3 deploy/env_upsert.py [--header "说明"] <env文件> KEY=VALUE [KEY=VALUE ...]

退出码：0 成功；2 用法/参数错误；3 文件不存在。
"""
from __future__ import annotations

import argparse
import os
import sys

EXIT_USAGE = 2
EXIT_NOFILE = 3


def upsert(path: str, pairs, header: str = "") -> str:
    """对 ``path`` 做键级 upsert，返回写回后的文本（调用方决定是否落盘）。"""
    kv = dict(pairs)
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")

    out, seen = [], set()
    for ln in lines:
        s = ln.strip()
        key = None
        if s and not s.startswith("#"):
            head = s.split("=", 1)[0].strip()
            if head in kv:
                key = head
        if key is None:
            out.append(ln)
        elif key not in seen:
            seen.add(key)
            out.append("%s=%s" % (key, kv[key]))
        # 其余同键生效行：丢弃（systemd 对重复键的取值依赖行序，不许留歧义）

    missing = [k for k, _ in pairs if k not in seen]
    if missing:
        out.append("")
        if header:
            out.append("# ---- %s ----" % header)
        for k in missing:
            out.append("%s=%s" % (k, kv[k]))

    text = "\n".join(out)
    if not text.endswith("\n"):
        text += "\n"
    return text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--header", default="",
                    help="追加缺失键时，在追加段前写的表头注释文字")
    ap.add_argument("path", help="env 文件路径（原地修改）")
    ap.add_argument("pairs", nargs="+", help="KEY=VALUE，可多个")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.path):
        print("文件不存在：%s" % args.path, file=sys.stderr)
        return EXIT_NOFILE

    pairs = []
    for p in args.pairs:
        if "=" not in p:
            print("参数不是 KEY=VALUE：%r" % p, file=sys.stderr)
            return EXIT_USAGE
        pairs.append(tuple(p.split("=", 1)))

    text = upsert(args.path, pairs, args.header)
    with open(args.path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
