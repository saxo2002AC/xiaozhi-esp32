# kitty-gif: sources

The Mission Kitty face: a cream robot-cat head with a dark glass visor, glowing aqua LED eyes and
mouth, pink cheeks and an antenna light. The art is original vector drawing done in code by
`../kitty-face/generate.py` (Pillow, version pinned in `../kitty-face/requirements.txt`). No image
from any other project is copied, traced or embedded. Regenerate with:

```sh
cd main/boards/lafvin-s3-169-cam/kitty-face
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python generate.py --sheet contact-sheet.png
```

The generator is deterministic: two runs give byte-identical GIFs.

## Reference

- LAFVIN ESP32-S3 1.69" LCD sample `IDF/usb_webcam/eyes_show`:
  https://github.com/lafvintech/LAFVIN-ESP32S3-1.69-LCD/tree/main/IDF/usb_webcam/eyes_show
  - Used only as a reference for the idea (animated eyes in GIFs, shown centred on this 240x280
    panel through LVGL). Nothing was copied from it.
  - Licence: `show_eyes.c` carries `SPDX-License-Identifier: Apache-2.0` (Espressif Systems,
    2023). The repository has no top-level licence file.

## Format

- 22 GIFs, 200x200 px each. They are shown 1:1 and centred on the 240x280 panel, between the
  status bar and the chat line. The first version was 120x120, which read too small on the panel.
  A 200x200 GIF needs about 200 KB of LVGL heap while it plays (the ARGB canvas plus the index
  frame). The pool is `CONFIG_LV_MEM_SIZE_KILOBYTES=1024`, and only one face plays at a time.
- They loop forever. Every open-eyed face blinks in its loop.
- Each GIF has one 255-colour palette plus a transparent index. A thin white sticker edge keeps
  the 1-bit transparency clean on both the light and the dark theme.
- Every frame is written whole with disposal 2 (restore to background). The firmware's
  `main/display/lvgl_display/gif/gifdec.c` decodes this with no ghosting. That was checked
  frame by frame against the rendered art, over two loops, with `LV_GIF_CACHE_DECODE_DATA` both
  on and off.
- Total is about 1.7 MB. The 8 MB `assets` partition holds 2.6 MB with push to talk and 5.3 MB with
  the wake build's mn7_en model.

## Names

The 21 emotion names are the ones the server sends (`neutral`, `happy`, `laughing`, `funny`,
`sad`, `angry`, `crying`, `loving`, `embarrassed`, `surprised`, `shocked`, `thinking`, `winking`,
`cool`, `relaxed`, `delicious`, `kissy`, `confident`, `sleepy`, `silly`, `confused`).

The board itself sets two of the faces (see `KittyLcdDisplay` in `../lafvin_s3_169_cam_board.cc`):

- `listening` (an extra face, not a server emotion): shown while BOOT is held.
- `thinking`: shown from the moment the child's words are recognized until the reply's emotion
  arrives. If no emotion arrives (the server's emoji feature is off), the first spoken line
  switches it to `happy`, so Kitty never "thinks" through a whole reply.

`happy` is the server's default reply emotion, so its mouth moves as if talking: it doubles as the
speaking face. `confused` is also the "I can't see" face.

Keep only face GIFs in this folder. `build_default_assets.py` packs every `.png` and `.gif` here
as an emotion, which is why the contact sheet lives in `../kitty-face/`.
