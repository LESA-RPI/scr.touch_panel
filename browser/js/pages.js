// Page markup. Pure functions of the store and the route; main.js wires events.
import { store, busy } from './api.js';
import { esc, icon, ago, num, roomTime, weatherIcon } from './ui.js';

export const NAV = [
  ['home', 'home', 'Home'],
  ['lights', 'lighting', 'Lights'],
  ['guide', 'guide', 'Guide'],
  ['settings', 'tools', 'Settings'],
];
const LIGHT_TABS = [['white', 'White light'], ['scenes', 'Scenes'], ['programmes', 'Programmes'], ['channels', 'Channels']];
const SETTINGS = [['screen', 'screen', 'Screen'], ['appearance', 'appearance', 'Appearance'], ['weather', 'clock', 'Date & weather'], ['system', 'system', 'System'], ['about', 'about', 'About']];
const IDLE = [[0, 'Off'], [60, '1 minute'], [300, '5 minutes'], [900, '15 minutes']];

const S = () => store.state || {};
const L = () => S().lights || {};
const content = () => store.content || {};

// ---------- Shared state wording ----------
export function status() {
  const s = S(), lights = L(), recovery = s.lighting_recovery || {};
  if (!store.reachable) return { key: 'off', label: 'Website offline', detail: "This page can't reach the touch panel right now. It reconnects by itself." };
  if (!s.available) return { key: 'warn', label: 'Panel unavailable', detail: s.detail || 'The touch panel is not accepting website controls.' };
  if (s.mode === 'original') return { key: 'off', label: 'Legacy open', detail: 'The touch panel is showing the original (Legacy) controls. Return panel to Home to close Legacy and restore lighting controls.' };
  if (store.pending || store.awaiting || s.busy || lights.state === 'applying') return { key: 'busy', label: 'Working…', detail: 'A change is on its way. Other lighting buttons wait until it is confirmed.' };
  if (lights.state === 'connecting') return { key: 'busy', label: 'Connecting…', detail: 'The panel is reading the lights. Controls appear in a moment.' };
  if (recovery.write_blocked || lights.state === 'failed') return { key: 'warn', label: 'Check needed', detail: recovery.detail || 'A change could not be confirmed. Press Check connection to confirm current settings.' };
  if (lights.state === 'disconnected') return { key: 'warn', label: 'Lighting offline', detail: 'The panel cannot reach the lighting service. Check connection tries again without changing anything.' };
  if (s.can_control) return { key: 'ready', label: 'Ready', detail: 'Lighting controls work on the panel and here.' };
  return { key: 'warn', label: 'Not ready', detail: recovery.detail || 'Lighting controls are paused.' };
}

export const canLight = () => Boolean(store.reachable && S().can_control && !busy());

function lightsNow() {
  const lights = L();
  if (lights.confirmed_power === 'off' || lights.scene === 'Off') return 'Lights are off';
  if (lights.confirmed_power !== 'on') return 'Lights not confirmed yet';
  if (lights.scene) return `Lights are on · ${lights.scene}`;
  return `Lights are on · ${num(lights.cct)} K, level ${num(lights.intensity)}`;
}

export function readback() {
  const pending = store.pending, awaiting = store.awaiting, st = status();
  let text, warn = false;
  if (pending) text = pending.status === 'unknown' ? `<b>Waiting to hear back about ${esc(pending.label)}…</b> Don't press it again.` : `<b>Sending ${esc(pending.label)}…</b>`;
  else if (awaiting) text = `<b>${esc(awaiting.label)}</b> sent · waiting for the lights to confirm…`;
  else if (st.key === 'ready' || st.key === 'busy') text = `<b>${lightsNow()}</b> · confirmed ${ago(L().confirmed_age_s)}`;
  else {
    warn = st.key === 'warn';
    text = `<b>${esc(st.label)}.</b> ${esc(st.detail)} <span class="muted">Last known: ${lightsNow().toLowerCase()}, ${ago(L().confirmed_age_s)}.</span>`;
  }
  return `<p class="readback ${warn ? 'warn' : ''}" role="status">${text}</p>`;
}

