"""Hold-to-talk race: releasing BOOT before the audio channel opens must not leave the mic on.

Runs the real Application::HandleStartListeningEvent, HandleStopListeningEvent and
ContinueOpenAudioChannel bodies (extracted from main/application.cc) against host fakes, and
replays the main loop order: within one loop pass START is handled, then STOP, then the scheduled
tasks (application.cc main loop). A quick tap lands START and STOP in the same pass while the
channel open is still scheduled, so STOP sees kDeviceStateConnecting.
"""

import os
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def definition(source, signature):
    start = source.index(signature)
    brace = source.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


DRIVER = r'''
#include <cstdio>
#include <functional>
#include <memory>
#include <string>
#include <vector>
#include "DEVICE_STATE_H"

enum ListeningMode { kListeningModeAutoStop, kListeningModeManualStop, kListeningModeRealtime };
enum AbortReason { kAbortReasonNone };
enum class PowerSaveLevel { PERFORMANCE };
#define TAG "test"
#define ESP_LOGE(tag, ...) std::fprintf(stderr, __VA_ARGS__)
#define ESP_LOGI(tag, ...) do {} while (0)

struct Board {
    static Board& GetInstance() { static Board b; return b; }
    void SetPowerSaveLevel(PowerSaveLevel) {}
};
struct FakeProtocol {
    bool opened = false, open_ok = true;
    int stop_sent = 0;
    bool IsAudioChannelOpened() const { return opened; }
    bool OpenAudioChannel() { opened = open_ok; return open_ok; }
    void SendStopListening() { stop_sent++; }
    void CloseAudioChannel() { opened = false; }
};
struct FakeAudio {
    void EnableAudioTesting(bool) {}
    void EncodeWakeWord() {}
    void EnableWakeWordDetection(bool) {}
};

class Application {
public:
    DeviceState state_ = kDeviceStateIdle;
    ListeningMode listening_mode_ = kListeningModeAutoStop;
    std::unique_ptr<FakeProtocol> protocol_ = std::make_unique<FakeProtocol>();
    FakeAudio audio_service_;
    std::vector<std::function<void()>> tasks_;
    int listening_entered = 0;
    bool stop_after_connect_ = false;
    bool play_popup_on_listening_ = false;

    DeviceState GetDeviceState() const { return state_; }
    bool SetDeviceState(DeviceState s) { state_ = s; if (s == kDeviceStateListening) listening_entered++; return true; }
    void StopNotification() {}
    void AbortSpeaking(AbortReason) {}
    void Schedule(std::function<void()>&& f) { tasks_.push_back(std::move(f)); }
    void SetListeningMode(ListeningMode mode) { listening_mode_ = mode; SetDeviceState(kDeviceStateListening); }
    ListeningMode GetDefaultListeningMode() const { return kListeningModeAutoStop; }
    void RunTasks() { auto t = std::move(tasks_); tasks_.clear(); for (auto& f : t) f(); }
    // The session ends and the server closes the channel: back to idle, channel closed.
    void EndSession() { state_ = kDeviceStateIdle; protocol_->opened = false; }

    void HandleToggleChatEvent();
    void HandleStartListeningEvent();
    void HandleStopListeningEvent();
    void ContinueOpenAudioChannel(ListeningMode mode);
    void BeginWakeWordInvoke(const std::string& wake_word);
    void ContinueWakeWordInvoke(const std::string& wake_word);
};

METHODS

static int failures = 0;
#define CHECK(cond, msg) do { if (!(cond)) { std::printf("FAIL: %s\n", msg); failures++; } } while (0)

int main() {
    {   // Quick tap: START and STOP in one pass, then the scheduled open.
        Application app;
        app.HandleStartListeningEvent();
        app.HandleStopListeningEvent();
        app.RunTasks();
        CHECK(app.state_ == kDeviceStateIdle, "tap: ends idle");
        CHECK(app.listening_entered == 0, "tap: never listens");
        CHECK(!app.stop_after_connect_, "tap: flag consumed");
    }
    {   // Hold: the open runs while BOOT is down; release arrives afterwards.
        Application app;
        app.HandleStartListeningEvent();
        app.RunTasks();
        CHECK(app.state_ == kDeviceStateListening, "hold: listening while held");
        app.HandleStopListeningEvent();
        CHECK(app.state_ == kDeviceStateIdle, "hold: idle after release");
        CHECK(app.protocol_->stop_sent == 1, "hold: stop sent");
    }
    {   // Tap, then press again before the open runs: the second press wins.
        Application app;
        app.HandleStartListeningEvent();
        app.HandleStopListeningEvent();
        app.HandleStartListeningEvent();
        app.RunTasks();
        CHECK(app.state_ == kDeviceStateListening, "re-press: listening");
    }
    {   // A stale flag from a failed open must not cancel the next hold.
        Application app;
        app.protocol_->open_ok = false;
        app.HandleStartListeningEvent();
        app.HandleStopListeningEvent();
        app.RunTasks();
        CHECK(app.state_ == kDeviceStateIdle, "failed open: idle");
        app.protocol_->open_ok = true;
        app.HandleStartListeningEvent();
        app.RunTasks();
        CHECK(app.state_ == kDeviceStateListening, "after failed open: next hold listens");
    }
    {   // BOOT released while a wake-word connect is opening: the wake path must consume the
        // flag, or it lingers and ends the next toggle-started session idle.
        Application app;
        app.BeginWakeWordInvoke("hey kitty");
        app.HandleStopListeningEvent();
        app.RunTasks();
        CHECK(app.state_ == kDeviceStateListening, "wake connect: listening");
        CHECK(!app.stop_after_connect_, "wake connect: flag cleared");
        app.EndSession();
        app.HandleToggleChatEvent();
        app.RunTasks();
        CHECK(app.state_ == kDeviceStateListening, "toggle after wake: listening");
    }
    {   // The toggle path never inherits a stale flag, whatever left it set.
        Application app;
        app.stop_after_connect_ = true;
        app.HandleToggleChatEvent();
        app.RunTasks();
        CHECK(app.state_ == kDeviceStateListening, "toggle with stale flag: listening");
        CHECK(!app.stop_after_connect_, "toggle with stale flag: flag cleared");
    }
    {   // Same for a wake-word connect over an already open channel (no scheduling).
        Application app;
        app.protocol_->opened = true;
        app.stop_after_connect_ = true;
        app.BeginWakeWordInvoke("hey kitty");
        CHECK(app.state_ == kDeviceStateListening, "wake on open channel: listening");
        CHECK(!app.stop_after_connect_, "wake on open channel: flag cleared");
    }
    return failures ? 1 : 0;
}
'''


