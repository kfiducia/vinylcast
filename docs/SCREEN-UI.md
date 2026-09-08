# On-screen UI — speaker picker + now-playing display

The Pi already has spare CPU, so a touchscreen turns vinylcast from a headless box
into an appliance: **pick your AirPlay zones, then watch the album art for whatever's
on the platter.** This doc covers the display app's UX and the two APIs it stands
on. The recognition half lives in [NOW-PLAYING-ACR.md](NOW-PLAYING-ACR.md).

## Target panel: Elecrow 7" 1024×600 (landscape)

Design the layout for **1024×600, landscape**. It's a wide, short canvas (only 600 px
tall), which actually suits a "big square of album art on one side, text on the other"
now-playing screen. See "Putting it on the Elecrow panel" below for the kiosk config.

## The two-state UX you described (laid out for 1024×600 landscape)

```
 PICKER  (first run / tap ⚙︎)                    NOW-PLAYING  (default)
 ┌────────────────────────────────────────┐    ┌────────────────────────────────────────┐
 │  STREAM TO…                            │    │ ▸ Living Room · Kitchen            ⚙︎  │ ← chip
 │  ┌────────┐┌────────┐┌────────┐        │    │ ┌──────────────┐                        │
 │  │Living ✓││Kitchen✓││Bedroom │  once  │    │ │██████████████│  Dreams                │
 │  ├────────┤├────────┤├────────┤ ─────▶ │    │ │██ ALBUM ART ██│  Fleetwood Mac         │
 │  │Office  ││Patio   ││Bath    │        │    │ │██  ~560px   ██│  Rumours · 1977        │
 │  └────────┘└────────┘└────────┘        │    │ └──────────────┘                        │
 │                       [ Done ]         │    │                    ◔ Side A · 12:04     │
 └────────────────────────────────────────┘    └────────────────────────────────────────┘
   grid of AirPlay outputs, toggle + vol         art fills the height; text column right
```

- **Picker view:** a grid of discovered AirPlay outputs with on/off toggles and
  per-zone volume. Tapping **Done** (or a timeout) collapses it to a small chip
  showing the active zones.
- **Now-playing view (default):** full-screen album art + title/artist/album,
  updated as tracks change. Tap the ⚙︎/chip to reopen the picker.
- **Graceful empty states:** "Listening…" while recognizing, and a neutral
  "vinyl · Side A" card when a track can't be identified (ACR isn't perfect — see
  the ACR doc).

## Standing on OwnTone's API (the picker is basically free)

You do **not** need to talk AirPlay yourself — OwnTone already discovers the
speakers and exposes them over a local REST + WebSocket API. The picker is a thin
client over it:

| Need | OwnTone endpoint |
|---|---|
| List AirPlay outputs (zones) | `GET /api/outputs` |
| Enable/disable a zone, set volume | `PUT /api/outputs/{id}` |
| Start/stop the `vinyl` pipe, transport | `PUT /api/player/play|pause`, `/api/queue` |
| Live push (output + player changes) | WebSocket `ws://<pi>:3689/ws` (subscribe to `outputs`, `player`) |

So "pick devices → minimize" maps directly onto `GET /api/outputs` →
toggle via `PUT /api/outputs/{id}` → collapse. No AirPlay plumbing in your app.

Reference: OwnTone JSON API — https://owntone.github.io/owntone-server/json-api/

## Standing on the ACR worker for now-playing

The recognizer (AudD/ACRCloud — see [NOW-PLAYING-ACR.md](NOW-PLAYING-ACR.md)) runs
as a small background worker that pushes `{artist,title,album,artwork_url}` whenever
it identifies a new track. The screen app just renders the latest and animates the
art swap on change.

## How to actually put it on the screen (kiosk)

Simplest, most flexible: run the app as a **local web page in Chromium kiosk mode**
on the Pi's framebuffer. Web tech gives you easy album-art layout, touch, and
animation, and it reuses OwnTone's HTTP/WS API directly.

- Hardware here: the **Elecrow 7" 1024×600 HDMI capacitive** panel (see next
  section for its exact wiring/mode config).
