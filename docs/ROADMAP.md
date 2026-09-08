# vinylcast — roadmap & backlog

Captures the vision as it evolves so nothing gets lost. Ordered roughly by
dependency: the **core loop** first, then features that need the ADC/recognition,
then the Home Assistant epic.

## ✅ Done / working
- **OwnTone (AirPlay sender)** built from source on the Pi (Debian 13 / Pi 5), running
  as a service, discovers all house AirPlay 1 + 2 speakers.
- **Kiosk backend** (`display/server/app.py`) — proxies OwnTone's outputs API +
  relays its push WebSocket to the browser.
- **Kiosk UI** (`display/web/`) at 1024×600 for the Elecrow 7″:
  - now-playing: big album art + artist/track/album
  - speaker **picker** (the 24 zones) with on/off + volume, collapses to a chip
  - **side timer**: elapsed vs. side length, "FLIP SOON" warning, tap to change length

## ▢ Next (buildable now, no ADC)
- **Kiosk on the touchscreen** — Chromium kiosk → `localhost:8080`, boot into the UI.
- **shairport-sync as an AirPlay-in source** → OwnTone pipe (with metadata). Lets you
  *stream to* the Pi to test the whole UI + send path today — and it's the **exact
  same pipe the vinyl will use** (shairport-sync now, `arecord` from the ADC later),
  so it's on the critical path, not throwaway. Also a permanent "AirPlay-in" feature.
- **nqptp** — companion daemon for tight AirPlay 2 sync (currently NTP fallback).
- OwnTone → **ALSA-only** (quiet the Pulseaudio log noise).

## ▢ Needs the ADC (UCA202) + line-in
- **Line-in capture** → named pipe → OwnTone plays the turntable to the speakers.
- **Now-playing for vinyl via ACR** (audio fingerprinting) — real album art +
  artist/track for a source that carries no metadata. Provider swappable
  (AudD / ACRCloud). See `docs/NOW-PLAYING-ACR.md`.
- **Side length auto-derived** from the identified album (sum the side's track
  durations via MusicBrainz) instead of the manual default.
- **Needle-drop detection** — the silence→audio transition that auto-starts the side
  timer (same signal the ACR sampler uses).

## ▢ Home Assistant integration (epic) — outlet control
All via a **WebSocket from the kiosk to Home Assistant**; HA owns the smart outlet on
the turntable. We do **not** reinvent outlet control.
- **Auto-off at end of side** — detect run-out-groove silence/static → tell HA to cut
  the turntable outlet, so it doesn't wear the needle/album when a side ends.
- **Stop / park button** — one control = stop the OwnTone stream **and** cut turntable
  power. (Note the physics: cutting power stops the platter; resume ramps back up with
  a brief pitch wobble — so this is "stop/park," not a clean mid-song pause. A clean
  pause = stop the stream only, but that leaves the record spinning/wearing.)
- Optional: expose vinylcast state (playing / side elapsed / flip-soon) to HA for
  dashboards & automations.

## Notes
- Kiosk talks to two backends by design: **OwnTone API** (speakers, playback) and, in
  the HA epic, **Home Assistant WS** (the outlet). The screen stays a thin renderer.
