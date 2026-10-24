"""identity（ADR-017 命名可配置）单元测试。"""
from __future__ import annotations

import os
import tempfile
import unittest

from m20_ai_detect.identity import (
    DEFAULT_APP_ID,
    PROFILE_KEY,
    Identity,
    IdentityError,
    check_app_id,
    env_file_candidates,
    resolve_env_file,
)


def J(*parts: str) -> str:
    """拼路径。os.path.join 在 Windows 用反斜杠，断言必须与运行平台无关。"""
    return os.path.join(*parts)


class TestCheckAppId(unittest.TestCase):
    def test_default_when_empty(self):
        self.assertEqual(DEFAULT_APP_ID, "m20")

    def test_ok_ascii(self):
        self.assertEqual(check_app_id("m20"), "m20")
        self.assertEqual(check_app_id("lite3"), "lite3")
        self.assertEqual(check_app_id("ugv-01"), "ugv-01")
        self.assertEqual(check_app_id("cam_v2"), "cam_v2")
        self.assertEqual(check_app_id("  m20  "), "m20")

    def test_bad_charset(self):
        for bad in ("my app", "dev/x", "..", "-lead", "a" * 33, "@x"):
            with self.subTest(bad=bad):
                with self.assertRaises(IdentityError):
                    check_app_id(bad)


class TestIdentityNames(unittest.TestCase):
    def test_m20_default_is_backward_compatible(self):
        """最关键的回归：不配任何东西时，名字必须与改造前完全一致。"""
        ident = Identity.from_env({}, base_dir="/home/djw/m20-ai-detect")
        self.assertEqual(ident.app_id, "m20")
        self.assertEqual(ident.unit, "m20-ai-detect.service")
        self.assertEqual(ident.console_unit, "m20-ai-console.service")
        self.assertEqual(ident.unit_name, "m20-ai-detect")
        self.assertEqual(ident.console_unit_name, "m20-ai-console")
        self.assertEqual(ident.helper, "/usr/local/sbin/m20-ai-console-helper")
        self.assertEqual(
            ident.env_file, J("/home/djw/m20-ai-detect", "m20-ai-detect.env")
        )

    def test_lite3_names(self):
        ident = Identity.from_env(
            {"M20AI_APP_ID": "lite3", "M20AI_BASE_DIR": "/home/ysc/ai-detect"},
        )
        self.assertEqual(ident.unit, "lite3-ai-detect.service")
        self.assertEqual(ident.console_unit, "lite3-ai-console.service")
        self.assertEqual(ident.helper, "/usr/local/sbin/lite3-ai-console-helper")
        self.assertEqual(ident.env_file, J("/home/ysc/ai-detect", "lite3-ai-detect.env"))
        self.assertEqual(ident.units, ["lite3-ai-detect", "lite3-ai-console"])

    def test_display_priority(self):
        base = {"M20AI_APP_ID": "ugv01"}
        self.assertEqual(Identity.from_env(base).display, "ugv01")
        self.assertEqual(
            Identity.from_env(dict(base, M20AI_PLATFORM_NAME="巡检车 · 01")).display,
            "巡检车 · 01",
        )
        self.assertEqual(
            Identity.from_env(dict(base, M20AI_PROFILE="lite3-single")).display,
            "Lite3 · 单目",
        )
        # 显式 PLATFORM_NAME 压过 profile
        d = Identity.from_env(
            dict(base, M20AI_PLATFORM_NAME="X", M20AI_PROFILE="lite3-single")
        )
        self.assertEqual(d.display, "X")

    def test_profile_default(self):
        self.assertEqual(Identity.from_env({}).profile, "")
        self.assertEqual(Identity.from_env({PROFILE_KEY: "ipc-generic"}).profile,
                         "ipc-generic")

    def test_bad_app_id_raises(self):
        with self.assertRaises(IdentityError):
            Identity.from_env({"M20AI_APP_ID": "bad name"})

    def test_to_dict_serializable(self):
        d = Identity.from_env({"M20AI_APP_ID": "a1"}, base_dir="/tmp/x").to_dict()
        self.assertEqual(d["app_id"], "a1")
        self.assertEqual(d["unit"], "a1-ai-detect")
        self.assertTrue(d["env_file"].endswith("a1-ai-detect.env"))

    def test_no_base_dir_returns_basename(self):
        self.assertEqual(Identity(app_id="x").env_file, "x-ai-detect.env")


class TestEnvFileLookup(unittest.TestCase):
    def test_candidates_new_then_legacy(self):
        c = env_file_candidates("/b", "lite3")
        self.assertEqual(c[0], J("/b", "lite3-ai-detect.env"))
        self.assertEqual(c[1], J("/b", "m20-ai-detect.env"))

    def test_candidates_no_dup_when_app_is_m20(self):
        self.assertEqual(
            env_file_candidates("/b", "m20"), [J("/b", "m20-ai-detect.env")]
        )

    def test_candidates_empty_base(self):
        self.assertEqual(env_file_candidates("", "x"), [])

    def test_resolve_prefers_existing_new_name(self):
        with tempfile.TemporaryDirectory() as td:
            new = os.path.join(td, "lite3-ai-detect.env")
            old = os.path.join(td, "m20-ai-detect.env")
            open(old, "w").close()
            self.assertEqual(resolve_env_file(td, "lite3"), old)  # 只有老的
            open(new, "w").close()
            self.assertEqual(resolve_env_file(td, "lite3"), new)  # 新的优先

    def test_resolve_none(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(resolve_env_file(td, "x"))


if __name__ == "__main__":
    unittest.main()
