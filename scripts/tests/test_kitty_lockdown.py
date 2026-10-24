"""Host test for main/kitty_lockdown.h: the Mission Kitty URL/host allowlist.

Compiles the header with the host C++ compiler against a stub sdkconfig.h and checks each case.
Skipped when no host compiler is available.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOST = "192.168.0.11"

URL_ALLOWED = [
    "http://192.168.0.11:8003/xiaozhi/ota/",
    "ws://192.168.0.11:8000/xiaozhi/v1/",
    "http://192.168.0.11/mcp/vision/explain",
    "http://192.168.0.11",
    "http://192.168.0.11:8003?x=1",
]
URL_REJECTED = [
    "",
    "192.168.0.11",
    "https://192.168.0.11/",
    "wss://192.168.0.11/",
    "mqtt://192.168.0.11/",
    "HTTP://192.168.0.11/",
    "http://192.168.0.111/",
    "http://192.168.0.1/",
    "http://192.168.0.11.evil.example/",
    "http://evil.example/?h=192.168.0.11",
    "http://evil.example/192.168.0.11",
    "http://192.168.0.11@evil.example/",
    "http://user@192.168.0.11/",
    "http://192.168.0.11:/",
    "http://192.168.0.11:80a/",
    "http://192.168.0.11:123456/",
    "ws://api.tenclass.net/xiaozhi/v1/",
]
ENDPOINT_ALLOWED = ["192.168.0.11", "192.168.0.11:1883", "192.168.0.11:8884"]
ENDPOINT_REJECTED = [
    "",
    "192.168.0.11:",
    "192.168.0.110",
    "evil.example:1883",
    "192.168.0.11/x",
    "a@192.168.0.11",
    "192.168.0.11:x",
    "mqtt.xiaozhi.me:8883",
]


def _cxx():
    for name in ("c++", "clang++", "g++"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _lit(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


class KittyLockdownHeaderTests(unittest.TestCase):
    def test_allowlist(self):
        cxx = _cxx()
        if cxx is None:
            self.skipTest("no host C++ compiler")
        lines = ['#include "kitty_lockdown.h"', "#include <cstdio>", "int main() {", "  int bad = 0;"]
        for fn, cases, want in (
            ("KittyUrlAllowed", URL_ALLOWED, "true"),
            ("KittyUrlAllowed", URL_REJECTED, "false"),
            ("KittyEndpointAllowed", ENDPOINT_ALLOWED, "true"),
            ("KittyEndpointAllowed", ENDPOINT_REJECTED, "false"),
        ):
            for case in cases:
                lines.append(
                    f"  if (kitty::{fn}({_lit(case)}) != {want}) "
                    f"{{ std::printf(\"WRONG {fn} %s\\n\", {_lit(case)}); bad = 1; }}"
                )
        lines += ["  return bad;", "}"]
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "sdkconfig.h").write_text(
                f'#define CONFIG_KITTY_LOCKDOWN 1\n#define CONFIG_KITTY_SERVER_HOST "{HOST}"\n'
            )
            src = tmp / "t.cc"
            src.write_text("\n".join(lines) + "\n")
            exe = tmp / "t"
            subprocess.run(
                [cxx, "-std=c++17", "-Wall", "-Werror", f"-I{tmp}", f"-I{ROOT / 'main'}",
                 str(src), "-o", str(exe)],
                check=True,
            )
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout)

    def test_header_is_empty_without_lockdown(self):
        cxx = _cxx()
        if cxx is None:
            self.skipTest("no host C++ compiler")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "sdkconfig.h").write_text("/* no lockdown */\n")
            src = tmp / "t.cc"
            src.write_text(
                '#include "kitty_lockdown.h"\n'
                "namespace kitty { int marker; }\n"
                "#ifdef CONFIG_KITTY_LOCKDOWN\n#error lockdown leaked\n#endif\n"
                "int main() { return kitty::marker; }\n"
            )
            subprocess.run(
                [cxx, "-std=c++17", "-Wall", "-Werror", f"-I{tmp}", f"-I{ROOT / 'main'}",
                 str(src), "-o", str(tmp / "t")],
                check=True,
            )


if __name__ == "__main__":
    unittest.main()
