# LAFVIN ESP32-S3 1.69" LCD + Camera (Mission Kitty)

Board folder for the LAFVIN ESP32-S3-N16R8 kit with a 1.69" ST7789 240x280 IPS panel, a detachable
OV3660 camera, an ICS-43434 I2S mic and a MAX98357 I2S amp. It is derived from
`bread-compact-wifi-s3cam` (same SPI LCD, simplex I2S and DVP camera code) with the LAFVIN pins.

## Pins

| Part | Pins |
|---|---|
| LCD ST7789 240x280 (SPI3) | MOSI 39, SCK 38, CS 14, DC 10, RST 3, BL 13; IPS invert, offset Y 20 |
| Camera OV3660 | XCLK 17 (20 MHz), SIOD 1, SIOC 2, VSYNC 21, HREF 18, PCLK 16, D0-D7 = 7, 5, 4, 6, 8, 9, 11, 15, PWDN/RESET not connected |
| Mic ICS-43434 (I2S RX) | WS 40, SCK 41, SD 42 |
| Amp MAX98357 (I2S TX) | DIN 45, BCLK 46, LRCLK 47 |
| BOOT button | GPIO0: hold to talk (press = listen, release = send); a click during start-up opens Wi-Fi config |
| WS2812 LED | GPIO48 |

Camera frames are RGB565 VGA in PSRAM, as in the reference board.

## Lockdown (`CONFIG_KITTY_LOCKDOWN`)

`KITTY_LOCKDOWN` follows the board type and has no prompt, so it cannot be switched off from
menuconfig or a fragment. With it:

- `Ota::GetCheckVersionUrl` returns the build-time `CONFIG_OTA_URL` and ignores any `ota_url` in NVS.
- The OTA request carries `Kitty-Key: <CONFIG_KITTY_DEVICE_KEY>`; the server answers 403 without it.
- `Ota::CheckVersion` ignores a `firmware` section; `has_new_version_` is never set.
- `Ota::Upgrade` and `Application::UpgradeFirmware` return false at once.
- `self.upgrade_firmware`, `self.assets.set_download_url`, `self.screen.snapshot` and
  `self.screen.preview_image` are not registered (each takes an arbitrary URL).
- Every server-supplied destination passes `main/kitty_lockdown.h`: only `http://` or `ws://` URLs
  (or a `host[:port]` endpoint) whose host is exactly `KITTY_SERVER_HOST`. This covers the
  websocket url and MQTT endpoint (checked before they are stored from the OTA reply, and again
  before connecting, since NVS may hold factory values), the MQTT UDP server, the vision explain url
  and notify audio urls. A rejected value is logged and the previous one kept.
- `Application::CheckAssetsVersion` never downloads assets; a stale `download_url` is erased.
- CMake fails if `CONFIG_KITTY_DEVICE_KEY` is empty or `CONFIG_OTA_URL` is not
  `http://<KITTY_SERVER_HOST>:<KITTY_HTTP_PORT>/xiaozhi/ota/`.

`KITTY_SERVER_HOST` is fixed at `192.168.0.11`. `KITTY_HTTP_PORT` is `3030` (the deployed server's
HTTP port; its websocket is on 3029 and arrives in the OTA reply). Change `CONFIG_KITTY_HTTP_PORT`
and `CONFIG_OTA_URL` together in `config.json`.

## Device key

The key is never committed. `scripts/kitty-key.sh` reads `KITTY_DEVICE_KEY` over ssh from the
server's env file and writes the git-ignored `sdkconfig.kitty.local` (mode 600), which
`scripts/build.py` applies last. Where the key lives is configured locally, never in the repo:
`KITTY_KEY_SOURCE=<ssh-host>:<path-to-env-file>`, from the environment or from the git-ignored
`kitty-key.local` in the repo root. With no source, or no key at the source, it writes a non-hex
placeholder that the server can never accept. `KITTY_REQUIRE_REAL_KEY=1` makes both scripts refuse
the placeholder.

## Build

One folder per variant (never flash from `build/`, which `scripts/build.py` reuses):

```sh
. ~/esp/esp-idf-v6/export.sh && scripts/kitty-build.sh lafvin-s3-169-cam build-ptt
```

