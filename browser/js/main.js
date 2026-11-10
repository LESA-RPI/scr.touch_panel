// Routing, rendering and input. Pages are pure markup; commands go through api.send.
import { store, onChange, poll, send, loadContent, busy, notify } from './api.js';
import { esc, icon, applyStyles, progress, num, morph } from './ui.js';
import * as pages from './pages.js';

const $ = (id) => document.getElementById(id);
const phone = matchMedia('(max-width: 760px)');
const dark = matchMedia('(prefers-color-scheme: dark)');
let sheetName = null;
let interacting = false; // a finger is down: don't redraw under it
let lastHtml = '';

function route() {
  const [page = 'home', ...rest] = location.hash.replace(/^#/, '').split('/');
  return { page: ['home', 'lights', 'guide', 'settings'].includes(page) ? page : 'home', rest: rest.join('/') };
}
const device = () => (phone.matches ? 'phone' : innerWidth >= 1200 ? 'desktop' : 'tablet');

const preview = new URLSearchParams(location.search); // ?theme=dark|light for screenshots
function render(force = false) {
  document.documentElement.dataset.theme = preview.get('theme') || (dark.matches ? 'dark' : 'light');
  if (interacting && !force) return;
  const { page, rest } = route();
  const titles = { home: 'Smart Conference Room', lights: 'Lights', guide: 'Guide', settings: 'Settings' };
  let body;
  if (!store.content && !store.state) body = '<p class="muted">Connecting to the touch panel…</p>';
  else if (page === 'lights') body = pages.lights(rest || 'white');
  else if (page === 'guide') body = pages.guide(rest === '' ? null : Number(rest), device());
  else if (page === 'settings') body = pages.settings(rest || (device() === 'phone' ? '' : 'screen'), device());
  else body = pages.home(device());
  const legacy = store.state?.mode === 'original' && store.reachable
    ? `<div class="banner"><p>The touch panel is showing Legacy controls. Lighting here is paused.</p><button class="btn quiet" data-cmd="home" data-label="Return panel to Home" ${busy() ? 'disabled' : ''}>Return panel to Home</button></div>` : '';
  const notice = store.notice ? `<p class="notice ${store.notice.warn ? 'warn' : ''}" role="alert">${esc(store.notice.text)} <button class="link" data-dismiss>Dismiss</button></p>` : '';
  const html = `${legacy}${notice}<header class="pagehead"><h1>${titles[page]}</h1>${pages.chip()}</header>${body}`;
  if (html !== lastHtml) {
    const main = $('page');
    morph(main, html);
    applyStyles(main);
    lastHtml = html;
  }
  document.querySelectorAll('[data-nav]').forEach((a) => (a.ariaCurrent = a.dataset.nav === page ? 'page' : null));
  const sheet = $('sheet');
  if (sheetName) {
    const markup = pages.sheet(sheetName);
    if (sheet.dataset.html !== markup) {
      morph(sheet.querySelector('.sheet-body'), markup);
      applyStyles(sheet);
      sheet.dataset.html = markup;
    }
    if (!sheet.open) sheet.showModal();
  } else if (sheet.open) sheet.close();
}

function nav() {
  const items = pages.NAV.map(([id, ic, label]) => `<a href="#${id}" data-nav="${id}">${icon(ic)}<span>${label}</span></a>`).join('');
  $('rail').innerHTML = `<a class="brand" href="#home"><img src="/logo.jpg" alt="LESA"></a>${items}`;
  $('tabbar').innerHTML = items;
}

// ---------- Input ----------
document.addEventListener('click', async (event) => {
  const el = event.target.closest('[data-cmd],[data-sheet],[data-pick],[data-pref],[data-step],[data-chanstep],[data-family],[data-marker],[data-copy],[data-dismiss],[data-close]');
  if (!el || el.disabled) return;
  const d = el.dataset;
  if ('close' in d) sheetName = null;
  else if ('dismiss' in d) notify(null);
  else if (d.sheet) sheetName = d.sheet;
  else if (d.pick) sheetName = d.pick;
  else if (d.pref) {
    sheetName = null;
    await send(d.pref, { value: JSON.parse(d.value) }, d.label);
  } else if (d.family) pages.setMap(d.family, null);
  else if (d.marker) pages.setMap(undefined, d.marker);
  else if (d.copy !== undefined) {
    try {
      await navigator.clipboard.writeText(d.copy);
      el.textContent = 'Copied';
    } catch {
      el.textContent = 'Select and copy';
    }
    return;
  } else if (d.chanstep !== undefined) {
    const values = [...(store.state?.lights?.channels || Array(8).fill(0))];
    const i = Number(d.chanstep);
    values[i] = Math.min(100, Math.max(0, values[i] + Number(d.delta)));
    const name = store.content?.channels?.[i]?.label || 'Channel';
    await send('channels', { values }, `${name} ${values[i]}%`);
  } else if (d.step) {
    const lights = store.state?.lights || {};
    const limits = { cct: [1600, 10000], intensity: [0, 1900] };
    const next = { cct: lights.cct, intensity: lights.intensity };
    next[d.step] = Math.min(limits[d.step][1], Math.max(limits[d.step][0], next[d.step] + Number(d.delta)));
    await send('cct', next, d.step === 'cct' ? `${num(next.cct)} K` : `Level ${num(next.intensity)}`);
  } else if (d.cmd) {
    const args = {};
    if (d.name) args.name = d.name;
    if (d.cmd === 'cct') Object.assign(args, { cct: Number(d.cct), intensity: Number(d.intensity) });
    if (d.cmd === 'power') Object.assign(args, { operation: d.operation, confirmed: true });
    if (['check_connection', 'power', 'home'].includes(d.cmd)) sheetName = null;
    await send(d.cmd, args, d.label || d.cmd);
  }
  render(true);
});
$('sheet').addEventListener('click', (event) => {
  if (event.target === $('sheet')) {
    sheetName = null;
    render(true);
  }
});
$('sheet').addEventListener('close', () => {
  sheetName = null;
});

// Sliders: show the value while dragging, send once on release.
document.addEventListener('pointerdown', () => (interacting = true));
document.addEventListener('input', (e) => {
  const input = e.target;
  if (!input.matches('input[type=range]')) return;
  interacting = true;
  progress(input);
  const key = input.dataset.range ?? 'chan' + input.dataset.chan;
  document.querySelectorAll(`[data-val="${key}"]`).forEach((label) => (label.textContent = input.dataset.chan != null ? input.value + '%' : num(input.value)));
  if (input.dataset.chan != null) {
    const bar = document.querySelector(`[data-mix="${input.dataset.chan}"]`);
    if (bar) bar.style.height = input.value + '%';
  }
});
document.addEventListener('change', async (e) => {
  const input = e.target;
  if (!input.matches('input[type=range]')) return;
  interacting = false;
  const lights = store.state?.lights || {};
  if (input.dataset.range) {
    const next = { cct: lights.cct, intensity: lights.intensity, [input.dataset.range]: Number(input.value) };
    await send('cct', next, input.dataset.range === 'cct' ? `${num(next.cct)} K` : `Level ${num(next.intensity)}`);
  } else {
    const values = [...(lights.channels || Array(8).fill(0))];
    values[Number(input.dataset.chan)] = Number(input.value);
    await send('channels', { values }, 'Channel mix');
  }
  render(true);
});
// Release the hold after the click (or slider change) has run.
['pointerup', 'pointercancel'].forEach((type) => document.addEventListener(type, (e) => {
  setTimeout(() => {
    interacting = false;
    render();
  }, e.target.matches?.('input[type=range]') ? 600 : 250);
}));

// ---------- Loop ----------
// Scroll to the top only when the main page changes, not for tabs within it.
let lastPage = route().page;
addEventListener('hashchange', () => {
  const { page } = route();
  if (page !== lastPage || (device() === 'phone' && page !== 'lights')) scrollTo(0, 0);
  lastPage = page;
  render(true);
});
phone.addEventListener('change', () => render(true));
dark.addEventListener('change', () => render(true));
onChange(() => render());
nav();
loadContent().then(nav);
(async function loop() {
  await poll();
  setTimeout(loop, busy() ? 500 : document.hidden ? 5000 : 1500);
})();
document.addEventListener('visibilitychange', () => !document.hidden && poll());
