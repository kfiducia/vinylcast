# Setup — step by step

This walks through a working build on Raspberry Pi OS. Each step says *what* to do
and *why*, plus how to verify it before moving on. Budget ~30–45 minutes.

Assumes you've read [HARDWARE.md](HARDWARE.md) and have the turntable → ADC → Pi
chain physically connected.

---

## 1. Base OS

Flash **Raspberry Pi OS Lite (64-bit)** with the Raspberry Pi Imager. In the
Imager's settings, pre-set the hostname (e.g. `vinylcast`), enable SSH, and enter
your Wi-Fi (or use Ethernet — recommended for multiroom timing stability).

Boot, SSH in, update:
```sh
sudo apt update && sudo apt full-upgrade -y
```

## 2. Confirm the Pi sees your USB ADC

Plug in the ADC. Then:
```sh
arecord -l
```
You should see your device, e.g.:
```
card 1: CODEC [USB Audio CODEC], device 0: USB Audio [USB Audio]
```
**Write down the card/device numbers** — here it's `card 1, device 0`, i.e. ALSA
address **`hw:1,0`**. You'll put this in the capture service.

Verify you can actually capture (play a record, then):
```sh
arecord -D hw:1,0 -f cd -d 5 /tmp/test.wav   # 5-second grab, S16_LE/44100/stereo
aplay /tmp/test.wav                            # or scp it off and listen
```
If `/tmp/test.wav` has your record on it, the capture chain works. If it's silent
or barely audible, revisit phono vs line level in [HARDWARE.md](HARDWARE.md) and
check your input isn't muted:
```sh
alsamixer -c 1     # F4 for capture view; unmute (M) and raise the Capture level
sudo alsactl store # persist mixer settings across reboots
```

## 3. Install OwnTone

```sh
sudo apt install -y owntone alsa-utils
```
OwnTone ships as a systemd service and a web UI on port **3689**. Confirm it's up:
```sh
systemctl status owntone
```
Browse to `http://vinylcast.local:3689` (or the Pi's IP). You should get the
OwnTone web interface. Your AirPlay speakers should appear under **Outputs** once
OwnTone discovers them on the network (they must be on the same subnet / mDNS
reachable).

> If AirPlay speakers don't show up: they and the Pi must be on the same L2 network
> for mDNS/Bonjour discovery. Guest VLANs and some mesh routers block this.

## 4. Create the pipe + capture pieces

OwnTone plays a **named pipe** placed in its library as if it were a track. We put
the pipe in a dedicated dir owned by the `owntone` user.

```sh
sudo mkdir -p /srv/vinylcast
sudo chown owntone:owntone /srv/vinylcast
```

Install the capture script and service from this repo:
```sh
sudo install -m0755 scripts/linein-capture.sh /usr/local/bin/vinylcast-capture
sudo install -m0644 systemd/vinylcast-capture.service /etc/systemd/system/
```

Edit the service so `CARD=` matches your `arecord -l` result from step 2:
```sh
sudo systemctl edit --full vinylcast-capture   # set Environment=CARD=hw:1,0
```

## 5. Point OwnTone at the pipe

Add the library directory and pipe behaviour. Merge the snippet from
`config/owntone.conf.snippet` into `/etc/owntone.conf` (inside the existing
`library { … }` block — don't create a second one):

```
library {
    directories = { "/srv/vinylcast" }

    # false: OwnTone only reads the pipe when YOU press play (recommended — lets you
    #        choose which zones, and it won't stream tape-hiss 24/7). See §7 for the
    #        autostart alternative.
    pipe_autostart = false
}
```
Restart OwnTone:
```sh
sudo systemctl restart owntone
```

## 6. Start capture and play

```sh
sudo systemctl enable --now vinylcast-capture
```
This creates `/srv/vinylcast/vinyl` (the FIFO) and has `arecord` feed it. In the
OwnTone web UI:

1. Under **Outputs**, toggle ON the AirPlay speakers/zones you want.
2. Find the **`vinyl`** pipe track (Files → your library) and press **Play**.
3. Drop the needle. After the ~1–2 s AirPlay buffer, all selected zones play in
   sync.

Adjust per-zone volume in OwnTone. That's it.

## 7. Optional: autostart when the needle drops

With `pipe_autostart = false` (the default above) you press Play yourself, which is
usually what you want because it also lets you pick zones each time. If you'd rather
it **start automatically** whenever audio flows:

- Set `pipe_autostart = true` in `/etc/owntone.conf` and restart OwnTone. It will
  begin playing to your **last-selected** outputs as soon as the pipe has audio.
- Caveat: a plain continuous `arecord` writes *silence/hiss* even when the platter
  is stopped, so autostart would play forever. To gate on real signal, switch the
  capture to the **silence-gated** mode described in
  [`scripts/linein-capture.sh`](../scripts/linein-capture.sh) (uses `sox`'s
  `silence` effect so the pipe only carries audio when the record is actually
  playing). Install sox first: `sudo apt install -y sox`.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Speakers don't appear in OwnTone | mDNS blocked — put Pi + speakers on same VLAN/subnet; disable AP/client isolation. |
| `vinyl` track missing | Pipe not created or wrong owner. Check `ls -l /srv/vinylcast/vinyl`, `journalctl -u vinylcast-capture`. |
| Silent / very quiet | Phono vs line level (see HARDWARE.md); capture muted in `alsamixer -c <card>`. |
| Audio present but never stops (autostart) | Expected with continuous capture — use manual play, or silence-gated mode (§7). |
| Dropouts / zones drift | Wi-Fi congestion; use Ethernet for the Pi, reduce number of zones, keep 2.4/5 GHz clean. |
| Hum/buzz | Grounding — see the hum note in HARDWARE.md. |
| `arecord` "Device or resource busy" | Something else grabbed the card. Only the capture service should use it. |

## Verifying the whole chain quickly

```sh
journalctl -u vinylcast-capture -f      # capture running, no errors
journalctl -u owntone -f                # OwnTone opened the pipe when you pressed play
ls -l /srv/vinylcast/vinyl              # should be a 'p' (fifo), owned by owntone
```
