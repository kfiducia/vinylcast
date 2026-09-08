# display/ — touchscreen kiosk app

Phase-2 on-screen UI for vinylcast: a **speaker picker** and a **now-playing** card
on the Elecrow 7" (1024×600). Design rationale is in
[`../docs/SCREEN-UI.md`](../docs/SCREEN-UI.md) and
[`../docs/NOW-PLAYING-ACR.md`](../docs/NOW-PLAYING-ACR.md).

## What's implemented (phase 2a)

A **runnable skeleton** that proves the screen + live-update pipeline end to end:

- `server/app.py` — tiny aiohttp backend: serves the UI, proxies OwnTone's
  `/api/outputs` (the picker) and now-playing artwork, and relays OwnTone's push
  WebSocket to the browser as a state snapshot.
- `web/` — the kiosk front-end, fixed at **1024×600 landscape**: now-playing view
  (album art + title/artist/album) and a picker view (grid of AirPlay zones with
  on/off + volume), collapsing to a chip.
- `kiosk/start-kiosk.sh` — launches Chromium in kiosk mode at the app.
- `systemd/vinylcast-display.service` — runs the backend as a service.

In 2a, "now playing" reflects **OwnTone's own metadata** — so it lights up today when
you AirPlay from a phone, or play a library track. **Vinyl** now-playing (audio
fingerprinting) is phase **2c**: it drops in by replacing `now_playing` in
`server/app.py:build_snapshot()` with the recognizer's output — the UI needs no
changes. See `../docs/NOW-PLAYING-ACR.md`.

## Try it (on the Pi, or any machine with OwnTone reachable)

```sh
cd display
python3 -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt

# Point at your OwnTone if it isn't on localhost:
#   export OWNTONE_HTTP=http://<owntone-host>:3689
#   export OWNTONE_WS=ws://<owntone-host>:3688
../.venv/bin/python server/app.py         # serves http://localhost:8080
```
Open `http://localhost:8080` in a browser (resize to 1024×600 to preview the kiosk
layout). Tap the ⚙ chip → pick zones → Done.

## Install as services (Pi)

```sh
sudo mkdir -p /opt/vinylcast && sudo cp -r . /opt/vinylcast/display
sudo python3 -m venv /opt/vinylcast/.venv
sudo /opt/vinylcast/.venv/bin/pip install -r /opt/vinylcast/display/requirements.txt
sudo cp systemd/vinylcast-display.service /etc/systemd/system/
sudo systemctl enable --now vinylcast-display
# then autostart kiosk/start-kiosk.sh in your graphical session (see docs/SCREEN-UI.md)
```

## Ports / assumptions

- OwnTone **REST** on `:3689`, **push WebSocket** on `:3688` (`websocket_port` in
  `owntone.conf`; enable it if off). Override via `OWNTONE_HTTP` / `OWNTONE_WS`.
- Field names (`selected`, `volume`, queue `title/artist/album`) follow OwnTone's
  [JSON API](https://owntone.github.io/owntone-server/json-api/) — verify against
  your version if something doesn't populate.

## Roadmap

- **2a ✅ this** — kiosk + picker + OwnTone-metadata now-playing.
- **2b** — polish picker (drag-volume, zone grouping), collapse-timeout.
- **2c** — vinyl now-playing via ACR worker (`recognizer/`) + `dsnoop` audio tap.
- **2d** — art crossfade, "Listening…"/fallback states, dim-on-silence.
