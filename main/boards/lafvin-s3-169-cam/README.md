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
| BOOT button | GPIO0: push to talk; during start-up it opens Wi-Fi config |
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

`KITTY_SERVER_HOST` is fixed at `192.168.0.11`. `KITTY_HTTP_PORT` is `8003` until Task 26 allocates
the real port; change `CONFIG_KITTY_HTTP_PORT` and `CONFIG_OTA_URL` together in `config.json`.

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
registered URL tool, or a non-lockdown sdkconfig.

## Flashing (Task 30, not here)

1. Rebuild with the real key: `KITTY_REQUIRE_REAL_KEY=1 scripts/kitty-build.sh lafvin-s3-169-cam build-ptt`.
2. Flash `build-ptt` explicitly (for example `esptool write-flash 0x0 build-ptt/merged-binary.bin`).
3. Run `esptool verify-flash 0x0 build-ptt/merged-binary.bin`. Enter Wi-Fi only after it passes:
   the stock firmware phones `api.tenclass.net` and must never get Wi-Fi.

Recovery: hold BOOT, tap RST, release BOOT for download mode.
