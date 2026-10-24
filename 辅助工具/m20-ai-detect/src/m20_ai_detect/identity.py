"""身份与命名（ADR-017）：一次配置，处处生效。

历史包袱：``m20`` 被写死在 5 类地方 —— systemd unit 名、helper 脚本名、env 文件名、
journal 标识符、UI 展示名。换到 Lite3 / IPC / UGV 就处处不合身，而改名要连带动
unit（4 处硬编码路径）、helper、sudoers、安装脚本、文档，成本极高且易错。

现在这些都由 **app_id** 派生。app_id 来自环境变量 ``M20AI_APP_ID``（部署时由
``deploy/site.env`` 的 ``APP_ID`` 渲染写入），缺省 ``m20`` ⇒ **老部署零改动**。

约束
----
1. app_id 会成为文件路径与 unit 名的一部分，字符集必须收紧（``APP_ID_RE``），
   非法值在配置阶段就报错，而不是等到 systemd 报 "Unit name ... is not valid"。
2. 本模块**不读文件、不依赖其它模块**（除 stdlib），任何地方都能安全 import，
   也不参与 Config 的构造（避免与 Config 形成循环依赖）。
3. Python 包名 ``m20_ai_detect`` **不参与本抽象** —— import 路径是静态的，
   不可能"运行时改名"。对外的名字（服务/脚本/文件/展示）全部可配，足够了。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

#: 运行时 env 键（由 deploy 的 APP_ID 渲染写入）
APP_ID_KEY = "M20AI_APP_ID"
PLATFORM_KEY = "M20AI_PLATFORM_NAME"
PROFILE_KEY = "M20AI_PROFILE"
BASE_DIR_KEY = "M20AI_BASE_DIR"
#: 控制台自身 env 键（优先级最高，见 discover_app_id）
CONSOLE_APP_ID_KEY = "M20AIC_APP_ID"

#: 缺省身份 = 原 M20 部署，保证 104 上跑着的那份行为完全不变
DEFAULT_APP_ID = "m20"

#: app_id → unit 名 / helper 名 / 文件名的片段，字符集按 systemd unit 规则收紧
APP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")

#: profile → 展示名。profile 本身只是"一组默认值"（见 ADR-016 §4），
#: 这里的映射仅供未显式设 PLATFORM_NAME 时兜底，缺了也不该炸。
PROFILE_TITLES: Dict[str, str] = {
    "m20pro-dual": "M20 Pro · 双目",
    "lite3-single": "Lite3 · 单目",
    "ipc-generic": "IPC · ONVIF",
    "local-usb": "本地相机",
}


class IdentityError(ValueError):
    """身份配置非法（app_id 字符集/为空等）。"""


def check_app_id(app_id: str) -> str:
    """校验并返回规范化的 app_id；非法直接抛 IdentityError（消息可操作）。"""
    val = (app_id or "").strip()
    if not val:
        raise IdentityError("%s 为空；不设即缺省 %r" % (APP_ID_KEY, DEFAULT_APP_ID))
    if not APP_ID_RE.match(val):
        raise IdentityError(
            "%s=%r 非法：只能含字母/数字/下划线/连字符，最长 32 位，且必须以字母或数字开头"
            % (APP_ID_KEY, app_id)
        )
    return val


@dataclass(frozen=True)
class Identity:
    """一次部署的身份：决定所有对外可见的名字。"""

    app_id: str = DEFAULT_APP_ID
    platform_name: str = ""
    profile: str = ""
    base_dir: str = ""

    # ---------------- systemd ----------------
    @property
    def unit(self) -> str:
        return "%s-ai-detect.service" % self.app_id

    @property
    def console_unit(self) -> str:
        return "%s-ai-console.service" % self.app_id

    @property
    def unit_name(self) -> str:
        """``systemctl`` / ``journalctl -u`` 用的名字（不带 .service）。"""
        return "%s-ai-detect" % self.app_id

    @property
    def console_unit_name(self) -> str:
        return "%s-ai-console" % self.app_id

    @property
    def units(self) -> List[str]:
        return [self.unit_name, self.console_unit_name]

    # ---------------- 文件 ----------------
    @property
    def helper(self) -> str:
        return "/usr/local/sbin/%s-ai-console-helper" % self.app_id

    @property
    def sudoers(self) -> str:
        return "/etc/sudoers.d/%s-ai-console" % self.app_id

    @property
    def env_basename(self) -> str:
        return "%s-ai-detect.env" % self.app_id

    @property
    def console_env_basename(self) -> str:
        return "%s-ai-console.env" % self.app_id

    @property
    def env_file(self) -> str:
        """运行时 env 文件路径（无 base_dir 时退化为仅文件名）。"""
        if not self.base_dir:
            return self.env_basename
        return os.path.join(self.base_dir, self.env_basename)

    # ---------------- 展示 ----------------
    @property
    def display(self) -> str:
        """UI 顶栏 / 日志里给人看的名字。优先级：显式 > profile 兜底 > app_id。"""
        if self.platform_name.strip():
            return self.platform_name.strip()
        return PROFILE_TITLES.get(self.profile, self.app_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_id": self.app_id,
            "platform_name": self.platform_name,
            "profile": self.profile,
            "base_dir": self.base_dir,
            "display": self.display,
            "unit": self.unit_name,
            "console_unit": self.console_unit_name,
            "helper": self.helper,
            "env_file": self.env_file,
        }

    # ---------------- 构造 ----------------
    @classmethod
    def from_env(
        cls, env: Optional[Dict[str, str]] = None, base_dir: str = ""
    ) -> "Identity":
        """从运行时 env 构造。``env`` 缺省取 os.environ（真机用法）。

        base_dir 通常由调用方从 Config.base_dir 传入（避免重复解析）；
        拿不到时退化为读 ``M20AI_BASE_DIR``。
        """
        env = os.environ if env is None else env
        app_raw = (env.get(APP_ID_KEY) or "").strip() or DEFAULT_APP_ID
        return cls(
            app_id=check_app_id(app_raw),
            platform_name=(env.get(PLATFORM_KEY) or "").strip(),
            profile=(env.get(PROFILE_KEY) or "").strip(),
            base_dir=base_dir or (env.get(BASE_DIR_KEY) or "").strip(),
        )


def env_file_candidates(base_dir: str, app_id: str) -> List[str]:
    """env 文件的查找顺序（先新后旧，保证改名迁移期两边都能跑）。

    1. ``<base>/<app_id>-ai-detect.env``
    2. ``<base>/m20-ai-detect.env``  ← 老部署（含 app_id=m20 的默认安装）

    存在鸡生蛋问题：要先读 env 才知道 app_id，而文件名又依赖 app_id。
    解法就是"两边都找"，显式指定（``M20AIC_ENV_FILE``）优先级最高，由调用方处理。
    """
    if not base_dir:
        return []
    out = [os.path.join(base_dir, "%s-ai-detect.env" % app_id)]
    legacy = os.path.join(base_dir, "m20-ai-detect.env")
    if legacy not in out:
        out.append(legacy)
    return out


def resolve_env_file(base_dir: str, app_id: str = DEFAULT_APP_ID) -> Optional[str]:
    """按 env_file_candidates 顺序返回**第一个真实存在**的文件；都不存在返回 None。"""
    for path in env_file_candidates(base_dir, app_id):
        if os.path.isfile(path):
            return path
    return None


def _read_app_id_from(path: str) -> str:
    """从单个 env 文件里抠出 ``M20AI_APP_ID``。单行扫描，不引入 parser 依赖。

    任何读失败都按"没写"处理（返回空串）—— 身份解析不能因为一个坏文件炸掉。
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                if key.strip() != APP_ID_KEY:
                    continue
                return val.strip().strip("'\"")
    except OSError:
        pass
    return ""


