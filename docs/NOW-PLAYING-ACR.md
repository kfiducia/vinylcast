# "Now playing" from vinyl — the audio-fingerprinting problem

This is the interesting one, and it's worth understanding *why* it's harder than it
looks before picking an approach.

## The core problem: vinyl carries no metadata

When you stream Spotify or AirPlay from your phone, the track name / artist / album
art ride *alongside* the audio as metadata — the player just hands them to the
screen. **A turntable sends none of that.** All the Pi receives is an analog
waveform: voltage wiggling in time. There is no "this is track 3 of *Rumours*" data
anywhere in the signal.

So to show what's playing, you have to do what Shazam does: **listen to the actual
audio, compute an acoustic fingerprint, and match it against a database of known
recordings** (automatic content recognition, "ACR"). That match then gives you the
artist/title/album, from which you fetch album art. This is a fundamentally
different, fuzzier operation than reading a metadata field — it can be wrong, it
needs a few seconds of clean audio, and it leans on a big external catalog.

## Your provider options, honestly ranked

You named "Gracenote or Shazam or something." Here's the real landscape:

| Option | Verdict | Why |
|---|---|---|
| **AudD** ([audd.io](https://audd.io)) | **Recommended to start** | Simple REST API: POST a short audio clip, get back artist/title/album + links to Apple/Spotify/Deezer (and often album art). Cheap, has a trial, trivial to wire. Best "get it working this weekend" path. |
| **ACRCloud** ([acrcloud.com](https://www.acrcloud.com)) | **Recommended for the polished build** | Purpose-built for *continuous broadcast monitoring* — you point it at a rolling stream and it emits recognitions as tracks change, which is exactly our situation. Rich metadata + cover art. Free tier/trial; paid as you scale. More setup than AudD. |
| **Shazam** | Avoid for a durable build | No official public API for this use. The unofficial RapidAPI wrappers exist but are ToS-gray and break without notice. Fine to prototype, bad to depend on. |
| **Gracenote** | Not realistically accessible | Enterprise licensing; not hobby-obtainable. Skip. |
| **Self-hosted** (Dejavu, Olaf, chromaprint/AcoustID) | Niche fit | These only recognize recordings you've **pre-fingerprinted** (Dejavu/Olaf) or that exist in the open **AcoustID/MusicBrainz** DB (chromaprint). AcoustID+MusicBrainz is free and could work, but coverage is patchier than commercial ACR and album art comes separately from Cover Art Archive. Good "no ongoing cost / it's my own collection" option; more work, lower hit rate on obscure pressings. |

**My recommendation:** start with **AudD** to prove the UX, and graduate to
**ACRCloud** if you want the always-on "it just updates as sides change" feel.
Design the code so the recognizer is a swappable module (see the interface sketch
below) so switching providers is a one-file change.

## Set expectations on accuracy

ACR is excellent on commercially released, well-known recordings and **flaky on**:
obscure/indie pressings, classical (which movement?), live/bootleg versions,
and the lead-in seconds of a track. It needs ~**5–10 s of reasonably clean audio**
to lock on. Plan the UI to degrade gracefully: show "Listening…", and if no match,
just fall back to a tasteful "Side A · vinyl" placeholder rather than a spinner of
shame.

## Pipeline shape

```
                       ┌──────────────────────────────► OwnTone pipe (audio to speakers)
line-in (ALSA dsnoop) ─┤
                       └──► ACR sampler ──► grab ~10 s ──► [AudD/ACRCloud] ──► {artist,title,album}
                                 ▲                                                    │
                          track-change trigger                                       ▼
                          (silence between tracks)                    album art (iTunes Search API)
                                                                                     │
                                                                                     ▼
                                                                    push to screen UI (WebSocket)
```

### Tapping the same input twice (without fighting over the sound card)

A USB capture device is usually single-open — if OwnTone's `arecord` holds it, a
second `arecord` for ACR gets "device busy." The clean fix is the ALSA **`dsnoop`**
plugin, which lets multiple readers share one capture device. Define it in
`/etc/asound.conf`:

```
pcm.vinyl_snoop {
    type dsnoop
    ipc_key 2202
    slave {
        pcm "hw:1,0"          # your USB ADC from `arecord -l`
        channels 2
        rate 44100
        format S16_LE
    }
}
```

Then point **both** the OwnTone capture service **and** the ACR sampler at
`-D vinyl_snoop` instead of `hw:1,0`. (Update `CARD=vinyl_snoop` in the capture
service; the ACR worker opens the same.)

### When to recognize (don't hammer the API)

Two strategies, combine them:

- **Track-change trigger:** vinyl has a short quiet gap between tracks. Detect that
  silence (RMS below a threshold for ~1–2 s, e.g. via `sox`/simple math on the
  sampler stream) and fire **one** recognition when audio resumes. This is both
  cheaper and more accurate than time-polling.
- **Fallback poll:** if no silence is seen (continuous/gapless side), re-recognize
  every ~90–120 s so a long side still updates.

This keeps you to a handful of API calls per side — pennies with AudD, within
ACRCloud's monitoring model.

### Album art

Whichever ACR you use, the free, no-key way to fetch cover art is the **iTunes
Search API**:
```
https://itunes.apple.com/search?term=<artist>+<track>&entity=song&limit=1
```
Take `artworkUrl100` and swap the size (`100x100` → `600x600` or `1200x1200`) for a
crisp full-screen image. ACRCloud/AudD also return streaming-service IDs you can use
to pull art directly if you prefer.

## Recognizer interface (keep providers swappable)

```python
# display/recognizer/base.py  — pseudo-interface
class Recognizer:
    def identify(self, wav_bytes: bytes) -> dict | None:
        """Return {'artist','title','album','artwork_url'} or None if no match."""

# Implementations: AuddRecognizer, AcrCloudRecognizer, AcoustIdRecognizer.
# The screen app calls identify(); swapping providers never touches the UI.
```

## Cost sketch

- **AudD:** roughly a few dollars per ~1000 recognitions (check current pricing);
  with track-change triggering you'll do maybe 10–15 per listening session, so this
  is coffee-money territory for personal use.
- **ACRCloud:** free tier for low volume; paid monitoring plans if you leave it on
  24/7.
- **AcoustID/MusicBrainz self-hosted:** free, just your effort and a lower hit rate.
