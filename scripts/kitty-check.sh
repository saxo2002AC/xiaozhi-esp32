#!/usr/bin/env bash
# kitty-check.sh <build_dir>
#
# Mission Kitty lockdown gate. Run it on every build folder before anything is flashed.
# It fails when:
#   - the app image (and the merged image, if present) contains "tenclass" or "xiaozhi.me";
#   - the app image does not contain the Mini's LAN address 192.168.0.11;
#   - the app image still registers the remote firmware or asset download MCP tools;
#   - the build's sdkconfig is not the locked-down, en-US, ST7789 240x280 lafvin-s3-169-cam config;
#   - the device key is empty.
# It never prints the device key. With KITTY_REQUIRE_REAL_KEY=1 (Task 30, before flashing) it also
# fails on a placeholder key; without it, a placeholder key is reported as a NOTE.
#
# sdkconfig lookup: <build_dir>/sdkconfig (one folder per variant, R9), else <build_dir>/../sdkconfig.
set -euo pipefail

dir=${1:?usage: kitty-check.sh <build_dir>}
fail() {
    echo "KITTY CHECK FAIL: $*" >&2
    exit 1
}

bin="$dir/xiaozhi.bin"
[ -f "$bin" ] || fail "$bin not found"

if [ -f "$dir/sdkconfig" ]; then
    cfg="$dir/sdkconfig"
elif [ -f "$dir/../sdkconfig" ]; then
    cfg="$dir/../sdkconfig"
else
    fail "no sdkconfig in $dir or $dir/.."
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# Strings go to a file first: under pipefail, `strings | grep -q` can SIGPIPE strings on an early
# match and turn a hit into a miss.
images=("$bin")
[ -f "$dir/merged-binary.bin" ] && images+=("$dir/merged-binary.bin")
for img in "${images[@]}"; do
    strings -a "$img" >"$work/strings.txt"
    for bad in tenclass xiaozhi.me; do
        if grep -qiF "$bad" "$work/strings.txt"; then
            fail "$img contains '$bad'"
        fi
        # Raw byte scan as well, in case strings splits or skips a run.
        if LC_ALL=C grep -qaiF "$bad" "$img"; then
            fail "$img contains '$bad' (raw bytes)"
        fi
    done
done

strings -a "$bin" >"$work/app.txt"
grep -qF "192.168.0.11" "$work/app.txt" || fail "$bin does not contain 192.168.0.11"
for tool in self.upgrade_firmware self.assets.set_download_url; do
    if grep -qF "$tool" "$work/app.txt"; then
        fail "$bin still registers $tool"
    fi
done

for want in \
    CONFIG_KITTY_LOCKDOWN=y \
    CONFIG_LANGUAGE_EN_US=y \
    CONFIG_LCD_ST7789_240X280=y \
    CONFIG_BOARD_TYPE_LAFVIN_S3_169_CAM=y; do
    grep -qx "$want" "$cfg" || fail "$cfg lacks $want"
done
grep -qE '^CONFIG_OTA_URL="http://192\.168\.0\.11:[0-9]+/xiaozhi/ota/"$' "$cfg" ||
    fail "$cfg OTA_URL is not http://192.168.0.11:<port>/xiaozhi/ota/"

# The header compiled into the image must agree with the sdkconfig we just read.
if [ -f "$dir/config/sdkconfig.h" ]; then
    grep -qx '#define CONFIG_KITTY_LOCKDOWN 1' "$dir/config/sdkconfig.h" ||
        fail "$dir/config/sdkconfig.h was not compiled with CONFIG_KITTY_LOCKDOWN"
fi

# Device key: checked by shape only, never echoed.
if grep -qE '^CONFIG_KITTY_DEVICE_KEY="[0-9a-f]{64}"$' "$cfg"; then
    echo "KITTY CHECK KEY: real (64 hex)"
elif grep -qE '^CONFIG_KITTY_DEVICE_KEY=".+"$' "$cfg"; then
    if [ "${KITTY_REQUIRE_REAL_KEY:-0}" = 1 ]; then
        fail "device key is a placeholder; rebuild after KITTY_DEVICE_KEY exists in the Mini's .env"
    fi
    echo "KITTY CHECK NOTE: placeholder device key; this image gets 403 from the server. Rebuild before flashing (Task 30)."
else
    fail "CONFIG_KITTY_DEVICE_KEY is empty or missing in $cfg"
fi

echo "KITTY CHECK OK"