export function chip() {
  const st = status();
  return `<button class="chip" data-sheet="status" aria-label="Room connection: ${esc(st.label)}"><span class="dot ${st.key}"></span>${esc(st.label)}</button>`;
}

const disabled = (on) => (on ? '' : 'disabled');

// ---------- Home ----------
function weatherBlock(compact) {
  const w = S().weather;
  if (!w) return '<p class="muted">Weather unavailable right now.</p>';
  const f = S().preferences?.temperature !== 'c';
  const t = (key) => (w[key + (f ? '_f' : '_c')] == null ? '–' : Math.round(w[key + (f ? '_f' : '_c')]) + '°');
  return `<div class="wx">${icon(weatherIcon(w), 'wx-icon')}<span class="temp">${t('temperature')}</span>
      <div><div class="cond">${esc(w.condition || '')}</div><div class="muted small">Feels like ${t('feels_like')}</div></div></div>
    <p class="facts"><span>High <b>${t('high')}</b></span><span>Low <b>${t('low')}</b></span><span>Rain today <b>${w.rain_chance == null ? '–' : Math.round(w.rain_chance) + '%'}</b></span></p>
    ${compact ? '' : `<p class="muted small">Sunrise ${roomTimeOf(w.sunrise)} · Sunset ${roomTimeOf(w.sunset)} · updated ${ago(S().weather_age_s)}</p>`}`;
}
function roomTimeOf(iso) {
  if (!iso) return '–';
  const [h, m] = iso.slice(11, 16).split(':').map(Number);
  if (S().preferences?.clock === '24') return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, '0')} ${h < 12 ? 'AM' : 'PM'}`;
}

function blindsBlock() {
  const s = S(), blinds = s.blinds || {}, prefs = s.preferences || {};
  if (prefs.blinds_display === 'hidden') return '';
  let body;
  if (!blinds.connected) body = '<p class="muted">Blind controls are not connected right now.</p>';
  else if (!blinds.enabled) body = '<p class="muted">Blinds are locked so they are not moved by accident. <a class="link" href="#settings/screen">Unlock in Settings ›</a></p>';
  else {
    const ok = blinds.available && store.reachable && !busy();
    body = `<div class="blinds">${(content().blind_actions || [['lift', 'Lift blinds'], ['open', 'Open slats'], ['close', 'Close & lower']])
      .map(([name, label]) => `<button class="btn" ${disabled(ok)} data-cmd="blind" data-name="${name}" data-label="${esc(label)}">${esc(label)}</button>`).join('')}</div>
      <p class="muted small">Moves the whole room's blinds. The panel cannot see their actual position.</p>`;
  }
  return `<section class="stack"><h2>Blinds</h2>${body}</section>`;
}

export function home(device) {
  const ok = canLight(), s = S();
  const time = device === 'phone' ? '' : `<div class="time">${roomTime(s, { hour: 'numeric', minute: '2-digit', hour12: s.preferences?.clock !== '24' })}</div>
      <div class="date">${roomTime(s, { weekday: 'long', month: 'long', day: 'numeric' })}</div>`;
  const statusRow = device === 'desktop' ? `<div class="status-row">
      <button data-sheet="status"><span class="muted small">Lighting</span><b>${esc(status().label)}</b><span class="muted small">Confirmed ${ago(L().confirmed_age_s)}</span></button>
      <a href="#settings/system"><span class="muted small">Room services</span><b>${diagSummary()}</b><span class="muted small">Checked ${ago(s.room_diagnostics?.age_s)}</span></a>
      <a href="#settings/system"><span class="muted small">Touch panel</span><b class="${powerWarn() ? 'warn-text' : ''}">${powerWarn() ? 'Power supply warning' : 'Healthy'}</b><span class="muted small">${esc(s.health?.power || '')}</span></a></div>` : '';
  const pressed = (label) => (store.pending?.label === label || store.awaiting?.label === label ? 'sending' : '');
  const note = (label) => (store.pending?.label === label ? 'Sending…' : store.awaiting?.label === label ? 'Confirming…' : '');
  return `<section class="home">
    <div class="stack">
      <h2>Lights</h2>
      <div class="pair">
        <button class="btn big ${pressed('Lights on')}" ${disabled(ok)} data-cmd="on" data-label="Lights on">${icon('lighting')}Lights on<span class="note">${note('Lights on')}</span></button>
        <button class="btn big ${pressed('Lights off')}" ${disabled(ok)} data-cmd="off" data-label="Lights off">${icon('off')}Lights off<span class="note">${note('Lights off')}</span></button>
      </div>
      ${readback()}
      <p><a class="link" href="#lights/white">White light, scenes and channels ›</a></p>
      ${blindsBlock()}
    </div>
    <aside class="clock">
      <div class="muted small">Troy, NY</div>${time}${weatherBlock(device === 'phone')}
    </aside>
    ${statusRow}
  </section>`;
}
function diagSummary() {
  const services = S().room_diagnostics?.services || [];
  if (!services.length) return 'Not checked';
  return `${services.filter((x) => x.state === 'listed').length} of ${services.length} listed`;
}
export const powerWarn = () => Boolean(S().health?.power_warning);

