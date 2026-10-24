#!/usr/bin/env bash
# kitty-build.sh <variant> <out_dir> [scripts/build.py options]
#
# Builds one lafvin-s3-169-cam variant and copies the flashable artifacts into <out_dir>, one folder
# per variant with its own sdkconfig (R9: build-ptt, build-wake), then runs kitty-check.sh on it.
# Flash from <out_dir> only, never from build/ (scripts/build.py reuses build/ for every variant).
#
# Without extra options: en-US, wake word disabled (push to talk on BOOT). Language and wake word
# are build parameters, never board config.json options (upstream rule); kitty-check.sh still
# requires CONFIG_LANGUAGE_EN_US=y in the result.
# Run from a shell where ESP-IDF is exported:
#   . ~/esp/esp-idf-v6/export.sh && scripts/kitty-build.sh lafvin-s3-169-cam build-ptt
set -euo pipefail
cd "$(dirname "$0")/.."

variant=${1:?usage: kitty-build.sh <variant> <out_dir> [build.py options]}
out=${2:?usage: kitty-build.sh <variant> <out_dir> [build.py options]}
shift 2
[ $# -gt 0 ] || set -- --language en-US --wake-word disabled

case "$out" in
build | build/* | ./build | ./build/*)
    echo "kitty-build: out_dir must not be build/ (scripts/build.py owns it)" >&2
    exit 2
    ;;
esac

scripts/kitty-key.sh
python scripts/build.py lafvin-s3-169-cam --name "$variant" "$@"

rm -rf "$out"
mkdir -p "$out"
cp sdkconfig "$out/sdkconfig"
for f in \
    xiaozhi.bin \
    merged-binary.bin \
    generated_assets.bin \
    ota_data_initial.bin \
    bootloader/bootloader.bin \
    partition_table/partition-table.bin \
    flash_args \
    flasher_args.json \
    config/sdkconfig.h \
    config/sdkconfig.json; do
    if [ -f "build/$f" ]; then
        mkdir -p "$out/$(dirname "$f")"
        cp "build/$f" "$out/$f"
    fi
done
# The image and sdkconfig carry the device key.
chmod -R go-rwx "$out"

scripts/kitty-check.sh "$out"