class PushToTalkRaceTests(unittest.TestCase):
    def test_release_before_channel_opens(self):
        compiler = shlex.split(os.environ.get("CXX", "c++"))
        if not compiler or shutil.which(compiler[0]) is None:
            self.skipTest("requires a host C++ compiler")
        src = (ROOT / "main/application.cc").read_text(encoding="utf-8")
        methods = "\n\n".join(
            definition(src, sig) for sig in (
                "void Application::HandleToggleChatEvent()",
                "void Application::HandleStartListeningEvent()",
                "void Application::HandleStopListeningEvent()",
                "void Application::ContinueOpenAudioChannel(ListeningMode mode)",
                "void Application::BeginWakeWordInvoke(const std::string& wake_word)",
                "void Application::ContinueWakeWordInvoke(const std::string& wake_word)",
            )
        )
        driver = DRIVER.replace("METHODS", methods).replace(
            "DEVICE_STATE_H", str(ROOT / "main/device_state.h"))
        with tempfile.TemporaryDirectory() as d:
            cc = Path(d) / "race.cc"
            cc.write_text(driver, encoding="utf-8")
            exe = Path(d) / "race"
            built = subprocess.run(compiler + ["-std=c++17", str(cc), "-o", str(exe)],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("bool stop_after_connect_", (ROOT / "main/application.h").read_text())


if __name__ == "__main__":
    unittest.main()
