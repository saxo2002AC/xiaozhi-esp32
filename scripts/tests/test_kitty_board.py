"""Static checks for the lafvin-s3-169-cam board (Mission Kitty Tasks 28 and 29).

- Push to talk: BOOT press-down starts listening, release stops it, and a click during start-up
  still opens Wi-Fi config. No mode-switch tool is exposed to the LLM.
- The optional English "Hey Kitty" build: the MultiNet language comes from Kconfig instead of a
  hard-coded "cn", build.py accepts `--wake-word custom`, and the wake variant has its own fragment.
- The kitty face: the emote GIF collection, its resolver branch and its size limits.

No ESP-IDF build is needed.
"""

import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "main" / "boards" / "lafvin-s3-169-cam"
FACES = BOARD / "kitty-gif"

# The 21 names the server can send (xiaozhi-server textUtils.EMOJI_MAP values) ...
EMOTIONS = (
    "neutral", "happy", "laughing", "funny", "sad", "angry", "crying", "loving", "embarrassed",
    "surprised", "shocked", "thinking", "winking", "cool", "relaxed", "delicious", "kissy",
    "confident", "sleepy", "silly", "confused",
)
# ... plus the faces the firmware itself sets on this board.
BOARD_FACES = ("listening",)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _function_body(source, call):
    """Return the lambda body passed to `call(` in the board source."""
    match = re.search(re.escape(call) + r"\(\[[^\]]*\]\(\)\s*\{(.*?)\n\s*\}\);", source, re.S)
    return match.group(1) if match else None


class PushToTalkTests(unittest.TestCase):
    def setUp(self):
        self.src = (BOARD / "lafvin_s3_169_cam_board.cc").read_text(encoding="utf-8")

    def test_press_down_starts_listening(self):
        body = _function_body(self.src, "boot_button_.OnPressDown")
        self.assertIsNotNone(body, "BOOT has no OnPressDown handler")
        self.assertIn("StartListening()", body)

    def test_press_up_stops_listening(self):
        body = _function_body(self.src, "boot_button_.OnPressUp")
        self.assertIsNotNone(body, "BOOT has no OnPressUp handler")
        self.assertIn("StopListening()", body)

    def test_click_during_startup_opens_wifi_config(self):
        body = _function_body(self.src, "boot_button_.OnClick")
        self.assertIsNotNone(body, "BOOT has no OnClick handler")
        self.assertIn("kDeviceStateStarting", body)
        self.assertIn("EnterWifiConfigMode()", body)

    def test_no_toggle_and_no_mode_switch_tool(self):
        # D10: hold-to-talk is the compiled default; the LLM gets no tool to change it.
        self.assertNotIn("ToggleChatState", self.src)
        for path in BOARD.rglob("*"):
            if path.suffix in {".cc", ".h", ".c", ".cpp"}:
                text = path.read_text(encoding="utf-8")
                self.assertNotIn("PressToTalkMcpTool", text, path)
                self.assertNotIn("press_to_talk", text, path)


class WakeWordOptionTests(unittest.TestCase):
    def test_language_comes_from_kconfig(self):
        src = (ROOT / "main/audio/wake_words/custom_wake_word.cc").read_text(encoding="utf-8")
        # F19: the Kconfig path used to hard-code "cn". "cn" may only remain as the fallback for
        # builds without USE_CUSTOM_WAKE_WORD (the file compiles on every S3 target).
        self.assertRegex(
            src,
            r'#ifdef CONFIG_CUSTOM_WAKE_WORD_LANGUAGE\n\s+language_ = '
            r'CONFIG_CUSTOM_WAKE_WORD_LANGUAGE;\n#else\n\s+language_ = "cn";\n#endif',
        )
        self.assertEqual(src.count('language_ = "cn";'), 1)

    def test_kconfig_language_symbol_defaults_to_cn(self):
        kconfig = (ROOT / "main/Kconfig.projbuild").read_text(encoding="utf-8")
        match = re.search(
            r'^config CUSTOM_WAKE_WORD_LANGUAGE\n(.*?)(?=^\S)', kconfig, re.M | re.S
        )
        self.assertIsNotNone(match, "Kconfig lacks CUSTOM_WAKE_WORD_LANGUAGE")
        body = match.group(1)
        self.assertRegex(body, r'^\s+string\b', "must be a string symbol")
        self.assertIn('default "cn"', body)
        self.assertIn("depends on USE_CUSTOM_WAKE_WORD", body)

    def test_two_builds_push_to_talk_and_wake(self):
        config = json.loads((BOARD / "config.json").read_text(encoding="utf-8"))
        builds = {b["name"]: b["sdkconfig_append"] for b in config["builds"]}
        self.assertEqual(sorted(builds), ["lafvin-s3-169-cam", "lafvin-s3-169-cam-wake"])
        self.assertIn("CONFIG_WAKE_WORD_DISABLED=y", builds["lafvin-s3-169-cam"])
        self.assertNotIn("CONFIG_WAKE_WORD_DISABLED=y", builds["lafvin-s3-169-cam-wake"])
        # Everything else (display, port, OTA URL) is identical.
        ptt = [o for o in builds["lafvin-s3-169-cam"] if o != "CONFIG_WAKE_WORD_DISABLED=y"]
        self.assertEqual(ptt, builds["lafvin-s3-169-cam-wake"])

    def test_wake_fragment(self):
        lines = (BOARD / "sdkconfig.wake").read_text(encoding="utf-8").splitlines()
        options = {line for line in lines if line.startswith("CONFIG_")}
        for want in (
            "CONFIG_USE_CUSTOM_WAKE_WORD=y",
            'CONFIG_CUSTOM_WAKE_WORD="hey kitty"',
            'CONFIG_CUSTOM_WAKE_WORD_DISPLAY="Hey Kitty"',
            'CONFIG_CUSTOM_WAKE_WORD_LANGUAGE="en"',
            "CONFIG_CUSTOM_WAKE_WORD_THRESHOLD=20",
            "CONFIG_SR_MN_EN_MULTINET7_QUANT=y",
        ):
            self.assertIn(want, options)

    def test_mn7_en_symbol_exists_in_esp_sr(self):
        kconfig = ROOT / "managed_components/espressif__esp-sr/Kconfig.projbuild"
        if not kconfig.exists():
            self.skipTest("esp-sr is not downloaded")
        self.assertRegex(kconfig.read_text(encoding="utf-8"),
                         r"(?m)^\s+config SR_MN_EN_MULTINET7_QUANT$")

    def test_build_py_accepts_custom_wake_word(self):
        build = _load("build", ROOT / "scripts/build.py")
        name, options, symbols = build._wake_word_sdkconfig_options("custom", "esp32s3")
        self.assertEqual(name, "custom")
        self.assertEqual(options[-1], "CONFIG_USE_CUSTOM_WAKE_WORD=y")
        self.assertIn("CONFIG_WAKE_WORD_DISABLED=n", options)
        self.assertEqual(symbols, ["CONFIG_USE_CUSTOM_WAKE_WORD"])
        with self.assertRaises(ValueError):
            build._wake_word_sdkconfig_options("custom", "esp32c3")

    def test_kitty_build_selects_fragment_for_wake_variant(self):
        script = (ROOT / "scripts/kitty-build.sh").read_text(encoding="utf-8")
        self.assertIn("lafvin-s3-169-cam-wake", script)
        self.assertIn("--wake-word custom", script)
        self.assertIn("KITTY_SDKCONFIG_EXTRA", script)
        self.assertIn("KITTY_SDKCONFIG_EXTRA", (ROOT / "scripts/build.py").read_text())