def list_app_ids(base_dir: str) -> List[str]:
    """扫描 ``<base>/*-ai-detect.env``，返回其中出现的 app_id 列表（去重、排序稳定）。

    用于"改名迁移期两边都能跑"：目录里同时存在 ``lite3-ai-detect.env`` 与
    ``m20-ai-detect.env`` 时，两者都会被发现。
    """
    if not base_dir:
        return []
    try:
        names = sorted(os.listdir(base_dir))
    except OSError:
        return []
    out: List[str] = []
    for name in names:
        if not name.endswith("-ai-detect.env"):
            continue
        app = name[: -len("-ai-detect.env")]
        if app and app not in out:
            out.append(app)
    return out


def scan_app_id(base_dir: str) -> str:
    """从 env 文件内容里反查 app_id；查不到返回缺省 ``m20``。

    优先级：文件内显式写死的 ``M20AI_APP_ID`` > 文件名前缀 ``<id>-ai-detect.env``。
    """
    for app in list_app_ids(base_dir):
        val = _read_app_id_from(os.path.join(base_dir, "%s-ai-detect.env" % app))
        if val:
            try:
                return check_app_id(val)
            except IdentityError:
                continue
        try:
            return check_app_id(app)
        except IdentityError:
            continue
    return DEFAULT_APP_ID


def discover_app_id(base_dir: str, env: Optional[Dict[str, str]] = None) -> str:
    """控制台/CLI 起步时确定 app_id（解决"文件名依赖 app_id，而 app_id 在文件里"）。

    1. 控制台自身 env ``M20AIC_APP_ID``（install 渲染写入）最高优先；
    2. 否则扫 ``<base>/*-ai-detect.env`` 反查；
    3. 都没有 → 缺省 ``m20``（老部署零改动）。
    """
    explicit = ((env or {}).get(CONSOLE_APP_ID_KEY) or "").strip()
    if explicit:
        return check_app_id(explicit)
    return scan_app_id(base_dir)