// ---------- Lights ----------
function slider(key, label, value, min, max, step, unit) {
  return `<div class="card slider-card">
    <div class="slider-head"><span class="muted small">${label}</span><span class="val" data-val="${key}">${num(value)}</span><span class="unit">${unit}</span></div>
    <div class="slider-row">
      <button class="btn step" ${disabled(canLight())} data-step="${key}" data-delta="${-step}" aria-label="Lower ${label}">−</button>
      <input type="range" min="${min}" max="${max}" step="${step}" value="${value}" data-range="${key}" aria-label="${label}" ${disabled(canLight())}>
      <button class="btn step" ${disabled(canLight())} data-step="${key}" data-delta="${step}" aria-label="Raise ${label}">+</button>
    </div>
    <div class="minmax"><span>${num(min)}${unit === 'K' ? ' K warm' : ''}</span><span>${num(max)}${unit === 'K' ? ' K cool' : ''}</span></div></div>`;
}
export function lights(tab) {
  const lights = L(), c = content(), ok = canLight();
  const caps = lights.capabilities || {};
  let body;
  if (tab === 'scenes') {
    const scenes = [...(c.scenes || [])];
    if (caps.gradient && c.gradient) scenes.push(c.gradient);
    body = `<div class="scenes">${scenes.map((scene) => {
      const mix = c.presets?.[scene.id] || [70, 30, 10, 40, 60, 100, 50, 30];
      const current = lights.scene === scene.id && !busy();
      const label = scene.id === 'Gradient' ? 'Gradient' : scene.label + ' scene';
      const cmd = scene.id === 'Gradient' ? 'data-cmd="gradient"' : `data-cmd="preset" data-name="${esc(scene.id)}"`;
      return `<button class="scene ${store.pending?.label === label ? 'sending' : ''}" ${disabled(ok)} ${cmd} data-label="${esc(label)}">
        <span class="top"><span class="name">${esc(scene.label)}</span><span class="state ${current ? 'current' : ''}">${current ? 'Current' : store.pending?.label === label ? 'Sending…' : ''}</span></span>
        <span class="muted small">${esc(scene.detail)}</span>
        <span class="mix">${mix.map((v, i) => `<i data-h="${Math.max(4, v)}%" data-bg="${c.channels?.[i]?.colour || '#888'}"></i>`).join('')}</span></button>`;
    }).join('')}</div><p class="muted small">Tap a scene to apply it to the whole room. The bars show its eight-channel mixture.</p>`;
  } else if (tab === 'programmes') {
    if (!caps.programmes) body = `<p class="muted">${esc(c.unavailable_lighting || 'Programmes are not available on this panel.')}</p>`;
    else {
      const start = ok && S().can_programme !== false;
      body = `<div class="programmes">${(c.programmes || []).map((p) => `<div class="card stack"><h3>${esc(p.label)}</h3><p class="muted small">${esc(p.detail)}</p>
        <div><button class="btn primary" ${disabled(start)} data-cmd="programme" data-name="${esc(p.id)}" data-label="Start ${esc(p.label)}">${icon('play')}Start ${esc(p.label)}</button></div></div>`).join('')}</div>
        <div class="row"><button class="btn quiet" ${disabled(store.reachable && !busy() && S().mode !== 'original')} data-cmd="programme" data-name="Stop" data-label="Stop programmes">${icon('circle-slash')}Stop programmes</button>
        <span class="muted small">${lights.programme ? `${esc(lights.programme)} was requested. The room server runs it; any other light change stops it.` : 'No programme requested. Any other light change stops a running programme.'}</span></div>`;
    }
  } else if (tab === 'channels') {
    const values = lights.channels || Array(8).fill(0);
    body = `<div class="card channels">${(c.channels || []).map((ch, i) => `<label class="channel"><span class="swatch" data-bg="${ch.colour}"></span><span>${esc(ch.label)}</span>
      <input type="range" min="0" max="100" step="1" value="${values[i] ?? 0}" data-chan="${i}" aria-label="${esc(ch.label)}" ${disabled(ok)}><span class="pc" data-val="chan${i}">${values[i] ?? 0}%</span></label>`).join('')}</div>
      <p class="muted small">Changes apply when you let go. Values are drive levels, not measured brightness.</p>`;
  } else {
    const warm = c.previous_on || { arguments: { cct: 3500, intensity: 1000 } };
    body = `${slider('cct', 'Colour temperature', lights.cct ?? 3500, 1600, 10000, 100, 'K')}
      ${slider('intensity', 'Light level', lights.intensity ?? 1000, 0, 1900, 50, 'of 1,900')}
      <div class="row wrap"><button class="btn primary" ${disabled(ok)} data-cmd="cct" data-cct="${warm.arguments.cct}" data-intensity="${warm.arguments.intensity}" data-label="Warm white">Apply Warm white</button>
      <span class="muted small">3,500 K at level 1,000 (the old “On”). Sliders apply when you let go.</span></div>`;
  }
  return `<nav class="seg" aria-label="Lighting">${LIGHT_TABS.map(([id, label]) => `<a href="#lights/${id}" ${tab === id ? 'aria-current="page"' : ''}>${label}</a>`).join('')}</nav>
    <div class="lights-body">${body}<div class="foot">${readback()}</div></div>`;
}

