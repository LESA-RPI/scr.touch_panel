'use strict';
const byId = id => document.getElementById(id);
const systemTheme = matchMedia('(prefers-color-scheme: dark)');
function applyTheme() {
  document.documentElement.dataset.theme = systemTheme.matches ? 'dark' : 'light';
}
systemTheme.addEventListener('change', applyTheme);
applyTheme();

const roomTime = new Intl.DateTimeFormat('en-US', {timeZone: 'America/New_York', hour: 'numeric', minute: '2-digit'});
const roomDate = new Intl.DateTimeFormat('en-US', {timeZone: 'America/New_York', weekday: 'long', month: 'long', day: 'numeric', year: 'numeric'});
function clock() { const now = new Date(); byId('clock').textContent = roomTime.format(now); byId('date').textContent = roomDate.format(now); }
clock(); setInterval(clock, 1000);

let snapshot = null, receivedAt = 0, pending = false, failed = false;
const number = value => typeof value === 'number' && Number.isFinite(value);
function age(seconds) { return seconds < 60 ? `${Math.floor(seconds)} seconds ago` : `${Math.floor(seconds / 60)} minutes ago`; }
function badge(element, text, state) { element.textContent = text; element.className = element.id === 'connection' ? `connection ${state}` : `service-state ${state}`; }
function render() {
  if (!snapshot) { badge(byId('connection'), failed ? 'Status unavailable' : 'Checking…', failed ? 'warning' : ''); return; }
  const elapsed = Math.max(0, (performance.now() - receivedAt) / 1000);
  const sampleAge = snapshot.sample_age_s + elapsed;
  const stale = failed || sampleAge > 90;
  badge(byId('connection'), failed ? 'Page connection lost' : stale ? 'Readings are stale' : 'Updating normally', stale ? 'warning' : 'good');
  byId('freshness').textContent = `Computer readings ${age(sampleAge)}${stale ? ' · not current' : ''}.`;
  const host = snapshot.host, room = snapshot.room;
  byId('host-label').textContent = `${snapshot.host_label} · diagnostics`;
  byId('source-description').textContent = room.state === 'unconfigured' ?
    `Host-only preview · These readings come from ${snapshot.host_label}, not the room. No room connection is configured.` :
    `Readings from ${snapshot.host_label} · Room connections are checked separately below.`;
  byId('source-description').className = `source-note ${room.state === 'unconfigured' ? 'preview-note' : ''}`;
  byId('memory').textContent = number(host.memory_available_mib) ? `${host.memory_available_mib} MiB` : 'Unavailable';
  byId('memory-note').textContent = number(host.memory_total_mib) ? `Available of ${host.memory_total_mib} MiB total` : 'Not supported on this host';
  byId('temperature').textContent = number(host.temperature_c) ? `${host.temperature_c.toFixed(1)} °C` : 'Unavailable';
  const power = {warning_now: 'Low voltage now', warning_earlier: 'Earlier low voltage', no_warning: 'No voltage warning', unavailable: 'Not available'};
  byId('power').textContent = power[host.power] || 'Not available';
  byId('power').className = `power-value ${host.power.startsWith('warning') ? 'warning' : ''}`;
  byId('uptime').textContent = number(host.uptime_s) ? `Uptime · ${(host.uptime_s / 3600).toFixed(1)} hours` : 'Uptime unavailable';
  const graphStale = stale || room.state !== 'available' || !number(room.observation_age_s) || room.observation_age_s + elapsed > 90;
  document.querySelectorAll('[data-service]').forEach(card => {
    const service = room.services.find(item => item.name === card.dataset.service);
    const labels = {advertised: 'Service listed', partial: 'Some services listed', not_advertised: 'Not listed'};
    const label = service ? labels[service.state] || 'Not checked' : 'Not checked';
    badge(card.querySelector('.service-state'), service && graphStale ? `Previous: ${label.toLowerCase()}` : label,
      graphStale ? '' : service?.state === 'advertised' ? 'good' : 'warning');
  });
  byId('room-note').textContent = room.state === 'unconfigured' ? 'Room service lookup is not configured. Host status remains available.' :
    room.observed_at ? `Service list observed ${age(room.observation_age_s + elapsed)}${graphStale ? ' · previous information; current availability is unknown' : ' · registrations only'}.` :
      'Room service lookup is unavailable. Device state is unknown; no recovery action was attempted.';
}
async function refresh() {
  if (pending || document.hidden) return;
  pending = true;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 4000);
  try {
    const response = await fetch('/api/status', {signal: controller.signal, cache: 'no-store'});
    if (!response.ok) throw new Error('Unavailable');
    const next = await response.json();
    if (next.version !== 1 || next.read_only !== true || !next.host || !next.room || !Array.isArray(next.room.services) || !number(next.sample_age_s)) throw new Error('Invalid status');
    snapshot = next; receivedAt = performance.now(); failed = false;
  } catch (_) { failed = true; }
  finally { clearTimeout(timer); pending = false; render(); }
}
refresh(); setInterval(refresh, 30000); setInterval(render, 1000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