`kitty-build.sh` fetches the key, builds with the wake word disabled (push to talk), copies the
artifacts and `sdkconfig` into `build-ptt/` and runs `scripts/kitty-check.sh build-ptt`, which must
print `KITTY CHECK OK`. The check fails on `tenclass` or `xiaozhi.me` in the image, a missing
`192.168.0.11`, any http/https/ws/wss/mqtt URL to another host (exceptions: the local AP page
`192.168.4.1`, bare scheme prefixes, and the SVG XML namespace in the Wi-Fi config page), a
registered URL tool, or a non-lockdown sdkconfig. It also fails when a kitty face is missing
from the source folder or from `generated_assets.bin`, when `build-ptt` enables a wake word, or
when a wake build lacks the English MultiNet7 config or the `mn7_en` model in its assets.

## Talking: hold BOOT, or the optional "Hey Kitty" build

Hold to talk on BOOT is the compiled default. No MCP tool lets the LLM switch modes. Two variants
come from `config.json`, each built into its own folder:

| Variant | Folder | Wake word |
|---|---|---|
| `lafvin-s3-169-cam` | `build-ptt` | none (`CONFIG_WAKE_WORD_DISABLED=y`). This is the one we flash |
| `lafvin-s3-169-cam-wake` | `build-wake` | "Hey Kitty" as well as BOOT. Off until it passes the living-room false-trigger test |

```sh
. ~/esp/esp-idf-v6/export.sh && scripts/kitty-build.sh lafvin-s3-169-cam-wake build-wake
```

The wake variant builds with `--wake-word custom` and the committed fragment `sdkconfig.wake`:

- `CONFIG_USE_CUSTOM_WAKE_WORD=y`
- `CONFIG_CUSTOM_WAKE_WORD="hey kitty"` and display text "Hey Kitty"
- `CONFIG_CUSTOM_WAKE_WORD_LANGUAGE="en"`
- threshold 20
- the English MultiNet7 model `CONFIG_SR_MN_EN_MULTINET7_QUANT=y`

That MultiNet symbol comes from esp-sr 2.4.7, `Kconfig.projbuild`, choice
`ENGLISH_SR_MN_MODEL_SEL`, "general english recognition (mn7_en)". The model is packed into the
assets image (`mn7_en` plus `fst`, about 2.6 MB).

`CustomWakeWord` used to hard-code `"cn"` on its Kconfig path. It now reads
`CONFIG_CUSTOM_WAKE_WORD_LANGUAGE`. Upstream does not allow wake-word or language options in a
board `config.json` (`scripts/tests/test_build.py`), which is why they live in the fragment.

## Face (`kitty-gif`)

The emotion GIFs are original art made by `kitty-face/generate.py`. See `kitty-gif/SOURCES.md`
and `kitty-face/contact-sheet.png`.

`KittyLcdDisplay`, a board-local subclass of `SpiLcdDisplay`, adds two moods that the core does not
set:

- `listening`: replaces "neutral" while the status is Listening;
- `thinking`: shown once the child's words are recognized, until the reply's emotion arrives. If
  none arrives, the first spoken line switches it to `happy` (the talking face).

The faces are 200x200 and play at 1:1.

## Hold to talk: releasing before the channel opens

A quick tap can release BOOT before the audio channel finishes opening. In one pass, the main loop
handles START, then STOP, then the scheduled open, so STOP sees `Connecting`.
`Application::stop_after_connect_` records that release, and `ContinueOpenAudioChannel` goes back to
Idle instead of listening. Without this, the mic would stay on until the next press.

`scripts/tests/test_kitty_ptt_race.py` runs the real handlers on the host. Manual check for Task 30:

1. Tap BOOT once while idle and disconnected.
2. The status must return to Standby, never Listening.
3. No `listen start` may reach the server log.

## Flashing (Task 30, not here)

1. Rebuild with the real key: `KITTY_REQUIRE_REAL_KEY=1 scripts/kitty-build.sh lafvin-s3-169-cam build-ptt`.
2. Flash `build-ptt` explicitly (for example `esptool write-flash 0x0 build-ptt/merged-binary.bin`).
3. Run `esptool verify-flash 0x0 build-ptt/merged-binary.bin`. Enter Wi-Fi only after it passes:
   the stock firmware phones `api.tenclass.net` and must never get Wi-Fi.

Recovery: hold BOOT, tap RST, release BOOT for download mode.
