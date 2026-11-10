// The only code that talks to the panel. One command at a time, never resent.
export const store = {
  state: null, // last /api/controller snapshot
  content: null, // room-content.json (guide, help, icons, scenes)
  reachable: false,
  lastOk: 0,
  pending: null, // {id, action, label, session, sentAt, status: 'sending' | 'unknown'}
  awaiting: null, // {label, since}: accepted, waiting for the lights to confirm
  notice: null, // {text, warn, at}
};
const listeners = new Set();
export const onChange = (fn) => listeners.add(fn);
const emit = () => listeners.forEach((fn) => fn());

const UNKNOWN_GIVE_UP_MS = 20000; // the panel discards queued work after 2 s
const AWAIT_GIVE_UP_MS = 30000;

function signal(ms) {
  const controller = new AbortController();
  setTimeout(() => controller.abort(), ms);
  return controller.signal;
}

export function notify(text, warn = false) {
  store.notice = text ? { text, warn, at: Date.now() } : null;
  emit();
}

export async function loadContent() {
  try {
    const response = await fetch('/room-content.json', { cache: 'no-store', signal: signal(8000) });
    store.content = await response.json();
  } catch {
    store.content = null;
  }
  emit();
}

let polling = false;
export async function poll() {
  if (polling) return;
  polling = true;
  try {
    const response = await fetch('/api/controller', { cache: 'no-store', signal: signal(4000) });
    const value = await response.json();
    store.state = value;
    store.reachable = true;
    store.lastOk = Date.now();
    settle(value);
  } catch {
    if (Date.now() - store.lastOk > 6000) store.reachable = false;
  } finally {
    polling = false;
  }
  emit();
}

// Resolve the last command from what the panel reports. Never repeats a command.
function settle(state) {
  const pending = store.pending;
  if (pending) {
    const receipt = (state.receipts || []).find((r) => r.id === pending.id);
    if (receipt) {
      store.pending = null;
      if (receipt.ok) startAwaiting(pending);
      else notify(receipt.detail || 'The panel did not accept that.', true);
    } else if (state.session && state.session !== pending.session) {
      store.pending = null;
      notify('The panel restarted. Check what the lights show now, then try again if needed.', true);
    } else if (pending.status === 'unknown' && Date.now() - pending.sentAt > UNKNOWN_GIVE_UP_MS) {
      store.pending = null;
      notify("Couldn't confirm that change. The status line shows what the lights are now.", true);
    }
  }
  const awaiting = store.awaiting;
  if (awaiting) {
    const lights = state.lights || {};
    const settled = !state.busy && lights.state !== 'applying' && lights.state !== 'connecting';
    if (settled || Date.now() - awaiting.since > AWAIT_GIVE_UP_MS) store.awaiting = null;
  }
}

function startAwaiting(pending) {
  const lighting = ['on', 'off', 'preset', 'cct', 'channels', 'gradient', 'programme', 'blind', 'check_connection'];
  if (lighting.includes(pending.action)) store.awaiting = { label: pending.label, since: Date.now() };
}

export function busy() {
  return Boolean(store.pending || store.awaiting);
}

export async function send(action, args = {}, label = action) {
  const state = store.state;
  if (store.pending || !state || !state.available || !store.reachable) return false;
  const id = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('');
  store.pending = { id, action, label, session: state.session, sentAt: Date.now(), status: 'sending' };
  store.notice = null;
  emit();
  let response;
  let reply = null;
  try {
    response = await fetch('/api/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-SCR-Token': state.csrf },
      body: JSON.stringify({ id, revision: state.revision, action, arguments: args }),
      signal: signal(6000),
    });
    reply = await response.json().catch(() => null);
  } catch {
    if (store.pending) store.pending.status = 'unknown';
    emit();
    poll();
    return false;
  }
  if (response.status === 202 && reply && reply.ok) {
    store.pending = null;
    startAwaiting({ action, label });
  } else if (response.status === 503 || !reply) {
    if (store.pending) store.pending.status = 'unknown';
  } else {
    // Refused before running (stale page, busy panel, not allowed): nothing changed.
    store.pending = null;
    notify((reply && reply.detail) || 'The panel did not accept that. Nothing changed.', true);
  }
  emit();
  poll();
  return true;
}