// ---------- Guide ----------
const topics = () => content().guide || [];
const PAGE_ROUTES = { lighting: '#lights/white', home: '#home', screen: '#settings/screen', system: '#settings/system', clock: '#settings/weather' };
function ceilingMap(family) {
  const map = content().ceiling_map;
  if (!map) return '';
  const fam = map.families.find((f) => f.id === family) || map.families[0];
  const C = 100, cols = map.grid.columns, rows = map.grid.rows, W = cols * C, H = rows * C;
  const X = (cell, u) => (cell[0] - 1 + u) * C, Y = (cell, v) => (rows - (cell[1] - 1) - v) * C;
  let grid = '', fx = '', dots = '';
  for (let r = 0; r <= rows; r++) grid += `<line x1="0" y1="${r * C}" x2="${W}" y2="${r * C}"/>`;
  for (let c = 0; c <= cols; c++) grid += `<line x1="${c * C}" y1="0" x2="${c * C}" y2="${H}"/>`;
  for (const f of map.fixtures || []) for (const p of f.positions) {
    const x = X(p.cell, p.u), y = Y(p.cell, p.v);
    if (f.kind === 'troffer') fx += `<rect class="fx-troffer" x="${x - 34}" y="${y - 34}" width="68" height="68" rx="4"/>`;
    else if (f.kind === 'hvac') fx += `<g class="fx-line"><rect x="${x - 22}" y="${y - 22}" width="44" height="44"/><line x1="${x - 14}" y1="${y - 8}" x2="${x + 14}" y2="${y - 8}"/><line x1="${x - 14}" y1="${y + 8}" x2="${x + 14}" y2="${y + 8}"/></g>`;
    else fx += `<g class="fx-line"><line x1="${x - 9}" y1="${y - 9}" x2="${x + 9}" y2="${y + 9}"/><line x1="${x - 9}" y1="${y + 9}" x2="${x + 9}" y2="${y - 9}"/></g>`;
  }
  const dark = document.documentElement.dataset.theme === 'dark';
  fam.positions.forEach((p, i) => {
    const x = X(p.cell, p.u), y = Y(p.cell, p.v), sel = mapMarker === `${fam.id}:${i}`;
    dots += `<circle class="hit" cx="${x}" cy="${y}" r="44" data-marker="${fam.id}:${i}"/><circle class="${sel ? 'sel' : ''}" cx="${x}" cy="${y}" r="${sel ? 20 : 13}" fill="${fam.colours[dark ? 'dark' : 'light']}" data-marker="${fam.id}:${i}"/>`;
  });
  const portrait = matchMedia('(max-width: 760px)').matches;
  let labels = '', body, box;
  if (portrait) {
    const Lm = 64, T = 46;
    for (let r = 1; r <= cols; r++) labels += `<text x="${Lm - 12}" y="${T + (r - 0.5) * C + 10}" text-anchor="end">R${r}</text>`;
    for (let c = 1; c <= rows; c++) labels += `<text x="${Lm + (c - 0.5) * C}" y="${T - 14}" text-anchor="middle">C${c}</text>`;
    body = `<g transform="translate(${Lm + H},${T}) rotate(90)"><g class="grid">${grid}</g>${fx}${dots}</g>`;
    box = `0 0 ${Lm + H + 6} ${T + W + 6}`;
  } else {
    const Lm = 56;
    for (let c = 1; c <= cols; c++) labels += `<text x="${Lm + (c - 0.5) * C}" y="${H + 38}" text-anchor="middle">R${c}</text>`;
    for (let r = 1; r <= rows; r++) labels += `<text x="${Lm - 12}" y="${(rows - r + 0.5) * C + 10}" text-anchor="end">C${r}</text>`;
    body = `<g transform="translate(${Lm},0)"><g class="grid">${grid}</g>${fx}${dots}</g>`;
    box = `0 -6 ${Lm + W + 6} ${H + 56}`;
  }
  let info = `<b>${esc(fam.label)}</b> · ${fam.positions.length} ceiling positions. ${esc(fam.description)}`;
  if (mapMarker?.startsWith(fam.id + ':')) {
    const p = fam.positions[Number(mapMarker.split(':')[1])];
    info = `<b>${esc(fam.label)} · R${p.cell[0]} C${p.cell[1]}</b> · reference ${esc(p.reference_id)}. ${esc(fam.description)}`;
  }
  return `<nav class="seg" aria-label="Sensor family">${map.families.map((f) => `<button data-family="${f.id}" ${f.id === fam.id ? 'aria-current="page"' : ''}><span class="swatch" data-bg="${f.colours[dark ? 'dark' : 'light']}"></span>${esc(f.label)}</button>`).join('')}</nav>
    <svg class="map" viewBox="${box}" role="img" aria-label="Ceiling sensor map">${body}<g class="labels">${labels}</g></svg>
    <p>${info}</p>
    <p class="muted small">${portrait ? 'Turned to fit your phone: door on the left, windows at the bottom.' : 'Top view: door at the bottom, windows on the right.'} Reference positions, not live status. Faint squares: light troffers · slatted: HVAC · crosses: sprinklers.</p>`;
}
export let mapMarker = null;
export let mapFamily = 'combo';
export function setMap(family, marker) {
  if (family !== undefined) mapFamily = family;
  mapMarker = marker ?? null;
}
function topicBody(index) {
  const t = topics()[index];
  if (!t) return '<p class="muted">Topic not found.</p>';
  if (t.title === 'Ceiling map') return ceilingMap(mapFamily);
  const paragraphs = String(t.text || '').split(/\n\s*\n/).map((p) => `<p>${esc(p)}</p>`).join('');
  let visual = '';
  if (t.visual === 'channels') visual = `<div class="chanbar">${(content().channels || []).map((ch) => `<div><i data-bg="${ch.colour}"></i>${esc(ch.label)}</div>`).join('')}</div>
    <div class="row wrap"><button class="btn" ${disabled(canLight())} data-cmd="on" data-label="Lights on">Try it: Lights on</button>${L().capabilities?.gradient ? `<button class="btn" ${disabled(canLight())} data-cmd="gradient" data-label="Gradient">Try it: Gradient</button>` : ''}</div>
    <p class="muted small">These buttons change the room lights.</p>`;
  const links = (t.links || []).filter((l) => PAGE_ROUTES[l.page]).map((l) => `<a class="link" href="${PAGE_ROUTES[l.page]}">${esc(l.label.replace(/^Open /, ''))} ›</a>`).join(' ');
  return `${paragraphs}${visual}${links ? `<p class="row wrap">${links}</p>` : ''}`;
}
export function guide(index, device) {
  const sections = content().guide_sections || [['Room tour', 'room'], ['Control help', 'controls']];
  const list = sections.map(([title, id]) => `<span class="side-head">${esc(title === 'Control help' ? 'Using the controls' : title)}</span>${topics()
    .map((t, i) => (t.section === id ? `<a href="#guide/${i}" ${index === i ? 'aria-current="page"' : ''}>${icon(t.icon || 'guide')}<span>${esc(t.title)}</span></a>` : ''))
    .join('')}`).join('');
  const welcome = `<div class="stack"><h2>Welcome</h2><p>The Smart Conference Room is a research space for lighting and sensing. Pick a topic to explore the room or learn the controls. Reading the guide never changes anything in the room.</p>
    <p class="muted">Room Wi-Fi: <b>${esc(S().network_name || content().network_name || 'SCR_AP')}</b>. Ask the room host if you need access.</p></div>`;
  const detail = index == null ? welcome : `<article class="topic">${device === 'phone' ? '<a class="link" href="#guide">‹ All topics</a>' : ''}<h2>${icon(topics()[index]?.icon || 'guide')}${esc(topics()[index]?.title || '')}</h2>${topicBody(index)}</article>`;
  if (device === 'phone') return index == null ? `<nav class="side list">${list}</nav>${welcome}` : detail;
  return `<div class="split"><nav class="side" aria-label="Guide topics">${list}</nav><div class="detail">${detail}</div></div>`;
}

