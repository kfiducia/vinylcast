#!/bin/bash
# vinylcast kiosk launcher — wait for the display backend, then open Chromium
# fullscreen at the UI. Launched from labwc autostart via `lwrespawn` so it
# relaunches automatically if Chromium exits. Runs inside the labwc/Wayland
# session, so WAYLAND_DISPLAY / XDG_RUNTIME_DIR are already set.
for i in $(seq 1 60); do
    curl -fsS http://localhost:8080/ >/dev/null 2>&1 && break
    sleep 1
done
exec chromium --kiosk --ozone-platform=wayland \
    --user-data-dir="$HOME/.kiosk-chrome" \
    --no-first-run --no-default-browser-check --disable-session-crashed-bubble \
    --disable-infobars --noerrdialogs --disable-features=Translate \
    --check-for-update-interval=31536000 --autoplay-policy=no-user-gesture-required \
    --password-store=basic \
    http://localhost:8080
