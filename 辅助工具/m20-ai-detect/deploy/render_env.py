#!/usr/bin/env python3
"""把 deploy/site.env 的取值渲染进配置模板（部署前统一配置的渲染器）。

用法：
    python3 deploy/render_env.py --kind detect  --site deploy/site.env --base-dir /home/djw/m20-ai-detect
    python3 deploy/render_env.py --kind console --site deploy/site.env --base-dir /home/djw/m20-ai-detect
    python3 deploy/render_env.py --kind detect --app-id lite3 --site deploy/site.env
    # 输出到 stdout；--out <path> 写文件

规则（刻意保持"可预测"，不做花哨的模板语法）：
  1. 只认 `^[A-Z][A-Z0-9_]*=` 的行，其余（注释/空行）原样保留；
  2. site 里**非空**的同名键覆盖模板值；空值视为"用模板默认"；
  3. site 里有、模板里没有的键，追加到末尾的「site 覆盖」段；
  4. `M20AI_BASE_DIR` / `M20AIC_BASE_DIR` 强制等于 --base-dir（避免与 unit 不一致）；
  5. 输出首行加一条注释，注明生成来源，便于现场核对；
  6. **身份（ADR-017）**：``APP_ID``（site 或 --app-id，缺省 ``m20``）决定运行时
     env 文件名 ``<BASE_DIR>/<APP_ID>-ai-detect.env``，并写成
     ``M20AI_APP_ID``（detect）/ ``M20AIC_APP_ID``（console）。
     **缺省身份不写这两个键** ⇒ 输出与改名改造前**逐字相同**，
     老部署零改动（app_id 由文件名前缀兜底反查，见 identity.scan_app_id）。

``APP_ID`` 是**部署期**键，只活在 site.env / 命令行里，不会被写进运行时 env
（运行时只用 ``M20AI_APP_ID`` / ``M20AIC_APP_ID``）。

退出码：0 成功；2 参数/文件问题；3 app_id 非法。
"""
from __future__ import annotations

import argparse
import os
import sys

# 本脚本在开发机（或部署机）上运行，需要 src/ 下的 identity 模块做校验。
# 按脚本位置定位（不依赖 cwd，`python3 /path/deploy/render_env.py` 也要能跑）。
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from m20_ai_detect.identity import (  # noqa: E402
    APP_ID_KEY,
    CONSOLE_APP_ID_KEY,
    DEFAULT_APP_ID,
    IdentityError,
    check_app_id,
)

#: 缺省身份 = 原 M20 部署。保持这个缺省才能保证"老 site.env 渲染出的文件不变"
DEFAULT_APP_ID = DEFAULT_APP_ID

KINDS = {
    "detect": "m20-ai-detect.env.example",
    "console": "m20-ai-console.env.example",
}

#: 部署期专用键：只在 site.env / 命令行出现，不写进运行时 env
DEPLOY_ONLY_KEYS = ("APP_ID",)

#: 每类模板对应的"身份键"（detect 用采样器的，console 用自己的）
APP_ID_KEY_OF_KIND = {"detect": APP_ID_KEY, "console": CONSOLE_APP_ID_KEY}


def env_file_name(app_id: str) -> str:
    """运行时 env 文件名（ADR-017：由 app_id 派生）。"""
    return "%s-ai-detect.env" % app_id


def runtime_env_path(base_dir: str, app_id: str) -> str:
    """控制台要读的采样器 env 路径。

    换 app_id 时它必须跟着 BASE_DIR 走，否则控制台会去读旧文件的配置
    （表现为"改了 env 页面不生效"）。缺省 app_id 下与历史输出逐字相同。
    """
    return base_dir.rstrip("/") + "/" + env_file_name(app_id)


def resolve_app_id(site: dict, kind: str, cli_value: str = "") -> str:
    """确定本次渲染的身份。

    优先级：``--app-id`` > site 的 ``APP_ID`` > site 里本类身份键 > 另一类身份键
    > 缺省 ``m20``。非法值抛 ``IdentityError``（main 捕获后以退出码 3 退出）。
    """
    raw = (cli_value or "").strip()
    if not raw:
        raw = (site.get("APP_ID") or "").strip()
    if not raw:
        raw = (site.get(APP_ID_KEY_OF_KIND[kind]) or "").strip()
    if not raw:
        other = CONSOLE_APP_ID_KEY if kind == "detect" else APP_ID_KEY
        raw = (site.get(other) or "").strip()
    if not raw:
        return DEFAULT_APP_ID
    return check_app_id(raw)


def _key_of(line: str):
    """取出一行的键名；注释行 / 无 '=' 行返回 None。"""
    if "=" not in line or line.lstrip().startswith("#"):
        return None
    return line.split("=", 1)[0]


def _upsert(lines: list, key: str, value: str) -> None:
    """就地替换/追加 ``key=value``（保持原有位置，尽量不打乱可读性）。"""
    for i, line in enumerate(lines):
        if _key_of(line) == key:
            lines[i] = "%s=%s" % (key, value)
            return
    lines.append("%s=%s" % (key, value))


