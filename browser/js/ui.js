// Small presentation helpers shared by every page. No room requests here.
import { store } from './api.js';

export const esc = (value) =>
  String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

// Lucide outline icons exported by the panel (app/export_room_content.py).
const ALIASES = { on: 'lighting', health: 'system' }; // panel guide icon names
export function icon(name, cls = '') {
  const parts = store.content?.icons?.[ALIASES[name] || name];
  if (!parts) return '';
  const body = parts
    .map((p) => `<${p.tag} ${Object.entries(p.attributes).map(([k, v]) => `${k}="${esc(v)}"`).join(' ')}/>`)
    .join('');
  return `<svg class="i ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}

export const ago = (seconds) => {
  if (seconds == null) return 'not yet';
  if (seconds < 5) return 'just now';
  if (seconds < 60) return `${Math.round(seconds)} s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  return `${Math.round(seconds / 3600)} h ago`;
};
export const num = (value) => Number(value).toLocaleString('en-US');

export function roomTime(state, options) {
  try {
    return new Intl.DateTimeFormat('en-US', { timeZone: state?.timezone || undefined, ...options }).format(new Date());
  } catch {
    return new Intl.DateTimeFormat('en-US', options).format(new Date());
  }
}

export function weatherIcon(weather) {
  const code = weather?.code;
  const now = Date.now();
  const night = weather?.sunrise && weather?.sunset && !(now >= Date.parse(weather.sunrise) && now <= Date.parse(weather.sunset));
  if (code == null) return 'weather-circle-question-mark';
  if (code === 0) return night ? 'weather-moon' : 'weather-sun';
  if (code <= 2) return night ? 'weather-cloud-moon' : 'weather-cloud-sun';
  if (code === 3) return 'weather-cloud';
  if (code === 45 || code === 48) return 'weather-cloud-fog';
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return 'weather-cloud-snow';
  if (code >= 95) return 'weather-cloud-lightning';
  return 'weather-cloud-rain';
}

// Update the page in place so a button under a finger is never replaced mid-tap.
export function morph(target, html) {
  const next = document.createElement(target.tagName);
  next.innerHTML = html;
  patchChildren(target, next);
}
function patchChildren(old, next) {
  const a = [...old.childNodes], b = [...next.childNodes];
  b.forEach((node, i) => {
    const current = a[i];
    if (!current) old.appendChild(node);
    else if (current.nodeType !== node.nodeType || current.nodeName !== node.nodeName) old.replaceChild(node, current);
    else if (node.nodeType === Node.TEXT_NODE) {
      if (current.nodeValue !== node.nodeValue) current.nodeValue = node.nodeValue;
    } else if (node.nodeType === Node.ELEMENT_NODE) {
      [...current.attributes].forEach((attr) => !node.hasAttribute(attr.name) && current.removeAttribute(attr.name));
      [...node.attributes].forEach((attr) => current.getAttribute(attr.name) !== attr.value && current.setAttribute(attr.name, attr.value));
      if (current.tagName === 'INPUT' && current.value !== node.getAttribute('value')) current.value = node.getAttribute('value');
      patchChildren(current, node);
    }
  });
  for (let i = a.length - 1; i >= b.length; i--) a[i].remove();
}

// CSP forbids inline style attributes: pages mark dynamic values with data-* and we apply them here.
export function applyStyles(root) {
  root.querySelectorAll('[data-bg]').forEach((el) => (el.style.background = el.dataset.bg));
  root.querySelectorAll('[data-h]').forEach((el) => (el.style.height = el.dataset.h));
  root.querySelectorAll('[data-left]').forEach((el) => (el.style.left = el.dataset.left));
  root.querySelectorAll('input[type=range]').forEach(progress);
}
export function progress(input) {
  const p = ((input.value - input.min) / (input.max - input.min)) * 100;
  input.style.setProperty('--p', p + '%');
}
