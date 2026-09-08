# Hardware

You need three things: a **Raspberry Pi**, a **USB audio input (ADC) with line-in**,
and — depending on your turntable — a **phono preamp**. The trick to keeping this
simple is picking an ADC that already contains the phono preamp.

## The decision that determines your parts list: does your turntable output line level or phono level?

A bare moving-magnet (MM) cartridge outputs **phono level** — tiny (~5 mV) and
RIAA-equalized. It *must* go through a phono preamp before anything else, or it'll
be near-silent and sound bass-light/harsh. Two common situations:

- **Your turntable has a built-in preamp** (a `PHONO / LINE` switch set to `LINE`,
  or it's a modern "plug into powered speakers" deck) → it already outputs **line
  level**. You just need a plain line-in ADC.
- **Your turntable is bare / vintage / switch set to `PHONO`** → it outputs **phono
  level**. You need a phono preamp, either standalone or built into the ADC.

If you're not sure: if your turntable can drive powered speakers or an AUX input
directly and sound normal, it's line level.

## Recommended parts

### 1. Raspberry Pi
- **Raspberry Pi 4 (2 GB)** — comfortable headroom, wired Ethernet (nice for
  multiroom sync stability). Best default.
- **Pi 5** — overkill but fine.
- **Pi Zero 2 W** — works, Wi-Fi only; fine for a couple of zones, tighter on a
  large multiroom setup. Cheapest/smallest.
- Plus: quality SD card (32 GB+), official power supply. Underpowering a Pi with a
  USB audio device attached causes flaky audio — use the real PSU.

### 2. USB audio input (ADC) — pick based on the decision above

| Situation | Recommended ADC | Why |
|---|---|---|
| **Bare turntable (phono level)** | **Behringer U-PHONO UFO202** | Has a **built-in phono preamp with RIAA**. Turntable → UFO202 → USB. One box, two RCA cables, done. ~$30, class-compliant (no drivers). The standard "digitize my vinyl" board. |
| **Line-level turntable / any line source** | **Behringer U-CONTROL UCA202** | Clean line-in USB ADC, no phono stage. ~$30, class-compliant. (Feed a line-level signal only — a bare cartridge will be too quiet.) |
| **Want better fidelity** | Focusrite Scarlett Solo / 2i2, or any class-compliant USB interface with a line input | 24-bit, better converters. Overkill for AirPlay's lossy-ish path but nice if you also record. |

> **Class-compliant** matters: it means ALSA sees it with no drivers. All of the
> above are. Avoid random no-name cards that need Windows drivers.

### 3. Phono preamp — *only* if your turntable is phono-level **and** you didn't pick the UFO202
- Simplest: the **UFO202 above already includes one** — this is why it's the top
  pick for bare turntables.
- Standalone options if you went with a line-in ADC but have a phono deck:
  **ART DJPRE II**, **Schiit Mani**, **Pro-Ject Phono Box** — turntable → phono
  preamp → line-in ADC.

## Wiring summary

**Bare turntable, UFO202:**
```
Turntable RCA out ──▶ UFO202 PHONO IN ──USB──▶ Pi
(also connect turntable ground wire to UFO202 ground lug if it has one)
```

**Line-level turntable (or turntable + standalone preamp), UCA202:**
```
Turntable (LINE out / preamp out) ──▶ UCA202 LINE IN ──USB──▶ Pi
```

## Optional: touchscreen (phase 2)

- **Elecrow 7" 1024×600 IPS capacitive (HDMI + USB, driver-free)** — the chosen
  panel for the on-screen picker + now-playing display. HDMI for video, one USB
  cable for touch **and** power; the Pi sees a normal HDMI monitor + USB-HID
  touchscreen, no driver. Setup (forcing the 1024×600 mode, touch, rotation) is in
  [SCREEN-UI.md](SCREEN-UI.md). Any HDMI touch panel works; this doc is tuned to
  this one.
- Note: driving a 7" panel over HDMI+USB pushes the Pi's power budget — use the
  official PSU (and ideally a Pi 4/5), especially with the USB ADC also attached.

## Grounding / hum note

Turntables are hum-prone. If you get a buzz: connect the turntable's ground wire to
the preamp/ADC ground lug, keep the USB ADC away from the Pi's Wi-Fi antenna and
power brick, and prefer a short, shielded RCA run. A powered USB hub can also help
if the Pi's USB power is noisy.

## Rough cost

- Pi 4 (2 GB) + PSU + SD: ~$55–70
- UFO202 (bare turntable) **or** UCA202 (line level): ~$30
- **Total: ~$85–100**, versus a WiiM/Bluesound that may not even do the AirPlay-send
  reliably.