def parse_env(path: str) -> dict:
    """读 KEY=VALUE 文件（忽略注释/空行/非法行）。"""
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


def render(
    template_path: str,
    site: dict,
    base_dir: str,
    kind: str,
    app_id: str = DEFAULT_APP_ID,
) -> str:
    app_id = app_id or DEFAULT_APP_ID
    with open(template_path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()

    base_key = "M20AI_BASE_DIR" if kind == "detect" else "M20AIC_BASE_DIR"
    env_key = {"detect": "M20AI_ENV_FILE", "console": "M20AIC_ENV_FILE"}.get(kind)
    app_id_key = APP_ID_KEY_OF_KIND[kind]
    #: helper 路径同样由 app_id 派生（identity.Identity.helper）
    helper_key = "M20AIC_HELPER" if kind == "console" else None
    helper_path = "/usr/local/sbin/%s-ai-console-helper" % app_id

    out, seen = [], set()
    for line in lines:
        key = _key_of(line)
        if key and key in site and site[key] != "":
            out.append("%s=%s" % (key, site[key]))
            seen.add(key)
        elif key == base_key:
            out.append("%s=%s" % (base_key, base_dir))
            seen.add(key)
        elif env_key and key == env_key:
            # 控制台要读采样器的 env；换身份时它必须跟着 BASE_DIR / APP_ID 走，
            # 否则控制台会去读旧文件的配置（表现为"改了 env 页面不生效"）
            out.append("%s=%s" % (env_key, runtime_env_path(base_dir, app_id)))
            seen.add(env_key)
        elif helper_key and key == helper_key:
            out.append("%s=%s" % (helper_key, helper_path))
            seen.add(helper_key)
        else:
            out.append(line)

    # 模板里没有、site 里给了的键 → 追加（含 base_dir 之外的）
    extra = [
        k for k, v in site.items()
        if v != "" and k not in seen and k not in KINDS.values()
        and k not in DEPLOY_ONLY_KEYS and not k.startswith("DEPLOY_")
    ]
    if base_key not in seen:
        # 模板里没有 base 键时也要保证落地
        extra.insert(0, base_key)
        site = dict(site)
        site[base_key] = base_dir
    if extra:
        out.append("")
        out.append("# ---- 由 deploy/site.env 追加（模板中无此键）----")
        for k in extra:
            out.append("%s=%s" % (k, site[k]))

    # ---- 身份（ADR-017）----
    # 只在非缺省身份时写：缺省时一行都不加，保证老 site.env 渲染结果逐字不变。
    # app_id 另有"文件名前缀兜底"（identity.scan_app_id），缺省时不写也能反查到。
    if app_id != DEFAULT_APP_ID:
        out.append("")
        out.append("# ---- 身份（ADR-017）：site.env 的 APP_ID=%s ----" % app_id)
        _upsert(out, app_id_key, app_id)

    header = "# 由 deploy/render_env.py 生成（模板 %s + site.env）—— 现场改值请直接改本文件" % (
        template_path.rsplit("/", 1)[-1]
    )
    return "\n".join([header] + out) + "\n"


def _write_stdout(text: str) -> None:
    """按 LF 写 stdout（Windows 默认会把 ``\\n`` 翻成 ``\\r\\n``，破坏字节级回归）。"""
    try:
        sys.stdout.reconfigure(newline="\n")
    except (AttributeError, ValueError):
        pass
    sys.stdout.write(text)


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--kind", choices=sorted(KINDS), default="detect")
    ap.add_argument("--site", default="deploy/site.env")
    ap.add_argument("--template", default="")
    ap.add_argument("--base-dir", default="",
                    help="目标机上的项目根；Windows Git Bash 下改用环境变量 RENDER_BASE_DIR")
    ap.add_argument("--app-id", default="",
                    help="部署身份（ADR-017）：决定 unit 名/env 文件名/helper 路径；"
                         "缺省 m20。也可写在 site.env 的 APP_ID= 里")
    ap.add_argument("--out", default="-")
    args = ap.parse_args()

    site = parse_env(args.site) if args.site else {}
    try:
        app_id = resolve_app_id(site, args.kind, args.app_id)
    except IdentityError as exc:
        print("app_id 非法：%s" % exc, file=sys.stderr)
        return 3
    # base_dir 来源优先级：--base-dir > site 里的 DEPLOY_DIR > 环境变量 > 模板默认值。
    # 之所以优先用 site 文件：Windows Git Bash（MSYS）会把 **命令行与环境变量里** 的
    # "/home/..." 改写成 "C:/Program Files/..."，而**文件内容不会被改写**。
    base_dir = (
        args.base_dir
        or site.get("DEPLOY_DIR", "")
        or os.environ.get("RENDER_BASE_DIR", "")
        or os.environ.get("M20AI_BASE_DIR", "")
    )
    tpl = args.template or ("deploy/" + KINDS[args.kind])
    text = render(tpl, site, base_dir, args.kind, app_id)

    if args.out == "-":
        _write_stdout(text)
    else:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
