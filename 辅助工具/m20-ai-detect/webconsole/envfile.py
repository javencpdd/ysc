"""m20-ai-detect.env 的读取 / 改写 / 校验。

设计约束：
  * 保留文件里的注释与分段——手工编辑的 env 是用户的，不能被重排；
  * 写前必须整份校验（当前值 + 改动合并后过 Config.from_env），
    非法配置绝不落盘（坏配置曾导致 doctor 起不来，见部署记录）；
  * 需要 shell 安全的引号规则：含 JSON/空格的值用单引号包裹
    （bash source 与 systemd EnvironmentFile 都认，双引号会被剥）。
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Tuple

from m20_ai_detect.config import Config, ConfigError

_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def shell_quote(value: str) -> str:
    """按 bash/systemd 通用规则加引号。空值与纯标识符原样返回。"""
    if value == "":
        return ""
    if re.fullmatch(r"[A-Za-z0-9_./:=@%+,-]+", value):
        return value
    if "'" not in value:
        return "'%s'" % value
    raise ValueError("值包含单引号，无法安全引用：%r" % value[:40])


def read_env(path: str) -> Dict[str, str]:
    """读 env 文件为 dict（忽略注释与空行；同键取最后一次）。"""
    out: Dict[str, str] = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            m = _KEY_RE.match(line)
            if m:
                out[m.group(1)] = _unquote(m.group(2))
    return out


def _unquote(raw: str) -> str:
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
        return raw[1:-1]
    return raw


def set_env_keys(path: str, updates: Dict[str, str]) -> None:
    """就地修改/追加键值，保留注释与其他行。文件不存在则创建。"""
    updates = dict(updates)
    lines: List[str] = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            lines = [ln.rstrip("\n") for ln in fh]
    for i, line in enumerate(lines):
        m = _KEY_RE.match(line)
        if not m:
            continue
        key = m.group(1)
        if key in updates:
            lines[i] = "%s=%s" % (key, shell_quote(updates.pop(key)))
    for key, value in updates.items():  # 新键追加到末尾
        lines.append("%s=%s" % (key, shell_quote(value)))
    tmp = path + ".console-tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, path)


def validate_env(current: Dict[str, str], updates: Dict[str, str]) -> Tuple[bool, List[str]]:
    """合并后整份校验。返回 (ok, errors)。"""
    merged = dict(current)
    merged.update(updates)
    try:
        Config.from_env(merged)
    except ConfigError as exc:
        return False, [str(exc)]
    except Exception as exc:  # 防御：任何解析意外都按配置错误处理
        return False, ["%s: %s" % (type(exc).__name__, exc)]
    return True, []
