#!/usr/bin/env python3
"""把 deploy/units/*.service.tmpl 渲染成目标机的 systemd unit（ADR-017）。

为什么要模板化：unit 名、helper 路径、env 文件名、工作空间全都由 **app_id** 派生，
而老 unit 文件里 ``/home/djw/m20-ai-detect`` 与 ``m20-ai-detect`` 被写死了 4 处以上。
换到 Lite3 / IPC / UGV 就得手改多处、极易漏改（漏改的表现是服务起不来或读写错目录）。

用法：
    # 渲染缺省身份（=仓库里 m20-ai-*.service / m20-ai-console-helper / *.sudoers 本身）
    python3 deploy/render_units.py
    # 换身份 + 换部署路径
    python3 deploy/render_units.py --app-id lite3 --base-dir /home/ysc/lite3-ai-detect \
        --run-user ysc --run-group ysc --cpu-affinity 0-7 --memory-max 1G
    # 只渲染其中一个
    python3 deploy/render_units.py --unit detect --stdout
    # 校验仓库里的缺省成品与模板是否仍然一致（CI 用）
    python3 deploy/render_units.py --check

四种产出（都由同一组占位符渲染，保证彼此不漂移）：
    <app_id>-ai-detect.service      采样器 unit
    <app_id>-ai-console.service     控制台 unit
    <app_id>-ai-console-helper      控制台唯一的提权入口（装到 /usr/local/sbin/）
    <app_id>-ai-console.sudoers     该 helper 的 sudoers 白名单（装到 /etc/sudoers.d/）

占位符：``@@APP_ID@@`` ``@@BASE_DIR@@`` ``@@RUN_USER@@`` ``@@RUN_GROUP@@``
``@@PYTHON@@`` ``@@CPU_AFFINITY@@`` ``@@MEMORY_MAX@@``（仅 detect）``@@NICE@@``（仅 detect）。
未替换的占位符会以退出码 4 报错——unit 里残留 ``@@`` 会让 systemd 直接拒载。

退出码：0 成功；2 参数/文件问题；4 模板含未替换占位符；5 --check 发现漂移。
"""
from __future__ import annotations

import argparse
import os
import sys

# 按脚本位置定位 src/（不依赖 cwd）
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from m20_ai_detect.identity import (  # noqa: E402
    DEFAULT_APP_ID,
    IdentityError,
    check_app_id,
)

UNIT_DIR = os.path.join(_HERE, "units")
REPO_DEPLOY_DIR = _HERE

#: 四类产物的默认参数。helper/sudoers 只用到 APP_ID 与 BASE_DIR，
#: 但共享同一张取值表（少一张表就少一处漂移）。
DEFAULTS = {
    "detect": {
        "template": "ai-detect.service.tmpl",
        "out": "%s-ai-detect.service",
        "PYTHON": "/usr/bin/python3",
        "CPU_AFFINITY": "0-3",
        "MEMORY_MAX": "1G",
        "NICE": "5",
        "chmod": "644",
    },
    "console": {
        "template": "ai-console.service.tmpl",
        "out": "%s-ai-console.service",
        "PYTHON": "/usr/bin/python3",
        "CPU_AFFINITY": "0-3",
        "MEMORY_MAX": "256M",
        "NICE": "5",
        "chmod": "644",
    },
    "helper": {
        "template": "ai-console-helper.tmpl",
        "out": "%s-ai-console-helper",
        "PYTHON": "/usr/bin/python3",
        "CPU_AFFINITY": "0-3",
        "MEMORY_MAX": "256M",
        "NICE": "5",
        "chmod": "755",
    },
    "sudoers": {
        "template": "ai-console.sudoers.tmpl",
        "out": "%s-ai-console.sudoers",
        "PYTHON": "/usr/bin/python3",
        "CPU_AFFINITY": "0-3",
        "MEMORY_MAX": "256M",
        "NICE": "5",
        "chmod": "440",
    },
}


def render_text(template: str, values: dict) -> str:
    """把 ``@@KEY@@`` 占位符替换为 values 里的值；返回渲染后的文本。"""
    out = template
    for key, val in values.items():
        out = out.replace("@@" + key + "@@", str(val))
    return out


def unit_values(kind: str, args) -> dict:
    """合并默认值与命令行参数，得到该类产物的占位符取值。"""
    d = DEFAULTS[kind]
    vals = {
        "APP_ID": args.app_id,
        "BASE_DIR": args.base_dir.rstrip("/"),
        "RUN_USER": args.run_user,
        "RUN_GROUP": args.run_group,
        "PYTHON": args.python or d["PYTHON"],
        "CPU_AFFINITY": args.cpu_affinity or d["CPU_AFFINITY"],
        "MEMORY_MAX": args.memory_max or d["MEMORY_MAX"],
        "NICE": args.nice or d["NICE"],
    }
    # 模板里没有的占位符本就不存在，多余的键不会被替换（replace 无副作用）
    return vals