// ---------- Settings ----------
function pref(key, label, value, hint) {
  return `<button class="pref" data-pick="${key}"><span class="t">${label}${hint ? `<small>${hint}</small>` : ''}</span><span class="v">${esc(value)}</span>${icon('chevron-right', 'chev')}</button>`;
}
export function settings(cat, device) {
  const s = S(), p = s.preferences || {}, blinds = s.blinds || {};
  let d;
  if (cat === 'appearance') {
    d = `<h2>Appearance</h2><p class="muted small">These change the touch panel. This website follows your own device's light or dark setting.</p>
      ${pref('theme', 'Panel theme', { auto: 'Automatic', light: 'Light', dark: 'Dark' }[p.theme] || p.theme, 'Automatic switches between light by day and dark at night')}
      ${pref('clock', 'Clock', p.clock === '24' ? '24-hour' : '12-hour')}
      ${pref('temperature', 'Temperature', p.temperature === 'c' ? '°C' : '°F')}`;
  } else if (cat === 'weather') {
    const w = s.weather || {};
    d = `<h2>Date & weather</h2><dl class="facts2"><dt>Room time</dt><dd>${roomTime(s, { weekday: 'long', month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</dd>
      <dt>Location</dt><dd>Troy, NY</dd><dt>Conditions</dt><dd>${esc(w.condition || '–')}</dd><dt>Forecast time</dt><dd>${esc((w.model_time || '–').replace('T', ' '))}</dd>
      <dt>Updated</dt><dd>${ago(s.weather_age_s)}</dd><dt>Source</dt><dd>Open-Meteo</dd></dl>`;
  } else if (cat === 'system') {
    const diag = s.room_diagnostics || {}, h = s.health || {};
    const power = s.power || {};
    d = `<h2>System</h2>
      <div class="list">
        <button data-sheet="status">${icon('system')}<span class="t">Room connection<small>Check connection, what each state means</small></span><span class="v">${esc(status().label)}</span>${icon('chevron-right', 'chev')}</button>
      </div>
      <section class="stack"><div class="row"><h3>Room services</h3><span class="spacer"></span><button class="btn quiet small-btn" ${disabled(diag.can_check && store.reachable && !store.pending)} data-cmd="refresh_status" data-label="Room services check">${diag.checking ? 'Checking…' : 'Check now'}</button></div>
        <p class="muted small">${esc(diag.detail || '')} Checked ${ago(diag.age_s)}.</p>
        <div class="services">${(diag.services || []).map((x) => `<span class="${x.state === 'listed' ? '' : 'warn-text'}">${esc(x.name)} <b>${x.state === 'listed' ? 'listed' : 'missing'}</b></span>`).join('')}</div></section>
      <section class="stack"><h3>This panel</h3><dl class="facts2">
        <dt>Power supply</dt><dd class="${powerWarn() ? 'warn-text' : ''}">${esc(h.power || '–')}</dd>
        <dt>Processor</dt><dd>${h.temperature == null ? '–' : Math.round(h.temperature) + ' °C'}</dd>
        <dt>Memory free</dt><dd>${h.ram_available == null ? '–' : `${h.ram_available} of ${h.ram_total} MB`}</dd>
        <dt>Disk free</dt><dd>${h.disk_available == null ? '–' : h.disk_available.toFixed(1) + ' GB'}</dd>
        <dt>Running for</dt><dd>${h.uptime == null ? '–' : h.uptime.toFixed(1) + ' days'}</dd></dl></section>
      <section class="stack"><h3>Maintenance commands</h3><p class="muted small">Steps for staff. They are shown and copied here, never run by the website.</p>
        <div class="list">${(content().help || []).filter((x) => x.reference?.steps?.length).map((x) => `<a href="#settings/help/${encodeURIComponent(x.title)}">${icon('system')}<span class="t">${esc(x.title)}<small>${esc(x.reference.machine)} · ${x.reference.steps.length} step${x.reference.steps.length > 1 ? 's' : ''}</small></span>${icon('chevron-right', 'chev')}</a>`).join('')}</div></section>
      <section class="stack"><h3>Touch panel power</h3><div class="row wrap"><button class="btn quiet" ${disabled(power.available && power.actions?.reboot && store.reachable && !busy())} data-sheet="reboot">Restart touch panel</button>
        <span class="muted small">Shut down is only available on the panel itself. ${esc(power.phase !== 'ready' ? power.message || '' : '')}</span></div></section>`;
  } else if (cat?.startsWith('help/')) {
    const topic = (content().help || []).find((x) => x.title === decodeURIComponent(cat.slice(5)));
    d = topic ? `<a class="link" href="#settings/system">‹ System</a><h2>${esc(topic.title)}</h2><p class="muted">${esc(topic.text)}</p>
      <p class="small">On: <b>${esc(topic.reference.machine)}</b> · ${esc(topic.reference.effect)}</p>
      ${topic.reference.steps.map((step, i) => `<section class="card stack"><h3>${i + 1}. ${esc(step.title)}</h3><p class="small">${esc(step.why)}</p>
        <pre><code>${esc(step.commands)}</code></pre><div class="row wrap"><button class="btn quiet small-btn" data-copy="${esc(step.commands)}">Copy</button><span class="muted small">Expect: ${esc(step.expect)}</span></div></section>`).join('')}
      ${topic.reference.documentation ? `<p><a class="link" href="${esc(topic.reference.documentation.url)}" target="_blank" rel="noopener">${esc(topic.reference.documentation.label)} ›</a></p>` : ''}` : '<p>Topic not found.</p>';
  } else if (cat === 'about') {
    d = `<h2>About</h2><dl class="facts2"><dt>Version</dt><dd>${esc(s.app_version || content().app_version || '–')}</dd><dt>Build</dt><dd>${esc(s.build_commit || '–')}</dd>
      <dt>Touch interface</dt><dd>Diyanko Bhowmik</dd><dt>Room Wi-Fi</dt><dd>${esc(s.network_name || 'SCR_AP')}</dd></dl>
      <p class="muted small">LESA Smart Conference Room. Icons adapted from Lucide. Original contributors are in the project's Git history.</p>`;
  } else {
    d = `<h2>Screen</h2>
      ${pref('idle', 'Screen saver', (IDLE.find(([v]) => v === p.idle) || [0, 'Off'])[1] === 'Off' ? 'Off' : 'After ' + (IDLE.find(([v]) => v === p.idle) || [0, ''])[1], 'Clock and weather after the panel is left alone')}
      ${pref('blinds_display', 'Blind buttons on Home', p.blinds_display === 'hidden' ? 'Hidden' : 'Shown')}
      ${blinds.connected ? pref('blinds_enabled', 'Blind movement', p.blinds_enabled ? 'Unlocked' : 'Locked', 'Locked keeps the blind buttons from moving anything') : '<p class="muted small">Blind movement can be unlocked once the blind controls are connected.</p>'}`;
  }
  const side = `<nav class="side" aria-label="Settings">${SETTINGS.map(([id, ic, label]) => `<a href="#settings/${id}" ${(cat || 'screen').split('/')[0] === id || (id === 'system' && cat?.startsWith('help/')) ? 'aria-current="page"' : ''}>${icon(ic)}<span>${label}</span></a>`).join('')}</nav>`;
  if (device === 'phone') return cat ? `<a class="link" href="#settings">‹ Settings</a><div class="detail">${d}</div>` : side.replace('class="side"', 'class="side list"');
  return `<div class="split">${side}<div class="detail">${d}</div></div>`;
}

