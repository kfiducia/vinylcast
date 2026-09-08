#!/usr/bin/env python3
"""vinylcast display backend.

The kiosk's data source. Two concerns, deliberately separate:

  * OwnTone  — the *audio router*: which AirPlay speakers exist + are selected,
    and whether audio is playing. Read via its REST API.
  * now-playing metadata (artist/track/album + cover art) — read DIRECTLY from
    the metadata source, NOT through OwnTone (OwnTone's pipe-metadata reader
    only grabs it once and drops cover art). For AirPlay-in that source is
    shairport-sync's metadata pipe, parsed here. For vinyl later, the ACR
    recognizer feeds this same `now_playing` slot — the UI never changes.

The frontend gets a periodic snapshot over /ws: {outputs, player, now_playing}.

Env:
  OWNTONE_HTTP     default http://localhost:3689
  SHAIRPORT_META   default /home/vinylcast/shairport-metadata  (a FIFO shairport writes)
  PORT             default 8080
"""
import asyncio
import base64
import json as _json
import logging
import os
import re
import select
import threading
import time
import urllib.parse
import urllib.request

from aiohttp import ClientSession, web

OWNTONE_HTTP = os.environ.get("OWNTONE_HTTP", "http://localhost:3689").rstrip("/")
SHAIRPORT_META = os.environ.get("SHAIRPORT_META", "/home/vinylcast/shairport-metadata")
PORT = int(os.environ.get("PORT", "8080"))
WEB_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "web"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("vinylcast-display")


# --------------------------------------------------------------------------- #
# shairport-sync metadata pipe parser (runs in a background thread)
# --------------------------------------------------------------------------- #
# Format: a stream of <item><type>HEX</type><code>HEX</code><length>N</length>
# [<data encoding="base64">B64</data>]</item>. type/code are 4 ASCII chars in hex.
_ITEM_RE = re.compile(
    rb'<item><type>([0-9a-fA-F]{8})</type><code>([0-9a-fA-F]{8})</code>'
    rb'<length>(\d+)</length>'
    rb'(?:\s*<data encoding="base64">\s*([A-Za-z0-9+/=\s]*?)</data>)?</item>',
    re.DOTALL,
)


def _code(hex_bytes: bytes) -> str:
    try:
        return bytes.fromhex(hex_bytes.decode()).decode("latin-1")
    except Exception:  # noqa: BLE001
        return ""


def _set_art(app: dict, ct: str, data: bytes) -> None:
    """Cache artwork and bump the version so the frontend re-fetches /artwork/current."""
    app["artwork"] = (ct, data)
    app["art_version"] = app.get("art_version", 0) + 1
    np = app.get("nowplaying")
    if np:
        app["nowplaying"] = {**np, "artwork_url": f"/artwork/current?v={app['art_version']}"}