- Boot to a minimal GUI and launch Chromium:
  ```sh
  chromium-browser --kiosk --noerrdialogs --disable-infobars \
    --check-for-update-interval=31536000 http://localhost:8080
  ```
  (Run under a `cage`/`wayfire` or X session; `raspi-config` can auto-login to
  desktop, then a systemd `--user` unit launches Chromium.)
- The app at `:8080` is served by a tiny local backend (see `display/`) that:
  1. proxies/relays OwnTone `/api/outputs` for the picker,
  2. exposes the latest ACR result + a WebSocket for live now-playing updates,
  3. serves the static front-end.

Alternative if you want to avoid a browser: a lightweight native kiosk (e.g. a
Python **pygame**/**Qt** or a **Flutter-pi** app) drawing straight to the
framebuffer. More efficient, more code. Start with Chromium kiosk; optimize later.

## Putting it on the Elecrow 7" panel (1024×600, HDMI + USB)

This panel is **driver-free**: HDMI carries video, one USB cable carries **both the
capacitive touch (as a standard USB-HID device) and power**. The Pi sees it as an
ordinary HDMI monitor and a USB touchscreen — no Elecrow driver needed. Two things to
get right:

**1. Force the 1024×600 mode (it's non-standard, so autodetect can miss it).**
Edit `/boot/firmware/config.txt` (older Pi OS: `/boot/config.txt`):

- **Pi 4 / older, or legacy (fkms) stack:**
  ```
  hdmi_group=2
  hdmi_mode=87
  hdmi_cvt=1024 600 60 6 0 0 0
  hdmi_drive=1
  ```
- **Pi 5 / Bookworm (the default `vc4-kms-v3d` KMS driver ignores most `hdmi_*`):**
  usually EDID reports 1024×600 correctly and you need nothing. If it doesn't, force
  it via the kernel cmdline in `/boot/firmware/cmdline.txt` (one line, append):
  ```
  video=HDMI-A-1:1024x600@60
  ```
  (Use `HDMI-A-2` if you're on the Pi 5's second HDMI port. Check what's detected with
  `kmsprint` or `cat /sys/class/drm/*/modes`.)

**2. Touch is plug-and-play.** As a USB-HID capacitive device it works in Chromium /
Wayland with no calibration in the default landscape orientation. **Only if you rotate
the display** do you also need to rotate the touch input so taps land in the right
place:
- Wayland (Bookworm default): set `rotate` for the output (e.g. via `wlr-randr` or the
  compositor config) — it rotates video *and* touch together.
- X11: rotate video with `xrandr -o` **and** apply a matching touch transform matrix
  with `xinput set-prop ... "Coordinate Transformation Matrix" ...`, or the pointer
  won't track the rotated image.

**3. Design to 1024×600.** Keep the UI at exactly this size, landscape. Album art fills
the ~560 px height with the text column beside it (see the mock above). Avoid layouts
that assume 720p/1080p — 600 px of height is the real constraint.

**Sanity check before writing any app:** boot to desktop, confirm the picture is crisp
at 1024×600 (not letterboxed/blurry) and that dragging a window with your finger
tracks correctly. Get that solid first; the kiosk app is just what you point Chromium
at afterward.

## Suggested app shape

```
display/
  server/            # tiny FastAPI/Flask (or Node) backend
    outputs.py       #   proxy to OwnTone GET/PUT /api/outputs
    nowplaying.py    #   holds latest ACR result; WebSocket push to UI
    recognizer/      #   AudD/ACRCloud/AcoustID implementations (swappable)
  web/               # static kiosk front-end (two views: picker, now-playing)
    index.html
    app.js           #   OwnTone WS for outputs/player, app WS for now-playing
    style.css
```

This keeps the AirPlay concerns (OwnTone) and the recognition concerns (ACR) behind
two clean seams, so the screen is just a renderer.

## Build order (so you always have something working)

1. **Phase 2a** — kiosk shows OwnTone's *own* metadata (works today for AirPlay
   *from your phone*; proves the screen + WS pipeline end to end).
2. **Phase 2b** — add the picker view over `/api/outputs`; collapse-to-chip UX.
3. **Phase 2c** — wire the ACR worker + `dsnoop` tap; light up real vinyl
   now-playing with album art. Start with AudD, one recognition on track-change.
4. **Phase 2d** — polish: art crossfade, "Listening…"/fallback states, per-zone
   volume sliders, screensaver/dim on silence.
