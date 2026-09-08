# Alternative: Snapcast (if endpoints don't have to be AirPlay)

The main [OwnTone path](SETUP.md) exists because you specifically want to feed
**AirPlay** speakers (HomePods, AirPlay soundbars, etc.). The price you pay is
AirPlay's ~1–2 s buffer.

If your speakers can be anything — or you're placing cheap Pis/amps around the house
as the endpoints — **[Snapcast](https://github.com/badaix/snapcast)** is the better
engine: it's purpose-built for synchronized multiroom, with latency in the **tens of
milliseconds** and famously tight sync between rooms. The trade-off is that each
endpoint runs a **Snapclient** (a small daemon on a Pi/computer), not AirPlay.

## Shape of it

```
Turntable ─▶ ADC ─▶ Pi:  arecord ─▶ Snapserver ──(Wi-Fi/LAN)──▶ Snapclient (Pi + amp/speaker) ×N
```

- **Snapserver** on the capture Pi reads the same ALSA line-in (a `pipe` or `alsa`
  stream source in `snapserver.conf`) and streams it to all clients in sync.
- **Snapclient** on each endpoint plays it out its own DAC/jack.
- Optional: run **shairport-sync** *into* Snapserver too, so the same speakers double
  as AirPlay receivers for phone audio.

## Minimal server config

`/etc/snapserver.conf`:
```ini
[stream]
# Read raw PCM from a pipe that arecord writes (same idea as the OwnTone path).
source = pipe:///srv/vinylcast/vinyl?name=Vinyl&sampleformat=44100:16:2&mode=create
```
Then capture into it exactly like the OwnTone script does:
```sh
arecord -D hw:1,0 -f cd -t raw > /srv/vinylcast/vinyl
```
Install a Snapclient on each endpoint (`sudo apt install snapclient`), point it at
the server, done.

## Which should I pick?

| | OwnTone → AirPlay | Snapcast |
|---|---|---|
| Endpoints | Existing AirPlay speakers/HomePods | Pi/computer running Snapclient |
| Latency | ~1–2 s (whole-home listening) | ~tens of ms (tight) |
| Setup on endpoints | None (already AirPlay) | Install Snapclient each |
| Best when | You already own AirPlay speakers | You're building the endpoints anyway |

You can also run **both** on the same capture Pi and choose per-session.

> This is also the multiroom engine used in the sibling
> [`beep-firmware`](../../beep-firmware) project — those Beep units make natural
> Snapclient endpoints.
