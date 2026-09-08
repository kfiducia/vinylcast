#!/bin/sh
# vinylcast — capture USB line-in and feed it to OwnTone's named pipe.
#
# OwnTone plays a named pipe (FIFO) placed in its library as if it were a track.
# We create that FIFO and have ALSA (arecord) write raw PCM16 stereo 44.1 kHz into
# it — exactly the format OwnTone's pipe input expects.
#
# Config via environment (set in the systemd unit):
#   CARD  ALSA capture device, from `arecord -l`      (default: hw:1,0)
#   PIPE  FIFO path inside OwnTone's library dir       (default: /srv/vinylcast/vinyl)
#   GATE  "1" to only pass audio when the record is    (default: 0)
#         actually playing (needs `sox`); pairs with
#         OwnTone pipe_autostart = true.
set -eu

CARD="${CARD:-hw:1,0}"
PIPE="${PIPE:-/srv/vinylcast/vinyl}"
GATE="${GATE:-0}"

# Create the FIFO once (OwnTone auto-detects it in the library dir).
if [ ! -p "$PIPE" ]; then
    rm -f "$PIPE"
    mkfifo "$PIPE"
fi

# -f cd == signed 16-bit LE, 44100 Hz, 2 channels — OwnTone's required pipe format.
if [ "$GATE" = "1" ]; then
    # Silence-gated: sox opens/holds the stream only while there's real signal, so
    # OwnTone (with pipe_autostart = true) starts on needle-drop and stops when the
    # record ends. Thresholds are conservative; tune the 2% / 2.0 to taste.
    #   silence 1 0.1 2%  : start passing after 0.1s above 2% level
    #   silence 1 2.0 2%  : (trim trailing) stop after 2.0s below 2% level
    exec arecord -D "$CARD" -f cd -t raw \
        | sox -t raw -e signed -b 16 -c 2 -r 44100 - -t raw - \
              silence 1 0.1 2% 1 2.0 2% \
        > "$PIPE"
else
    # Continuous: always streaming. Pair with OwnTone pipe_autostart = false and
    # press Play in the OwnTone UI when you want it (also lets you pick zones).
    exec arecord -D "$CARD" -f cd -t raw > "$PIPE"
fi
