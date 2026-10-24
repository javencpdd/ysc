#!/usr/bin/env python3
"""把 deploy/site.env 的取值渲染进配置模板（改造前版本的复刻，仅用于字节级回归对比）。"""
from __future__ import annotations

import argparse
import os
import sys

DEFAULT_APP_ID = "m20"

KINDS = {
    "detect": "m20-ai-detect.env.example",
    "console": "m20-ai-console.env.example",
}


def parse_env(path: str) -> dict:
    out: dict = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line or line.lstrip().startswith("#"):
                    continue
                key, sep, val = line.partition("=")
                if not sep or not key or not key.replace("_", "").isalnum():
                    continue
                if key[0].isdigit() or key != key.upper():
                    continue
                out[key.strip()] = val
    except OSError as exc:
        print("读取 %s 失败：%s" % (path, exc), file=sys.stderr)
        raise SystemExit(2)
    return out


def render(template_path: str, site: dict, base_dir: str, kind: str) -> str:
    with open(template_path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    base_key = "M20AI_BASE_DIR" if kind == "detect" else "M20AIC_BASE_DIR"
    env_key = {"detect": "M20AI_ENV_FILE", "console": "M20AIC_ENV_FILE"}.get(kind)

    out, seen = [], set()
    for line in lines:
        key = line.split("=", 1)[0] if "=" in line and not line.lstrip().startswith("#") else None
        if key and key in site and site[key] != "":
            out.append("%s=%s" % (key, site[key]))
            seen.add(key)
        elif key == base_key:
            out.append("%s=%s" % (base_key, base_dir))
            seen.add(key)
        elif env_key and key == env_key:
            out.append("%s=%s" % (env_key, base_dir.rstrip("/") + "/m20-ai-detect.env"))
            seen.add(env_key)
        else:
            out.append(line)

    extra = [
        k for k, v in site.items()
        if v != "" and k not in seen and k not in KINDS.values() and not k.startswith("DEPLOY_")
    ]
    if base_key not in seen:
        extra.insert(0, base_key)
        site = dict(site)
        site[base_key] = base_dir
    if extra:
        out.append("")
        out.append("# ---- 由 deploy/site.env 追加（模板中无此键）----")
        for k in extra:
            out.append("%s=%s" % (k, site[k]))

    header = "# 由 deploy/render_env.py 生成（模板 %s + site.env）—— 现场改值请直接改本文件" % (
        template_path.rsplit("/", 1)[-1]
    )
    return "\n".join([header] + out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--kind", choices=sorted(KINDS), default="detect")
    ap.add_argument("--site", default="deploy/site.env")
    ap.add_argument("--template", default="")
    ap.add_argument("--base-dir", default="",
                    help="目标机上的项目根；Windows Git Bash 下改用环境变量 RENDER_BASE_DIR")
    ap.add_argument("--out", default="-")
    args = ap.parse_args()

    site = parse_env(args.site) if args.site else {}
    base_dir = (
        args.base_dir
        or site.get("DEPLOY_DIR", "")
        or os.environ.get("RENDER_BASE_DIR", "")
        or os.environ.get("M20AI_BASE_DIR", "")
    )
    tpl = args.template or ("deploy/" + KINDS[args.kind])
    text = render(tpl, site, base_dir, args.kind)

    if args.out == "-":
        sys.stdout.write(text)
    else:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
