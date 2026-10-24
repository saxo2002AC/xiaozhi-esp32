"""Tamper tests for scripts/kitty-check.sh (Mission Kitty lockdown gate).

Each test builds a minimal fake build folder that passes the gate, injects one violation, and
expects KITTY CHECK FAIL. No ESP-IDF build is needed.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "kitty-check.sh"

GOOD_APP = (
    b"\0junk\0http://192.168.0.11:8003/xiaozhi/ota/\0Kitty-Key\0"
    b"http://192.168.4.1\0http://www.w3.org/2000/svg'\0http://\0https://\0ws://\0"
    b"www.digicert.com\0SSL.com\0"
)
GOOD_SDKCONFIG = "\n".join([
    "CONFIG_BOARD_TYPE_LAFVIN_S3_169_CAM=y",
    "CONFIG_KITTY_LOCKDOWN=y",
    "CONFIG_LANGUAGE_EN_US=y",
    "CONFIG_LCD_ST7789_240X280=y",
    'CONFIG_OTA_URL="http://192.168.0.11:8003/xiaozhi/ota/"',
    'CONFIG_KITTY_DEVICE_KEY="' + "ab" * 32 + '"',
    "",
])


class KittyCheckTamperTests(unittest.TestCase):
    def setUp(self):
        if shutil.which("bash") is None or shutil.which("strings") is None:
            self.skipTest("needs bash and strings")
        # setUp is re-run per subTest for a fresh folder; each folder is cleaned up at the end.
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name) / "build-x"
        (self.dir / "config").mkdir(parents=True)
        (self.dir / "xiaozhi.bin").write_bytes(GOOD_APP)
        (self.dir / "merged-binary.bin").write_bytes(b"\0boot\0" + GOOD_APP)
        (self.dir / "sdkconfig").write_text(GOOD_SDKCONFIG)
        (self.dir / "config" / "sdkconfig.h").write_text("#define CONFIG_KITTY_LOCKDOWN 1\n")

    def run_check(self, env=None):
        return subprocess.run(
            ["bash", str(CHECK), str(self.dir)],
            capture_output=True, text=True, env={**os.environ, **(env or {})},
        )

    def assert_ok(self):
        run = self.run_check()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("KITTY CHECK OK", run.stdout)

    def assert_fails(self, needle, env=None):
        run = self.run_check(env)
        self.assertNotEqual(run.returncode, 0, run.stdout)
        self.assertIn("KITTY CHECK FAIL", run.stderr)
        self.assertIn(needle, run.stderr)

    def inject(self, payload, name="xiaozhi.bin"):
        path = self.dir / name
        path.write_bytes(path.read_bytes() + b"\0" + payload + b"\0")

    def test_baseline_passes(self):
        self.assert_ok()

    # Cloud hosts
    def test_tenclass(self):
        self.inject(b"api.tenclass.net")
        self.assert_fails("tenclass")

    def test_xiaozhi_me(self):
        self.inject(b"xiaozhi.me")
        self.assert_fails("xiaozhi.me")

    # URL tools
    def test_tools_with_urls(self):
        for tool in (b"self.upgrade_firmware", b"self.assets.set_download_url",
                     b"self.screen.snapshot", b"self.screen.preview_image"):
            with self.subTest(tool=tool):
                self.setUp()
                self.inject(tool)
                self.assert_fails(tool.decode())

    # Off-LAN URLs
    def test_off_lan_urls(self):
        for url in (
            b"https://pcn7cs20v8cr.feishu.cn/wiki/CpQjwQsCJiQSWSkYEvrcxcbVnwh",
            b"wss://api.example.com/xiaozhi/v1/",
            b"ws://192.168.0.111:8000/",
            b"mqtt://broker.example.com:1883",
            b"mqtts://broker.example.com",
            b"HTTP://EVIL.EXAMPLE/",
            b"http://192.168.0.11.evil.example/",
            b"http://www.w3.org/2000/svg/evil",
            b"http://evil.example/?h=192.168.0.11",
        ):
            with self.subTest(url=url):
                self.setUp()
                self.inject(url)
                self.assert_fails("off-LAN URL")

    def test_userinfo_url(self):
        self.inject(b"http://192.168.0.11@evil.example/")
        self.assert_fails("userinfo")

    def test_off_lan_url_only_in_merged_image(self):
        self.inject(b"https://cdn.example.com/fw.bin", name="merged-binary.bin")
        self.assert_fails("merged-binary.bin contains an off-LAN URL")

    def test_allowed_urls_pass(self):
        for url in (b"ws://192.168.0.11:8000/xiaozhi/v1/", b"http://192.168.4.1/scan",
                    b"http://192.168.0.11/mcp/vision/explain"):
            self.inject(url)
        self.assert_ok()

    # Config and key
    def test_missing_lan_ip(self):
        (self.dir / "xiaozhi.bin").write_bytes(b"\0nothing here\0")
        self.assert_fails("does not contain 192.168.0.11")

    def test_lockdown_off(self):
        cfg = self.dir / "sdkconfig"
        cfg.write_text(cfg.read_text().replace("CONFIG_KITTY_LOCKDOWN=y\n", ""))
        self.assert_fails("CONFIG_KITTY_LOCKDOWN=y")

    def test_header_without_lockdown(self):
        (self.dir / "config" / "sdkconfig.h").write_text("/* none */\n")
        self.assert_fails("was not compiled with CONFIG_KITTY_LOCKDOWN")

    def test_ota_url_off_lan(self):
        cfg = self.dir / "sdkconfig"
        cfg.write_text(cfg.read_text().replace("http://192.168.0.11:8003", "https://api.example.com"))
        self.assert_fails("OTA_URL")

    def test_empty_key(self):
        cfg = self.dir / "sdkconfig"
        cfg.write_text(cfg.read_text().replace("ab" * 32, ""))
        self.assert_fails("CONFIG_KITTY_DEVICE_KEY is empty")

    def test_placeholder_key(self):
        cfg = self.dir / "sdkconfig"
        cfg.write_text(cfg.read_text().replace("ab" * 32, "KITTY-PLACEHOLDER-NOT-A-REAL-KEY"))
        self.assert_ok()
        self.assert_fails("placeholder", env={"KITTY_REQUIRE_REAL_KEY": "1"})

    def test_key_never_printed(self):
        run = self.run_check()
        self.assertNotIn("ab" * 32, run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
