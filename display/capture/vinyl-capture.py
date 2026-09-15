#!/usr/bin/env python3
"""vinylcast capture controller — the piece that makes the vinyl path automatic.

The problem it solves: something has to feed the turntable audio into OwnTone's pipe
FIFO, but it must NOT feed continuously — if it did, OwnTone would play silence 24/7,
so the screen would never sleep, the side timer would never reset, and the AirPlay
speakers would stream silence forever.

So this service *gates* the feed on audio presence. It continuously measures the
line-in level (USB ADC via ALSA dsnoop). While a record is playing it runs an arecord
that streams the audio into the FIFO and keeps OwnTone playing; when the line-in goes
quiet for a few seconds (needle lifted / run-out groove after a lift) it stops the feed
and stops OwnTone.

Everything downstream already keys off OwnTone's play state:
  * the display backend's /state → screen wakes on play, sleeps on stop
  * the vinyl ACR recognizer → identifies on play, clears on stop
  * the kiosk side timer → starts on needle-drop, resets on lift
…so gating the feed here drives the whole appliance. Nothing else needs to change.

Tapping the single-open ADC for BOTH this monitor and the FIFO feed (and the backend's
ACR sampler) relies on the ALSA dsnoop devices in /etc/asound.conf (vinyl_snoop /
vinyl_snoop_mono).

Env (all optional):
  VINYL_MONITOR_DEV  ALSA device to measure level on   (default vinyl_snoop_mono)
  VINYL_FIFO_DEV     ALSA device to feed OwnTone from   (default vinyl_snoop)
  VINYL_FIFO         OwnTone pipe FIFO path             (default /srv/vinylcast/vinylcast)
  OWNTONE_HTTP       OwnTone REST base                  (default http://localhost:3689)
  VINYL_ON_RMS       raw 16-bit RMS above which=playing (default 400 ≈ -38 dBFS)
  VINYL_ON_SECS      sustained presence before start    (default 1.0)
  VINYL_OFF_SECS     sustained silence before stop      (default 8.0)
"""
import array
import math
import os
import signal
import subprocess
import sys
import time
import urllib.request

MON = os.environ.get("VINYL_MONITOR_DEV", "vinyl_snoop_mono")
FEED = os.environ.get("VINYL_FIFO_DEV", "vinyl_snoop")
FIFO = os.environ.get("VINYL_FIFO", "/srv/vinylcast/vinylcast")
OWNTONE = os.environ.get("OWNTONE_HTTP", "http://localhost:3689").rstrip("/")
ON_RMS = int(os.environ.get("VINYL_ON_RMS", "400"))
ON_SECS = float(os.environ.get("VINYL_ON_SECS", "1.0"))
OFF_SECS = float(os.environ.get("VINYL_OFF_SECS", "8.0"))

RATE = 44100
CHUNK_SECS = 0.25
CHUNK_BYTES = int(RATE * CHUNK_SECS) * 2   # mono, 16-bit

_feed = None                               # the arecord → FIFO subprocess (or None)


def log(msg: str) -> None:
    print("[vinyl-capture] %s" % msg, flush=True)


def _owntone(path: str) -> None:
    try:
        req = urllib.request.Request(OWNTONE + path, method="PUT")
        urllib.request.urlopen(req, timeout=4).read()
    except Exception as e:  # noqa: BLE001
        log("OwnTone %s error: %s" % (path, e))


def start_feed() -> None:
    """Stream the line-in into the FIFO and nudge OwnTone to play."""
    global _feed
    if _feed and _feed.poll() is None:
        return
    log("audio present → start feed")
    # arecord opens the FIFO for write (blocks until OwnTone opens read via pipe_autostart);
    # that's fine, it's a child process. Raw PCM matches what OwnTone's pipe input expects.
    _feed = subprocess.Popen(
        ["sh", "-c",
         "exec arecord -D %s -f S16_LE -c2 -r%d -t raw > %s" % (FEED, RATE, FIFO)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)                        # give OwnTone a moment to attach to the pipe
    _owntone("/api/player/play")           # explicit play (pipe_autostart alone can land on pause)


def stop_feed() -> None:
    """Stop the feed so OwnTone hits pipe EOF and stops."""
    global _feed
    if _feed and _feed.poll() is None:
        log("silence → stop feed")
        _feed.terminate()
        try:
            _feed.wait(timeout=3)
        except subprocess.TimeoutExpired:
            _feed.kill()
    _feed = None
    _owntone("/api/player/stop")           # explicit stop → screen sleeps, timer resets


def _open_monitor() -> subprocess.Popen:
    return subprocess.Popen(
        ["arecord", "-D", MON, "-f", "S16_LE", "-c", "1", "-r", str(RATE),
         "-t", "raw", "-q", "/dev/stdout"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)


def main() -> int:
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    log("start: monitor=%s feed=%s fifo=%s on_rms=%d on=%.1fs off=%.1fs"
        % (MON, FEED, FIFO, ON_RMS, ON_SECS, OFF_SECS))
    mon = _open_monitor()
    playing = False
    above_since = None
    below_since = None
    try:
        while True:
            raw = mon.stdout.read(CHUNK_BYTES)
            if not raw or len(raw) < CHUNK_BYTES:
                log("monitor stream ended → reopening")
                try:
                    mon.kill()
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(1.0)
                mon = _open_monitor()
                continue
            a = array.array("h")
            a.frombytes(raw)
            rms = math.sqrt(sum(x * x for x in a) / len(a))
            now = time.monotonic()
            if rms >= ON_RMS:
                below_since = None
                above_since = above_since or now
                if not playing and (now - above_since) >= ON_SECS:
                    start_feed()
                    playing = True
            else:
                above_since = None
                below_since = below_since or now
                if playing and (now - below_since) >= OFF_SECS:
                    stop_feed()
                    playing = False
    finally:
        stop_feed()
        try:
            mon.kill()
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
