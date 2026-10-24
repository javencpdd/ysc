"""deploy/env_upsert.py 的键级 upsert 契约测试（migrate-rename.sh 的迁移语义）。

关键不变量：
  A. **只动身份派生键**：用户调过的键（token/port/AI_BASE/SOURCES）任何情况下
     都不在本工具的入参里——测试守住"传什么改什么"的边界；
  B. **同键多行只留第一处**（systemd 对重复键取行序在前的，留歧义会改名后仍读旧值）；
  C. **注释里的键不算生效**（追加而不是替换注释）；
  D. **幂等 + LF 行尾 + 行尾换行**（Windows 上写的 env 再 migrate 不许引入 CRLF）。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPSERT = os.path.join(ROOT, "deploy", "env_upsert.py")


def upsert(body: str, *pairs, header: str = "") -> str:
    """把 body 落成临时 env 文件，跑 env_upsert.py，返回结果文本。"""
    with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False,
                                     encoding="utf-8", newline="\n") as fh:
        fh.write(body)
        path = fh.name
    try:
        argv = [sys.executable, UPSERT]
        if header:
            argv += ["--header", header]
        argv += [path] + list(pairs)
        proc = subprocess.run(argv, capture_output=True, timeout=30)
        if proc.returncode != 0:
            raise AssertionError("rc=%s stderr=%s" % (proc.returncode, proc.stderr))
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8")
    finally:
        os.unlink(path)


def keys_of(text: str) -> dict:
    """取生效行的键值对（断言用户键未被碰过时用）。"""
    out = {}
    for ln in text.splitlines():
        s = ln.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            out[k.strip()] = v
    return out


class TestEnvUpsert(unittest.TestCase):
    def test_missing_key_appended_with_header(self):
        got = upsert("M20AI_PORT=1\n", "M20AI_APP_ID=lite3",
                     header="身份迁移（migrate-rename.sh）")
        self.assertIn("M20AI_PORT=1", got)
        self.assertIn("# ---- 身份迁移（migrate-rename.sh） ----", got)
        self.assertEqual(got.count("M20AI_APP_ID=lite3"), 1)
        self.assertEqual(keys_of(got), {"M20AI_PORT": "1", "M20AI_APP_ID": "lite3"})

    def test_existing_key_replaced_in_place(self):
        got = upsert("M20AI_APP_ID=m20\nM20AI_BASE_DIR=/x\n",
                     "M20AI_APP_ID=lite3")
        self.assertIn("M20AI_APP_ID=lite3\n", got)
        self.assertNotIn("M20AI_APP_ID=m20", got)
        # 原地替换，不挪到文件末尾
        self.assertTrue(got.startswith("M20AI_APP_ID=lite3\n"), got)

    def test_duplicate_keys_keep_only_first(self):
        """systemd 对重复键取行序在前的：两行同键必须收敛成一行（新值）。"""
        got = upsert("M20AIC_HELPER=/old/a\nM20AIC_PORT=1\nM20AIC_HELPER=/old/b\n",
                     "M20AIC_HELPER=/new/helper")
        self.assertEqual(got.count("M20AIC_HELPER="), 1)
        self.assertIn("M20AIC_HELPER=/new/helper\n", got)
        self.assertIn("M20AIC_PORT=1", got)

    def test_key_in_comment_is_not_touched(self):
        got = upsert("# M20AI_APP_ID=m20（注释里的老名，只是文档）\nA=1\n",
                     "M20AI_APP_ID=lite3")
        self.assertIn("# M20AI_APP_ID=m20", got, "注释行必须原样保留")
        lines = [ln for ln in got.splitlines()
                 if ln.strip() and not ln.lstrip().startswith("#")]
        self.assertEqual(len([ln for ln in lines if ln.startswith("M20AI_APP_ID=")]), 1)
        self.assertIn("M20AI_APP_ID=lite3", lines)

    def test_idempotent(self):
        body = "M20AIC_PORT=5050\n# 说明\nM20AIC_HELPER=/usr/local/sbin/m20-ai-console-helper\n"
        args = ("M20AIC_HELPER=/usr/local/sbin/lite3-ai-console-helper",
                "M20AIC_ENV_FILE=/base/lite3-ai-detect.env")
        first = upsert(body, *args, header="h")
        second = upsert(first, *args, header="h")
        self.assertEqual(first, second, "连续迁移两次必须逐字相同")

    def test_user_keys_are_never_the_tools_business(self):
        """契约文档化：本工具只改传入的键。这里示范一次真实迁移的键集合。"""
        body = ("M20AIC_PORT=5050\nM20AIC_TOKEN=secret\n"
                "M20AIC_BIND=0.0.0.0\nM20AIC_ENV_FILE=/b/m20-ai-detect.env\n"
                "M20AIC_HELPER=/usr/local/sbin/m20-ai-console-helper\n")
        got = upsert(body,
                     "M20AIC_APP_ID=lite3",
                     "M20AIC_ENV_FILE=/b/lite3-ai-detect.env",
                     "M20AIC_HELPER=/usr/local/sbin/lite3-ai-console-helper")
        self.assertEqual(keys_of(got), {
            "M20AIC_PORT": "5050", "M20AIC_TOKEN": "secret",
            "M20AIC_BIND": "0.0.0.0",
            "M20AIC_APP_ID": "lite3",
            "M20AIC_ENV_FILE": "/b/lite3-ai-detect.env",
            "M20AIC_HELPER": "/usr/local/sbin/lite3-ai-console-helper",
        })

    def test_always_lf_and_trailing_newline(self):
        got = upsert("A=1", "B=2")            # 原文件连换行都没有
        self.assertNotIn("\r", got)
        self.assertTrue(got.endswith("\n"))
        self.assertIn("B=2\n", got)

    def test_non_kv_argument_rejected(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False,
                                         encoding="utf-8") as fh:
            fh.write("A=1\n")
            path = fh.name
        try:
            proc = subprocess.run(
                [sys.executable, UPSERT, path, "NOT-A-PAIR"],
                capture_output=True, timeout=30)
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertIn("KEY=VALUE", proc.stderr.decode("utf-8", "replace"))
        finally:
            os.unlink(path)

    def test_missing_file_exits_3(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [sys.executable, UPSERT, os.path.join(tmp, "nope.env"), "A=1"],
                capture_output=True, timeout=30)
            self.assertEqual(proc.returncode, 3, proc.stderr)


if __name__ == "__main__":
    unittest.main()
