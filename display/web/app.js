// vinylcast kiosk front-end (phase 2a).
// Renders two views (now-playing + speaker picker) from a live state snapshot the
// backend pushes over /ws. Picker actions go back to the backend's REST proxy.

const $ = (id) => document.getElementById(id);
let state = { outputs: [], now_playing: null, player: {} };
let lastArtUrl = "";

// --- side timer state ---
let SIDE_SECONDS = 22 * 60;   // default LP side ~22 min; tap the timer to change
let sideStart = null;         // epoch ms when the current side started playing
let wasPlaying = false;

// ---------------------------------------------------------------- WebSocket ---
function connect() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => { lastArtUrl = ""; };   // force art to re-load on every (re)connect
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === "snapshot") {
        state = msg;
        render();
      }
    } catch (e) { /* ignore malformed frame */ }
  };
  ws.onclose = () => setTimeout(connect, 2000); // auto-reconnect on the kiosk
  ws.onerror = () => ws.close();
}

// ------------------------------------------------------------------- Render ---
function selectedZones() {
  return (state.outputs || []).filter((o) => o.selected);
}

function render() {
  renderChip();
  renderNowPlaying();
  renderPicker();
}

function renderChip() {
  const sel = selectedZones();
  const chip = $("chip");
  chip.classList.toggle("off", sel.length === 0);
  $("chip-zones").textContent = sel.length
    ? sel.map((o) => o.name).join(" · ")
    : "No speakers selected";
}

function renderNowPlaying() {
  const np = state.now_playing;
  const playing = state.player && state.player.state === "play";
  const art = $("art"), fallback = $("art-fallback");

  updatePlaying(playing);   // drive the side timer off play/stop transitions

  if (np && np.title) {
    $("np-title").textContent = np.title;
    $("np-artist").textContent = np.artist || "";
    $("np-album").textContent = np.album || "";
    $("np-status").textContent =
      np.source === "airplay" ? "AirPlay" : np.source === "vinyl" ? "Vinyl" : "";
    // Side timer is a vinyl-only thing (flip reminder) — hide it for AirPlay etc.
    $("side-timer").classList.toggle("hidden", np.source !== "vinyl");

    // Re-fetch art whenever the (versioned) art URL changes — covers a new track AND
    // late-arriving cover art for the current track. No flicker when art is unchanged.
    if (np.artwork_url && np.artwork_url !== lastArtUrl) {
      lastArtUrl = np.artwork_url;
      art.onload = () => { art.style.display = "block"; fallback.style.display = "none"; };
      art.onerror = () => { art.style.display = "none"; fallback.style.display = "flex"; };
      art.src = np.artwork_url;
    }
  } else {
    lastArtUrl = "";
    art.style.display = "none";
    fallback.style.display = "flex";
    $("side-timer").classList.add("hidden");
    $("np-title").textContent = playing ? "Listening…" : "Drop the needle";
    $("np-artist").textContent = "";
    $("np-album").textContent = "";
    $("np-status").textContent = "";
  }
}

function renderPicker() {
  const zones = $("zones");
  const outs = state.outputs || [];
  $("zones-empty").classList.toggle("hidden", outs.length > 0);
  zones.innerHTML = "";

  for (const o of outs) {
    const tile = document.createElement("div");
    tile.className = "zone" + (o.selected ? " on" : "");

    const row = document.createElement("div");
    row.className = "zone-row";
    const name = document.createElement("div");
    name.className = "zone-name";
    name.textContent = o.name;
    const st = document.createElement("div");
    st.className = "zone-state";
    st.textContent = o.selected ? "On" : "Off";
    row.append(name, st);

    const vol = document.createElement("input");
    vol.type = "range"; vol.min = 0; vol.max = 100; vol.className = "vol";
    vol.value = o.volume ?? 50;
    vol.oninput = (e) => e.stopPropagation();
    vol.onchange = (e) => putOutput(o.id, { volume: Number(e.target.value) });

    // Tap the tile (not the slider) to toggle the zone on/off.
    tile.onclick = (e) => {
      if (e.target === vol) return;
      putOutput(o.id, { selected: !o.selected });
    };

    tile.append(row, vol);
    zones.appendChild(tile);
  }
}

// ------------------------------------------------------------- Side timer ---
// Elapsed time on the current side vs. a typical LP side length, with a flip
// warning near the end. Driven by play/stop; when the ADC is in, the same
// signal that starts playback (needle drop) starts this, and the run-out-groove
// silence detection will stop it (and later flip the HA smart outlet).
function fmt(sec) {
  sec = Math.max(0, Math.floor(sec));
  const m = Math.floor(sec / 60), s = String(sec % 60).padStart(2, "0");
  return `${m}:${s}`;
}

function updatePlaying(playing) {
  if (playing && !wasPlaying) sideStart = Date.now();  // playback started → new side
  if (!playing) sideStart = null;                       // stopped → reset
  wasPlaying = playing;
}

function tickTimer() {
  const box = $("side-timer");
  const sideMin = Math.round(SIDE_SECONDS / 60);
  if (sideStart == null) {
    box.classList.remove("flip-soon");
    $("st-elapsed").textContent = "0:00";
    $("st-fill").style.width = "0%";
    $("st-flip").textContent = "";
    $("st-sub").textContent = `side ~${sideMin} min · not playing`;
    return;
  }
  const elapsed = (Date.now() - sideStart) / 1000;
  const remaining = SIDE_SECONDS - elapsed;
  $("st-elapsed").textContent = fmt(elapsed);
  $("st-fill").style.width = Math.min(100, (elapsed / SIDE_SECONDS) * 100) + "%";
  if (remaining > 120) {
    box.classList.remove("flip-soon");
    $("st-flip").textContent = "";
    $("st-sub").textContent = `~${fmt(remaining)} left on this ~${sideMin} min side`;
  } else if (remaining > 0) {
    box.classList.add("flip-soon");
    $("st-flip").textContent = "FLIP SOON";
    $("st-sub").textContent = `~${fmt(remaining)} left — get ready to flip`;
  } else {
    box.classList.add("flip-soon");
    $("st-flip").textContent = "FLIP IT";
    $("st-sub").textContent = `side likely over (${fmt(-remaining)} into run-out)`;
  }
}

// ------------------------------------------------------------------ Actions ---
async function putOutput(id, body) {
  try {
    await fetch(`/api/outputs/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    // The backend will push a fresh snapshot via /ws; optimistic tweak meanwhile:
    const o = state.outputs.find((x) => x.id === id);
    if (o) Object.assign(o, body);
    render();
  } catch (e) { /* kiosk: ignore, next snapshot corrects it */ }
}

function showView(which) {
  $("nowplaying").classList.toggle("hidden", which !== "nowplaying");
  $("picker").classList.toggle("hidden", which !== "picker");
}

// ---------------------------------------------------------------------- Init ---
$("chip").onclick = () => showView("picker");
$("done").onclick = () => showView("nowplaying");
// Tap the timer to cycle common side lengths (match your record).
$("side-timer").onclick = () => {
  const opts = [15, 18, 20, 22, 25, 30];
  const cur = Math.round(SIDE_SECONDS / 60);
  const i = opts.indexOf(cur);
  SIDE_SECONDS = opts[(i + 1) % opts.length] * 60;
  tickTimer();
};
showView("nowplaying");
render();
setInterval(tickTimer, 1000);
tickTimer();
connect();