class KittyFaceTests(unittest.TestCase):
    def test_every_face_is_a_small_looping_animation(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("needs Pillow")
        for name in EMOTIONS + BOARD_FACES:
            with self.subTest(face=name):
                path = FACES / f"{name}.gif"
                self.assertTrue(path.is_file(), f"{path} is missing")
                with Image.open(path) as im:
                    self.assertEqual(im.format, "GIF")
                    self.assertLessEqual(im.size[0], 120)
                    self.assertLessEqual(im.size[1], 120)
                    self.assertGreater(getattr(im, "n_frames", 1), 1, "not animated")
                    self.assertEqual(im.info.get("loop"), 0, "must loop forever")

    def test_collection_holds_only_faces(self):
        # build_default_assets packs every .png/.gif in the folder as an emoji, so a stray
        # image (a contact sheet, say) would become a bogus emotion.
        allowed = {f"{n}.gif" for n in EMOTIONS + BOARD_FACES} | {"SOURCES.md"}
        present = {p.name for p in FACES.iterdir() if not p.name.startswith(".")}
        self.assertEqual(present - allowed, set())

    def test_collection_size_budget(self):
        total = sum(p.stat().st_size for p in FACES.glob("*.gif"))
        self.assertLess(total, 2 * 1024 * 1024, f"kitty-gif is {total} bytes")

    def test_sources_record_reference_and_generator(self):
        text = (FACES / "SOURCES.md").read_text(encoding="utf-8")
        self.assertIn("github.com/lafvintech/LAFVIN-ESP32S3-1.69-LCD", text)
        self.assertIn("eyes_show", text)
        self.assertIn("kitty-face/generate.py", text)
        self.assertTrue((BOARD / "kitty-face" / "generate.py").is_file())

    def test_board_display_sets_board_faces(self):
        # Listening shows the "listening" face; once the words are recognized (the "user" chat
        # line from stt) the face is "thinking" until the reply's emotion arrives. The board owns
        # this through its display subclass; core code stays board-agnostic (AGENTS.md).
        src = (BOARD / "lafvin_s3_169_cam_board.cc").read_text(encoding="utf-8")
        self.assertRegex(src, r"class KittyLcdDisplay : public SpiLcdDisplay")
        self.assertRegex(src, r"new KittyLcdDisplay\(")
        self.assertRegex(src, r'emotion = "listening";')
        self.assertRegex(src, r'SetEmotion\("thinking"\);')
        self.assertIn("Lang::Strings::LISTENING", src)
        app = (ROOT / "main/application.cc").read_text(encoding="utf-8")
        self.assertNotIn("CONFIG_BOARD_TYPE_LAFVIN_S3_169_CAM", app)

    def test_resolver_finds_kitty_gif(self):
        assets = _load("build_default_assets", ROOT / "scripts/build_default_assets.py")
        path = assets.get_emoji_collection_path("kitty-gif", "/nonexistent", str(ROOT))
        self.assertEqual(Path(path), FACES)


if __name__ == "__main__":
    unittest.main()