def _fetch(url: str, timeout: int = 5):
    req = urllib.request.Request(url, headers={"User-Agent": "vinylcast/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.headers.get("Content-Type", "")


def itunes_art_lookup(app: dict, key: tuple) -> None:
    """Fetch cover art from the iTunes Search API for `key` = (title, artist, album).
    Runs in its own thread; only applies if the track hasn't changed and the source
    (PICT) hasn't already supplied art."""
    title, artist, album = key
    for term, entity in ((f"{artist} {album}", "album"), (f"{artist} {title}", "song")):
        term = term.strip()
        if not term:
            continue
        try:
            q = urllib.parse.urlencode({"term": term, "entity": entity, "limit": 1, "country": "US"})
            body, _ = _fetch(f"https://itunes.apple.com/search?{q}", timeout=4)
            results = _json.loads(body).get("results") or []
            if not results:
                continue
            art = results[0].get("artworkUrl100") or results[0].get("artworkUrl60")
            if not art:
                continue
            art = art.replace("100x100bb", "600x600bb").replace("60x60bb", "600x600bb")
            img, ct = _fetch(art, timeout=5)
            # apply only if still the current track AND the source didn't already give art
            if img and app.get("track_key") == key and app.get("artwork") is None:
                _set_art(app, ct or "image/jpeg", img)
            return
        except Exception:  # noqa: BLE001
            continue


def metadata_reader(app: dict) -> None:
    """Read shairport's metadata FIFO forever; update app['nowplaying']/['artwork'].

    Robust across reboots, after a failure where the reader stayed attached to the pipe
    but silently parsed nothing until the service was restarted by hand. shairport writes
    a metadata bundle only at specific moments (AirPlay session start / track change) —
    there is no "resend current track" trigger — so a reader that misses the pipe during
    a boot race, or wedges in a plain blocking O_RDONLY reopen loop, can sit blank forever
    through every later track change. The fix is to stay reliably attached:

      * Open the FIFO O_RDWR so *we* are always a writer too. open() then never blocks on
        a missing writer, the reader is attached from process start (before any AirPlay
        session, so it catches the session-start bundle), and it never sees a spurious EOF
        when shairport closes its end between tracks or restarts. Session start/stop is
        tracked via shairport's own `pend`/`pfls` codes, not by EOF.
      * A select()-driven loop (1s tick) keeps the thread responsive and unwedgeable —
        select always returns within the timeout, so the reader can never block forever.
    """
    buf = b""
    pending: dict = {}
    while not app.get("shutdown"):
        fd = None
        try:
            fd = os.open(SHAIRPORT_META, os.O_RDWR)     # O_RDWR: we're always a writer too
            log.info("metadata: reading %s", SHAIRPORT_META)
            while not app.get("shutdown"):
                readable, _, _ = select.select([fd], [], [], 1.0)
                if not readable:
                    continue                            # idle tick; loop stays responsive
                chunk = os.read(fd, 65536)
                if not chunk:                           # EOF — cannot happen while we hold
                    time.sleep(0.2)                     # O_RDWR, but guard against a busy spin
                    continue
                buf += chunk
                while True:
                    m = _ITEM_RE.search(buf)
                    if not m:
                        break
                    buf = buf[m.end():]
                    typ, code = _code(m.group(1)), _code(m.group(2))
                    data = b""
                    if m.group(4):
                        try:
                            data = base64.b64decode(re.sub(rb"\s", b"", m.group(4)))
                        except Exception:  # noqa: BLE001
                            data = b""
                    _handle(app, typ, code, data, pending)
                if len(buf) > 1_000_000:
                    buf = b""                           # safety: never let the buffer run away
        except FileNotFoundError:
            time.sleep(1.0)                             # pipe not created yet; wait and retry
        except Exception as e:  # noqa: BLE001
            log.warning("metadata reader error: %s", e)
            time.sleep(1.0)
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass


def _handle(app: dict, typ: str, code: str, data: bytes, pending: dict) -> None:
    if typ == "core":
        if code == "asar":
            pending["artist"] = data.decode("utf-8", "replace")
        elif code == "minm":
            pending["title"] = data.decode("utf-8", "replace")
        elif code == "asal":
            pending["album"] = data.decode("utf-8", "replace")
    elif typ == "ssnc":
        if code == "mdst":                             # metadata bundle start
            pending.clear()
        elif code == "mden":                           # bundle end → commit
            if pending.get("title") or pending.get("artist"):
                new_key = (pending.get("title"), pending.get("artist"), pending.get("album"))
                if new_key != app.get("track_key"):
                    # New track: drop the old art now (never show stale), then kick off an
                    # iTunes art lookup. If shairport later sends its own PICT, that wins.
                    app["track_key"] = new_key
                    app["artwork"] = None
                    app["art_version"] = app.get("art_version", 0) + 1
                    threading.Thread(target=itunes_art_lookup, args=(app, new_key),
                                     daemon=True).start()
                app["nowplaying"] = {
                    "title": pending.get("title"),
                    "artist": pending.get("artist"),
                    "album": pending.get("album"),
                    "artwork_url": f"/artwork/current?v={app.get('art_version', 0)}",
                    "source": "airplay",
                }
        elif code == "PICT":                           # cover art from the source (preferred)
            if data:
                ct = "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
                _set_art(app, ct, data)
        elif code in ("pend", "pfls"):                 # play end / flush → clear
            app["nowplaying"] = None
            app["artwork"] = None
            app["track_key"] = None


# --------------------------------------------------------------------------- #
# OwnTone (audio router) — outputs + player state
# --------------------------------------------------------------------------- #
async def ot_get(session: ClientSession, path: str):
    async with session.get(OWNTONE_HTTP + path, timeout=4) as r:
        r.raise_for_status()
        return await r.json()


async def build_snapshot(app: web.Application) -> dict:
    session = app["session"]
    snap = {"type": "snapshot", "outputs": [], "player": {}, "now_playing": app["nowplaying"]}
    try:
        outputs = await ot_get(session, "/api/outputs")
        snap["outputs"] = outputs.get("outputs", outputs)
    except Exception:  # noqa: BLE001
        pass
    try:
        snap["player"] = await ot_get(session, "/api/player")
    except Exception:  # noqa: BLE001
        pass
    return snap


# --------------------------------------------------------------------------- #
# Browser fan-out + periodic broadcast
# --------------------------------------------------------------------------- #
class Hub:
    def __init__(self) -> None:
        self.clients: set = set()

    async def broadcast(self, data: dict) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(data)
            except Exception:  # noqa: BLE001
                self.clients.discard(ws)


async def periodic_broadcast(app: web.Application) -> None:
    """Push a fresh snapshot ~every 1.5s — covers metadata changes AND OwnTone changes."""
    while not app.get("shutdown"):
        try:
            await app["hub"].broadcast(await build_snapshot(app))
        except Exception as e:  # noqa: BLE001
            log.warning("broadcast error: %s", e)
        await asyncio.sleep(1.5)


# --------------------------------------------------------------------------- #
# HTTP / WS handlers
# --------------------------------------------------------------------------- #
async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    request.app["hub"].clients.add(ws)
    try:
        await ws.send_json(await build_snapshot(request.app))
        async for _ in ws:
            pass
    finally:
        request.app["hub"].clients.discard(ws)
    return ws


async def outputs_get(request: web.Request) -> web.Response:
    return web.json_response(await ot_get(request.app["session"], "/api/outputs"))


async def outputs_put(request: web.Request) -> web.Response:
    oid = request.match_info["oid"]
    body = await request.read()
    async with request.app["session"].put(
        f"{OWNTONE_HTTP}/api/outputs/{oid}", data=body,
        headers={"Content-Type": "application/json"},
    ) as r:
        return web.Response(status=r.status, text=await r.text(),
                            content_type="application/json")


async def artwork_current(request: web.Request) -> web.Response:
    art = request.app.get("artwork")
    if not art:
        return web.Response(status=204)
    ct, data = art
    return web.Response(body=data, content_type=ct,
                        headers={"Cache-Control": "no-cache"})


async def state(request: web.Request) -> web.Response:
    """Lightweight status for the screen-manager: is anything playing right now?"""
    return web.json_response({"playing": request.app.get("nowplaying") is not None})


async def index(request: web.Request) -> web.Response:
    return web.FileResponse(os.path.join(WEB_DIR, "index.html"))


async def on_startup(app: web.Application) -> None:
    app["session"] = ClientSession()
    app["hub"] = Hub()
    app["shutdown"] = False
    app["nowplaying"] = None
    app["artwork"] = None
    app["art_version"] = 0
    app["track_key"] = None
    app["meta_thread"] = threading.Thread(target=metadata_reader, args=(app,), daemon=True)
    app["meta_thread"].start()
    app["broadcaster"] = asyncio.create_task(periodic_broadcast(app))


async def on_cleanup(app: web.Application) -> None:
    app["shutdown"] = True
    app["broadcaster"].cancel()
    await app["session"].close()


def make_app() -> web.Application:
    app = web.Application()
    app.add_routes([
        web.get("/", index),
        web.get("/ws", ws_handler),
        web.get("/api/outputs", outputs_get),
        web.put("/api/outputs/{oid}", outputs_put),
        web.get("/artwork/current", artwork_current),
        web.get("/state", state),
        web.static("/", WEB_DIR, show_index=False),
    ])
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


if __name__ == "__main__":
    log.info("kiosk on :%d — OwnTone %s, metadata pipe %s", PORT, OWNTONE_HTTP, SHAIRPORT_META)
    web.run_app(make_app(), host="0.0.0.0", port=PORT)
