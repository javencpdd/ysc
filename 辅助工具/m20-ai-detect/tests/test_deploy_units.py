"""部署工具链的契约测试：render_env.py（env 渲染）+ render_units.py（unit 渲染）。

覆盖的关键不变量：
  A. **向后兼容**：缺省身份（app_id=m20）时，渲染结果与改名改造前**逐字相同**
     —— 老 site.env / 老 bootstrap.sh 零改动；
  B. **改名生效**：APP_ID 一改，unit 名 / env 文件名 / helper 路径 / sudoers 路径
     全部跟着变，且不允许残留 ``@@`` 占位符；
  C. **模板与成品同步**：仓库里提交的 m20-ai-*.service 必须能由模板重新渲染出来
     （否则现场改名会基于一份过时的模板）。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RENDER = os.path.join(ROOT, "deploy", "render_env.py")
UNITS = os.path.join(ROOT, "deploy", "render_units.py")
DEPLOY = os.path.join(ROOT, "deploy")


def _write_site(site_text: str) -> str:
    """把 site 文本落成临时文件，返回路径（调用方负责删）。"""
    fh = tempfile.NamedTemporaryFile("w", suffix=".env", delete=False, encoding="utf-8")
    fh.write(site_text)
    fh.close()
    return fh.name


def _run(script: str, argv, cwd=ROOT, text=False):
    return subprocess.run(
        [sys.executable, script] + argv,
        cwd=cwd, capture_output=True, timeout=60, text=text, encoding="utf-8",
    )


def _out(proc) -> str:
    """把 CompletedProcess 的 stdout/stderr 解成文本（断言可读性用）。"""
    def dec(b):
        return b.decode("utf-8", "replace") if isinstance(b, bytes) else b
    return dec(proc.stdout) + "\n--- stderr ---\n" + dec(proc.stderr)


def render_env(site_text: str, kind: str = "detect", extra=()):
    """渲染 env 并返回 (returncode, stdout_text, stderr_text)。"""
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False, encoding="utf-8") as fh:
        fh.write(site_text)
        path = fh.name
    try:
        out = _run(RENDER, ["--kind", kind, "--site", path] + list(extra))
    finally:
        os.unlink(path)
    return out.returncode, out.stdout, out.stderr


def render_env_text(site_text: str, kind: str = "detect", extra=()) -> str:
    rc, text, err = render_env(site_text, kind, extra)
    if rc != 0:
        raise AssertionError("render_env 失败 rc=%s：%s" % (rc, err))
    return text


def render_env_bytes(site_text: str, kind: str = "detect", extra=()) -> bytes:
    """按**原始字节**取渲染结果（用于字节级向后兼容断言）。"""
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False, encoding="utf-8") as fh:
        fh.write(site_text)
        path = fh.name
    try:
        out = subprocess.run(
            [sys.executable, RENDER, "--kind", kind, "--site", path] + list(extra),
            cwd=ROOT, capture_output=True, timeout=60,
        )
    finally:
        os.unlink(path)
    if out.returncode != 0:
        raise AssertionError("render_env 失败 rc=%s：%s" % (out.returncode, out.stderr))
    return out.stdout.replace(b"\r\n", b"\n")


def active_lines(text: str) -> list:
    """只取**生效行**（去掉空行与注释）——unit/env 里的注释是文档，不该参与路径断言。"""
    return [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


class TestRenderEnv(unittest.TestCase):
    def test_site_overrides_and_empty_keeps_default(self):
        text = render_env_text(
            "DEPLOY_DIR=/home/user/m20-ai-detect\n"
            "M20AI_ENABLE_B=1\n"
            "M20AI_SRC_F=rtsp://10.0.0.9:8554/video1\n"
            "M20AI_AI_BASE=\n"          # 空值 → 用模板默认
        )
        self.assertIn("M20AI_ENABLE_B=1", text)
        self.assertIn("M20AI_SRC_F=rtsp://10.0.0.9:8554/video1", text)
        self.assertIn("M20AI_AI_BASE=http://jsxy.aihyzh.com:30881", text)

    def test_base_dir_comes_from_deploy_dir(self):
        text = render_env_text("DEPLOY_DIR=/opt/m20-ai-detect\n")
        self.assertIn("M20AI_BASE_DIR=/opt/m20-ai-detect", text)
        self.assertNotIn("M20AI_BASE_DIR=/home/djw/m20-ai-detect", text)

    def test_extra_keys_appended(self):
        text = render_env_text("DEPLOY_DIR=/home/user/x\nM20AI_CUSTOM_TEST_KEY=1\n")
        self.assertIn("M20AI_CUSTOM_TEST_KEY=1", text)
        self.assertIn("由 deploy/site.env 追加", text)

    def test_template_key_is_overridden_not_appended(self):
        text = render_env_text("DEPLOY_DIR=/home/user/x\nM20AI_SPOOL_MAX_FILES=300\n")
        self.assertIn("M20AI_SPOOL_MAX_FILES=300", text)
        self.assertNotIn("M20AI_SPOOL_MAX_FILES=600", text)

    def test_console_kind_uses_console_keys(self):
        text = render_env_text("DEPLOY_DIR=/home/user/x\nM20AIC_PORT=6060\n", kind="console")
        self.assertIn("M20AIC_PORT=6060", text)
        self.assertIn("M20AIC_BASE_DIR=/home/user/x", text)
        self.assertIn("M20AIC_ENV_FILE=/home/user/x/m20-ai-detect.env", text)

    def test_header_marks_generated(self):
        text = render_env_text("DEPLOY_DIR=/home/user/x\n")
        self.assertTrue(text.startswith("# 由 deploy/render_env.py 生成"), text.splitlines()[0])

    def test_stdout_uses_lf_only(self):
        """Windows 上 stdout 默认会把 \n 翻成 \r\n，会让 ssh 'cat > unit' 写出 CRLF。"""
        raw = render_env_bytes("DEPLOY_DIR=/home/user/x\n")
        self.assertNotIn(b"\r", raw)


# ---------------------------------------------------------------- 身份（ADR-017）
class TestRenderEnvIdentity(unittest.TestCase):
    """改名能力 + 缺省身份字节级不变。"""

    def test_default_identity_writes_no_app_id_key(self):
        """缺省 m20：一行身份键都不写 —— 靠文件名前缀兜底反查。"""
        for kind in ("detect", "console"):
            text = render_env_text("DEPLOY_DIR=/home/user/x\n", kind=kind)
            self.assertNotIn("M20AI_APP_ID=", text)
            self.assertNotIn("M20AIC_APP_ID=", text)

    def test_default_identity_byte_identical_to_legacy(self):
        """与改造前的渲染器逐字相同（CRLF 归一化后；旧版在 Windows 上会吐 CRLF）。

        快照 ``tests/fixtures/render_env_legacy.py`` 是 ADR-017 改造**之前**的
        render_env.py，只读不改。谁把新版的缺省输出改花了，这个测试就红。
        """
        legacy = os.path.join(ROOT, "tests", "fixtures", "render_env_legacy.py")
        self.assertTrue(os.path.isfile(legacy), legacy)
        sites = (
            "DEPLOY_DIR=/opt/x\n",
            "DEPLOY_DIR=/opt/x\nM20AIC_PORT=1\n",
            "DEPLOY_DIR=/opt/x\nM20AI_CUSTOM=9\nM20AI_ENABLE_B=\n",
        )
        for kind in ("detect", "console"):
            for site in sites:
                out = _run(legacy, ["--kind", kind, "--site", _write_site(site)], text=True)
                self.assertEqual(out.returncode, 0, out.stderr)
                old = out.stdout.replace("\r\n", "\n").encode("utf-8")
                self.assertEqual(old, render_env_bytes(site, kind=kind),
                                 "kind=%s site=%r 输出与改造前不同" % (kind, site))

    def test_app_id_from_site_renames_everything(self):
        site = "DEPLOY_DIR=/opt/lite3\nAPP_ID=lite3\n"
        detect = render_env_text(site, kind="detect")
        self.assertIn("M20AI_APP_ID=lite3", detect)
        # 部署期键 APP_ID 不许落进运行时 env（会被当成未知键带进 systemd 环境）
        self.assertNotIn("APP_ID=lite3", active_lines(detect))

        console = render_env_text(site, kind="console")
        self.assertIn("M20AIC_APP_ID=lite3", console)
        self.assertIn("M20AIC_ENV_FILE=/opt/lite3/lite3-ai-detect.env", console)
        self.assertIn("M20AIC_HELPER=/usr/local/sbin/lite3-ai-console-helper", console)
        self.assertIn("M20AIC_BASE_DIR=/opt/lite3", console)

    def test_cli_app_id_beats_site(self):
        site = "DEPLOY_DIR=/opt/x\nAPP_ID=lite3\n"
        text = render_env_text(site, kind="detect", extra=["--app-id", "ugv-1"])
        self.assertIn("M20AI_APP_ID=ugv-1", text)
        self.assertNotIn("M20AI_APP_ID=lite3", text)

    def test_app_id_from_runtime_key_in_site(self):
        """老 site.env 可能已经手写了 M20AI_APP_ID，也要被认出来。"""
        text = render_env_text(
            "DEPLOY_DIR=/opt/x\nM20AI_APP_ID=ipc-a\n", kind="detect")
        self.assertIn("M20AI_APP_ID=ipc-a", text)

    def test_invalid_app_id_exits_3(self):
        # 用 --app-id=<值> 形式，避免 argparse 把 "-lead" 当成选项
        for bad in ("bad id!", "-lead", "a" * 33, "id.with.dots"):
            rc, _, err = render_env(
                "DEPLOY_DIR=/opt/x\n", kind="detect", extra=["--app-id=" + bad])
            self.assertEqual(rc, 3, "app_id=%r 应被拒（stderr=%s）" % (bad, err))
            self.assertIn("非法", err)

    def test_app_id_accepts_hyphen_and_underscore(self):
        text = render_env_text("DEPLOY_DIR=/opt/x\nAPP_ID=ugv_1-a\n", kind="detect")
        self.assertIn("M20AI_APP_ID=ugv_1-a", text)


# ---------------------------------------------------------------- unit 渲染
class TestRenderUnits(unittest.TestCase):
    def test_default_render_matches_committed_units(self):
        """仓库里的 m20-ai-*.service 必须能由模板重新渲染出来（防模板漂移）。"""
        for kind, fname in (("detect", "m20-ai-detect.service"),
                            ("console", "m20-ai-console.service")):
            out = _run(UNITS, ["--unit", kind, "--stdout"], text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            with open(os.path.join(DEPLOY, fname), "rb") as fh:
                committed = fh.read().decode("utf-8")
            self.assertEqual(
                committed.replace("\r\n", "\n"), out.stdout.replace("\r\n", "\n"),
                "%s 与 deploy/units/*.tmpl 不一致：重跑 python3 deploy/render_units.py" % fname)

    def test_check_mode_is_clean_for_repo(self):
        out = _run(UNITS, ["--check"], text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("[一致]", out.stdout)

    def test_helper_and_sudoers_committed_match_templates(self):
        """helper/sudoers 也是模板渲染的（ADR-017）：提交的成品不许漂移。

        白名单指向的 helper 路径、helper 里写死的 unit 名只要和 unit 差一个
        身份，控制台的"重启服务/清日志"按钮就会以 root 权限调用一个不存在
        的命令——所以这两类产物与 unit 共用同一份渲染结果。
        """
        for kind, fname in (("helper", "m20-ai-console-helper"),
                            ("sudoers", "m20-ai-console.sudoers")):
            out = _run(UNITS, ["--unit", kind, "--stdout"], text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            with open(os.path.join(DEPLOY, fname), "rb") as fh:
                committed = fh.read().decode("utf-8")
            self.assertEqual(
                committed.replace("\r\n", "\n"), out.stdout.replace("\r\n", "\n"),
                "%s 与 deploy/units/*.tmpl 不一致：重跑 python3 deploy/render_units.py" % fname)

    def test_helper_renders_as_valid_bash(self):
        """helper 以 root 跑，模板里一个引号/sed 写错就是现场安全事故。

        Windows 上 ``which bash`` 可能命中 System32 的 WSL 存根（-n 直接失败），
        所以先用一个已知合法的探针脚本筛出**真 bash**，筛不到就 skip。
        """
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            out = _run(UNITS, ["--unit", "helper", "--app-id", "lite3",
                               "--base-dir", "/home/ysc/lite3-ai-detect",
                               "--out-dir", tmp], text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            path = os.path.join(tmp, "lite3-ai-console-helper")
            probe = os.path.join(tmp, "_probe.sh")
            with open(probe, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("#!/bin/sh\necho ok\n")
            cands = [shutil.which("bash"), r"C:\Program Files\Git\bin\bash.exe"]
            real = None
            for cand in cands:
                if not cand or not os.path.isfile(cand):
                    continue
                try:
                    if subprocess.run([cand, "-n", probe], capture_output=True,
                                      timeout=30).returncode == 0:
                        real = cand
                        break
                except OSError:
                    continue
            if real is None:
                self.skipTest("本机没有可用的真 bash（WSL 存根不算）")
            chk = subprocess.run([real, "-n", path], capture_output=True, text=True)
            self.assertEqual(chk.returncode, 0, chk.stderr)

    def test_helper_and_sudoers_follow_app_id(self):
        """改名后 helper/sudoers 必须整套换身份（否则 sudoers 白名单会悬空）。"""
        out = _run(UNITS, [
            "--unit", "all", "--app-id", "lite3",
            "--base-dir", "/home/ysc/lite3-ai-detect",
            "--run-user", "ysc", "--stdout",
        ], text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        # --unit all 用 "# ---- 8< ---- <name> ----" 分隔四类产物
        parts = {}
        chunks = out.stdout.split("# ---- 8< ---- ")
        for chunk in chunks[1:]:
            name, _, body = chunk.partition(" ----\n")
            parts[name] = body
        self.assertIn("lite3-ai-console-helper", parts)
        self.assertIn("lite3-ai-console.sudoers", parts)

        helper = active_lines(parts["lite3-ai-console-helper"])
        joined = "\n".join(helper)
        self.assertIn("BASE=/home/ysc/lite3-ai-detect", helper)
        self.assertIn('systemctl "$verb" lite3-ai-detect', joined)
        self.assertIn('systemctl "$verb" lite3-ai-console', joined)
        self.assertIn("logger -t lite3-ai-console-helper", joined)
        self.assertIn("# lite3-ai-console managed begin", joined)
        self.assertIn("F=/etc/logrotate.d/lite3-ai-detect", joined)
        for line in helper:
            self.assertNotIn("/home/djw", line, line)
            self.assertNotIn("m20-", line, line)

        sudoers = parts["lite3-ai-console.sudoers"]
        self.assertNotIn("m20-ai-console-helper", sudoers)
        # 13 条白名单必须一条不少地指向新身份
        self.assertEqual(sudoers.count("/usr/local/sbin/lite3-ai-console-helper"), 13)
        self.assertIn("NOPASSWD", sudoers)
        self.assertNotIn("@@", sudoers)

    def test_sudoers_drift_detected(self):
        """sudoers 漂移也要报 5（装错白名单比 unit 漂移更危险）。"""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "m20-ai-console.sudoers")
            with open(target, "w", encoding="utf-8") as fh:
                fh.write("# stale\nuser ALL=(root) NOPASSWD: /bin/sh\n")
            out = _run(UNITS, ["--unit", "sudoers", "--out-dir", tmp, "--check"], text=True)
            self.assertEqual(out.returncode, 5, out.stdout + out.stderr)
            self.assertIn("[漂移]", out.stdout)

    def test_rename_rewrites_all_paths_and_keeps_no_placeholder(self):
        out = _run(UNITS, [
            "--unit", "all", "--app-id", "lite3",
            "--base-dir", "/home/ysc/lite3-ai-detect",
            "--run-user", "ysc", "--run-group", "ysc",
            "--cpu-affinity", "0-7", "--memory-max", "1G", "--stdout",
        ], text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        text = out.stdout
        self.assertNotIn("@@", text)
        active = active_lines(text)
        self.assertTrue(active)
        # 老身份的任何痕迹都不许留在**生效行**里（注释里的参考部署说明除外）
        for line in active:
            self.assertNotIn("/home/djw", line, line)
            self.assertNotIn("m20-ai-detect", line.replace("lite3-ai-detect", ""), line)
        joined = "\n".join(active)
        self.assertIn("Description=lite3-ai-detect:", joined)
        self.assertIn("Description=lite3-ai-console:", joined)
        self.assertIn("SyslogIdentifier=lite3-ai-detect", joined)
        self.assertIn("User=ysc", joined)
        self.assertIn("Group=ysc", joined)
        self.assertIn("WorkingDirectory=/home/ysc/lite3-ai-detect", joined)
        self.assertIn("EnvironmentFile=/home/ysc/lite3-ai-detect/lite3-ai-detect.env", joined)
        self.assertIn("EnvironmentFile=/home/ysc/lite3-ai-detect/lite3-ai-console.env", joined)
        self.assertIn("ReadWritePaths=/home/ysc/lite3-ai-detect", joined)
        self.assertIn("CPUAffinity=0-7", joined)

    def test_run_group_defaults_to_run_user(self):
        out = _run(UNITS, ["--unit", "detect", "--run-user", "ysc", "--stdout"], text=True)
        self.assertIn("User=ysc", out.stdout)
        self.assertIn("Group=ysc", out.stdout)

    def test_bad_app_id_exits_2(self):
        out = _run(UNITS, ["--app-id", "bad id!", "--stdout"], text=True)
        self.assertEqual(out.returncode, 2, out.stderr)

    def test_out_dir_writes_all_four_artifacts(self):
        """--unit all 一次渲染四类产物，全部 LF、无 @@、都带新身份。

        helper/sudoers 必须一起换身份：现场只装 helper 不换 sudoers（或反之）
        都会让控制台的提权动作打到旧路径上。
        """
        with tempfile.TemporaryDirectory() as tmp:
            out = _run(UNITS, ["--app-id", "ugv", "--out-dir", tmp], text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            expect = {
                "ugv-ai-detect.service": b"Description=ugv-ai-detect:",
                "ugv-ai-console.service": b"Description=ugv-ai-console:",
                "ugv-ai-console-helper": b'systemctl "$verb" ugv-ai-detect',
                "ugv-ai-console.sudoers": b"/usr/local/sbin/ugv-ai-console-helper ",
            }
            self.assertEqual(sorted(os.listdir(tmp)), sorted(expect))
            for name, needle in expect.items():
                path = os.path.join(tmp, name)
                with open(path, "rb") as fh:
                    body = fh.read()
                self.assertNotIn(b"@@", body, name)
                self.assertNotIn(b"\r\n", body, "%s 必须是 LF 行尾" % name)
                self.assertIn(needle, body, name)

    def test_check_detects_drift(self):
        """模板改了但成品没重渲染 → --check 必须报 5（否则现场改名会基于过时模板）。"""
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "m20-ai-detect.service")
            with open(target, "w", encoding="utf-8") as fh:
                fh.write("[Unit]\nDescription=stale\n")
            out = _run(UNITS, ["--unit", "detect", "--out-dir", tmp, "--check"], text=True)
            self.assertEqual(out.returncode, 5, out.stdout + out.stderr)
            self.assertIn("[漂移]", out.stdout)


# ---------------------------------------------------------------- 模板与 profile 卫生
class TestDeployArtifacts(unittest.TestCase):
    def test_no_crlf_in_deploy_templates_and_profiles(self):
        """install.sh 只查 deploy/*.service；新增的 tmpl/profile 同样必须 LF。"""
        import glob
        pats = [
            os.path.join(DEPLOY, "units", "*.tmpl"),
            os.path.join(DEPLOY, "profiles", "*.env"),
            os.path.join(DEPLOY, "*.service"),
            os.path.join(DEPLOY, "*.py"),
        ]
        checked = 0
        for pat in pats:
            for path in sorted(glob.glob(pat)):
                with open(path, "rb") as fh:
                    body = fh.read()
                self.assertNotIn(b"\r\n", body, "%s 含 CRLF，上机会语法错误" % path)
                checked += 1
        self.assertGreater(checked, 5, "没扫到预期数量的部署文件")

    def test_profiles_exist_for_every_known_profile(self):
        import glob
        got = {
            os.path.basename(p)[: -len(".env")]
            for p in glob.glob(os.path.join(DEPLOY, "profiles", "*.env"))
        }
        from m20_ai_detect.identity import PROFILE_TITLES
        for profile in PROFILE_TITLES:
            self.assertIn(profile, got, "缺少 deploy/profiles/%s.env" % profile)

    def test_profiles_set_their_own_id(self):
        import glob
        for path in sorted(glob.glob(os.path.join(DEPLOY, "profiles", "*.env"))):
            with open(path, encoding="utf-8") as fh:
                body = fh.read()
            name = os.path.basename(path)[: -len(".env")]
            self.assertIn("M20AI_PROFILE=%s\n" % name, body,
                          "%s 必须写 M20AI_PROFILE=%s" % (path, name))


if __name__ == "__main__":
    unittest.main()