// ---------- Sheets ----------
export function sheet(name) {
  const s = S(), p = s.preferences || {}, st = status();
  if (name === 'status') {
    const recovery = s.lighting_recovery || {};
    const canCheck = store.reachable && recovery.can_check && !store.pending;
    return `<h2>Room connection</h2><p class="row"><span class="dot ${st.key}"></span><b>${esc(st.label)}</b></p><p>${esc(st.detail)}</p>
      <dl class="facts2"><dt>Lights</dt><dd>${lightsNow()}</dd><dt>Confirmed</dt><dd>${ago(L().confirmed_age_s)}</dd>
      <dt>Blinds</dt><dd>${esc(s.blinds?.reason || '–')}</dd><dt>Programme</dt><dd>${esc(L().programme ? L().programme + ' requested' : 'None requested')}</dd></dl>
      <button class="btn" ${disabled(canCheck)} data-cmd="check_connection" data-label="Connection check">${icon('system')}Check connection</button>
      <p class="muted small">${recovery.write_blocked ? 'Stops Sun/Circ, then confirms stable light settings. Current light levels are kept.' : 'Reads the current light settings without changing them.'}</p>
      ${s.mode === 'original' ? '<button class="btn quiet" data-cmd="home" data-label="Return panel to Home">Return the touch panel to Home</button>' : ''}`;
  }
  if (name === 'reboot') {
    return `<h2>Restart the touch panel?</h2><p>The panel and this website go offline for about two minutes, then come back by themselves. Room lights stay as they are.</p>
      <button class="btn" data-cmd="power" data-operation="reboot" data-label="Restart">Restart touch panel</button>`;
  }
  const choices = {
    idle: ['Screen saver', IDLE, p.idle],
    theme: ['Panel theme', [['auto', 'Automatic'], ['light', 'Light'], ['dark', 'Dark']], p.theme],
    clock: ['Clock', [['12', '12-hour'], ['24', '24-hour']], p.clock],
    temperature: ['Temperature', [['f', '°F'], ['c', '°C']], p.temperature],
    blinds_display: ['Blind buttons on Home', [['disabled', 'Shown'], ['hidden', 'Hidden']], p.blinds_display],
    blinds_enabled: ['Blind movement', [[false, 'Locked'], [true, 'Unlocked']], p.blinds_enabled],
  }[name];
  if (!choices) return '';
  const [title, options, current] = choices;
  return `<h2>${title}</h2><div class="list">${options.map(([value, label]) => `<button data-pref="${name}" data-value='${JSON.stringify(value)}' data-label="${esc(title)}: ${esc(label)}">
      <span class="t">${esc(label)}</span>${value === current ? '<b>Current</b>' : ''}</button>`).join('')}</div>
    <p class="muted small">Saved on the touch panel. Changing it never moves equipment.</p>`;
}