def render_unit(kind: str, args) -> str:
    tpl_path = os.path.join(UNIT_DIR, DEFAULTS[kind]["template"])
    with open(tpl_path, encoding="utf-8") as fh:
        template = fh.read()
    text = render_text(template, unit_values(kind, args))
    if "@@" in text:
        leftover = sorted(
            {tok.split("@@")[1] for tok in text.split("@@")[1::2]}
        )
        raise SystemExit(
            "模板 %s 有未替换的占位符：%s\n"
            "  （残留 @@ 会让 systemd 直接拒载，请检查 deploy/render_units.py 的取值表）"
            % (tpl_path, ", ".join(leftover) or "?")
        )
    if not text.endswith("\n"):
        text += "\n"
    return text


def out_name(kind: str, app_id: str) -> str:
    return DEFAULTS[kind]["out"] % app_id


def _write_stdout(text: str) -> None:
    """按 LF 写 stdout。

    Windows 的 ``sys.stdout`` 默认把 ``\\n`` 翻译成 ``\\r\\n``，会让
    ``--stdout | ssh ... 'cat > unit'`` 与 ``--check`` 的字节比对全部误判。
    """
    try:
        sys.stdout.reconfigure(newline="\n")
    except (AttributeError, ValueError):
        pass
    sys.stdout.write(text)


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--unit", choices=["detect", "console", "helper", "sudoers", "all"],
                    default="all")
    ap.add_argument("--app-id", default=DEFAULT_APP_ID,
                    help="部署身份（ADR-017）；缺省 m20")
    ap.add_argument("--base-dir", default="/home/djw/m20-ai-detect",
                    help="目标机上的项目根，会成为 WorkingDirectory/ReadWritePaths")
    ap.add_argument("--run-user", default="user", help="服务运行账户（默认 user）")
    ap.add_argument("--run-group", default="", help="服务运行组（默认与 --run-user 相同）")
    ap.add_argument("--python", default="", help="python3 绝对路径（默认 /usr/bin/python3）")
    ap.add_argument("--cpu-affinity", default="", help="CPUAffinity，如 0-3 / 0-7")
    ap.add_argument("--memory-max", default="", help="MemoryMax，如 1G / 256M")
    ap.add_argument("--nice", default="", help="Nice（仅 detect，默认 5）")
    ap.add_argument("--out-dir", default="", help="输出目录（缺省 deploy/ 自身）")
    ap.add_argument("--stdout", action="store_true", help="打印到 stdout 而不写文件")
    ap.add_argument("--check", action="store_true",
                    help="只比对不写文件：渲染结果与 out-dir 里已有文件不一致就报错")
    args = ap.parse_args()

    if not args.run_group:
        args.run_group = args.run_user
    try:
        args.app_id = check_app_id(args.app_id)
    except IdentityError as exc:
        print("app_id 非法：%s" % exc, file=sys.stderr)
        return 2

    kinds = list(DEFAULTS) if args.unit == "all" else [args.unit]
    out_dir = args.out_dir or REPO_DEPLOY_DIR
    rc = 0
    for kind in kinds:
        text = render_unit(kind, args)
        if args.stdout:
            # 分隔行必须写在产物**之前**（leading）：写成 trailing 的话，
            # 按分隔符切分的人每一块都会拿到上一块的名字（2026-10-19 实测踩到）。
            if len(kinds) > 1:
                _write_stdout("# ---- 8< ---- %s ----\n" % out_name(kind, args.app_id))
            _write_stdout(text)
            continue
        target = os.path.join(out_dir, out_name(kind, args.app_id))
        if args.check:
            if not os.path.isfile(target):
                print("  [缺失] %s（渲染后可生成）" % target)
                rc = 5
                continue
            with open(target, encoding="utf-8") as fh:
                current = fh.read()
            if current != text:
                print("  [漂移] %s 与模板不一致 → 重跑："
                      "python3 deploy/render_units.py --app-id %s --base-dir %s --out-dir %s"
                      % (target, args.app_id, args.base_dir, out_dir))
                rc = 5
            else:
                print("  [一致] %s" % target)
        else:
            os.makedirs(out_dir, exist_ok=True)
            with open(target, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            print("  写入 %s（%s）" % (target, DEFAULTS[kind]["chmod"]))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
