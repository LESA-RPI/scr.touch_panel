'use strict';
// Shared state and commands come from the existing panel owner. No device driver lives here.
const $ = (id) => document.getElementById(id);
const phoneLayout = matchMedia('(max-width:650px)');
let state = null,
  content = { guide: [], help: [] },
  posting = false,
  unknown = null,
  view = '',
  dragging = false,
  rangeRevision = null,
  chosenHelp = 0;
let powerChoice = null,
  powerRequest = null,
  unknownSession = null, // panel session that was running when a receipt became unknown
  reachable = true; // false when this website's own server does not answer
const paths = {
  home: 'M3 10 12 3l9 7v11h-6v-7H9v7H3Z',
  white: 'M9 18h6m-5 3h4M8 13a6 6 0 1 1 8 0l-1 3H9Z',
  scenes: 'm12 3 10 5-10 5L2 8Zm-10 9 10 5 10-5M2 16l10 5 10-5',
  experiment: 'M9 3h6m-5 0v7L4 20h16l-6-10V3',
  appearance:
    'M12 3v2m0 14v2M3 12h2m14 0h2M6 6l1 1m10 10 1 1M6 18l1-1M17 7l1-1M16 12a4 4 0 1 1-4-4',
  clock: 'M8 2v4m8-4v4M3 9h18M3 4h18v18H3Z',
  screen: 'M3 4h18v13H3Zm9 13v4m-5 0h10',
  system: 'M2 12h5l3-8 4 16 3-8h5',
  about: 'M12 11v6m0-10v1M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
  guide: 'M12 5v16M3 3l9 2 9-2v16l-9 2-9-2Z',
  legacy: 'M14 3h7v7m0-7L10 14M9 5H3v16h16v-6',
  off: 'M9 18h6m-5 3h4M8 13a6 6 0 0 1-2-5m3-4a6 6 0 0 1 7 9l-1 3H9M3 3l18 18',
};
function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
}
function icon(name) {
  const n = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  n.setAttribute('viewBox', '0 0 24 24');
  n.setAttribute('aria-hidden', 'true');
  for (const shape of content.icons?.[name] || [
    { tag: 'path', attributes: { d: paths[name] || paths.about } },
  ]) {
    const child = document.createElementNS(n.namespaceURI, shape.tag);
    for (const [key, value] of Object.entries(shape.attributes)) child.setAttribute(key, value);
    n.append(child);
  }
  return n;
}
function asset(path) {
  return window.SCR_ASSETS?.[path] || path;
}
function button(text, fn, opts = {}) {
  const n = el('button', text, opts.primary ? 'primary' : '');
  n.type = 'button';
  if (opts.icon) n.prepend(icon(opts.icon));
  n.onclick = fn;
  if (opts.action) n.dataset.action = opts.action;
  if (opts.choice) {
    n.dataset.choice = opts.choice[0];
    n.dataset.value = String(opts.choice[1]);
  }
  return n;
}
function link(text, hash, kind) {
  const a = el('a', text);
  a.href = '#' + hash;
  if (kind) a.prepend(icon(kind));
  return a;
}
function command(action, args = {}, revision = state?.revision) {
  if (posting || unknown || !state?.available) {
    // Not sent: put sliders and number boxes back to the confirmed values.
    dragging = false;
    rangeRevision = null;
    sync();
    return Promise.resolve(false);
  }
  const id = Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) =>
    b.toString(16).padStart(2, '0'),
  ).join('');
  const sentSession = state.session;
  if (action === 'power')
    powerRequest = { operation: args.operation, session: state.session, id, accepted: false };
  posting = true;
  sync();
  return fetch('/api/command', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-SCR-Token': state.csrf },
    body: JSON.stringify({ id, revision, action, arguments: args }),
    signal: AbortSignal.timeout(5000),
  })
    .then(async (response) => {
      const reply = await response.json().catch(() => null);
      if (!reply && [400, 403, 405].includes(response.status)) {
        if (action === 'power') powerRequest = null;
        message('Command was rejected. Refresh the page before trying a new action.');
        return false;
      }
      if (
        !reply ||
        typeof reply.ok !== 'boolean' ||
        reply.code !== response.status ||
        ![202, 400, 403, 405, 408, 409].includes(response.status) ||
        (reply.ok && (response.status !== 202 || reply.id !== id))
      ) {
        unknown = id;
        unknownSession = sentSession;
        message(
          action === 'power'
            ? 'Power request status is unknown. Check the touch panel before trying again.'
            : 'Command receipt unknown. Check the panel; do not repeat the action.',
        );
        return false;
      }
      if (!response.ok || !reply.ok) {
        if (action === 'power') powerRequest = null;
        message(reply.detail || 'Command was not accepted.');
        return false;
      }
      if (action === 'power') {
        powerRequest.accepted = true;
        powerChoice = null;
        if ($('power-confirmation')) $('power-confirmation').hidden = true;
        message(
          powerRequest.operation === 'reboot'
            ? 'Restart requested. The panel is preparing to restart.'
            : 'Shutdown requested. The panel is preparing to shut down.',
        );
        return true;
      }
      if (action === 'programme') {
        message(
          args.name === 'Stop'
            ? 'Stop requested. Programme running state is not confirmed.'
            : args.name + ' start requested. Programme running state is not confirmed.',
        );
        return true;
      }
      message(
        ['on', 'off', 'cct', 'channels', 'preset', 'gradient'].includes(action)
          ? 'Sent. Waiting for controller confirmation.'
          : 'Accepted by the panel.',
        true,
      );
      return true;
    })
    .catch(() => {
      unknown = id;
      unknownSession = sentSession;
      message(
        action === 'power'
          ? 'Power request status is unknown. Check the touch panel before trying again.'
          : 'Command receipt unknown. Check the panel; do not repeat the action.',
      );
      return false;
    })
    .finally(async () => {
      posting = false;
      dragging = false;
      rangeRevision = null;
      await refresh();
      sync();
    });
}
// Routine confirmations fade after a few seconds; warnings stay until replaced.
let messageTimer = null;
function message(text, transient = false) {
  clearTimeout(messageTimer);
  messageTimer = null;
  $('message').textContent = text;
  $('message').hidden = !text;
  if (text && transient) messageTimer = setTimeout(() => message(''), 6000);
}
function route() {
  const hash = location.hash.slice(1);
  if (/^(home|guide(-\d+)?|tools-[a-z-]+)$/.test(hash)) return hash;
  return location.pathname === '/guide'
    ? 'guide'
    : location.pathname === '/tools'
      ? 'tools-lighting'
      : 'home';
}
function layout() {
  const next = route();
  if (next === view) return;
  const navigating = view !== '';
  view = next;
  dragging = false;
  rangeRevision = null;
  powerChoice = null;
  const root = $('app');
  root.replaceChildren();
  for (const a of document.querySelectorAll('.header a'))
    a.setAttribute(
      'aria-current',
      a.hash.slice(1) === view ||
        (a.hash === '#tools-lighting' && view.startsWith('tools-')) ||
        (a.hash === '#guide' && view.startsWith('guide'))
        ? 'page'
        : 'false',
    );
  if (view.startsWith('tools-')) tools(root, view.slice(6));
  else if (view.startsWith('guide'))
    guide(root, view === 'guide' ? -1 : Number(view.split('-')[1]));
  else home(root);
  if (messageTimer) message('');
  // Keep the tab title and keyboard focus with the page the visitor just opened.
  const heading = root.querySelector('.tools-layout > section > h2') || root.querySelector('h2');
  document.title =
    (view === 'home' ? '' : (heading?.textContent || '') + ' · ') + 'Smart Conference Room';
  if (navigating && heading) {
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
  }
  sync();
}
function feedback(parent) {
  const box = el('div', undefined, 'feedback');
  const current = el('p');
  current.id = 'light-message';
  current.setAttribute('role', 'status');
  const recent = el('p', undefined, 'muted');
  recent.id = 'light-recent';
  box.append(current, recent);
  parent.append(box);
}
function home(root) {
  const row = el('div', undefined, 'room-layout'),
    left = el('section'),
    right = el('section');
  const groups = el('div', undefined, 'essential-grid');
  groups.id = 'essentials';
  for (const [title, caption, isBlind] of [
    ['Lights', 'Whole room', false],
    ['Blinds', 'Whole room', true],
  ]) {
    const group = el(isBlind ? 'details' : 'div', undefined, 'essential-group');
    group.id = isBlind ? 'blind-group' : 'light-group';
    let actions = group;
    if (isBlind) {
      group.open = !phoneLayout.matches;
      const summary = el('summary');
      // Blinds fold away only on phones; on wider screens the heading is not a toggle.
      summary.onclick = (event) => {
        if (!phoneLayout.matches) event.preventDefault();
      };
      summary.append(el('h2', title));
      const note = el('span', 'Disabled', 'muted');
      note.id = 'blind-status';
      summary.append(note);
      group.append(summary);
      actions = el('div', undefined, 'blind-actions');
      group.append(actions);
    } else group.append(el('h2', title), el('p', caption, 'muted'));
    for (const [name, label] of isBlind
      ? content.blind_actions || [
          ['lift', 'Lift blinds'],
          ['open', 'Open slats'],
          ['close', 'Close & lower'],
        ]
      : [
          ['on', 'Lights on'],
          ['off', 'Lights off'],
        ]) {
      const action = isBlind ? 'blind' : name,
        b = button(label, () => command(action, isBlind ? { name } : {}), {
          icon: isBlind ? null : action === 'on' ? 'white' : 'off',
          action,
        });
      actions.append(b);
    }
    if (!isBlind) group.append(el('small', 'Standard room lighting'));
    groups.append(group);
  }
  left.append(groups);
  feedback(left);
  right.append(el('p', 'Troy, NY', 'eyebrow'));
  const clock = el('p', undefined, 'clock');
  clock.id = 'clock';
  const date = el('p', undefined, 'date');
  date.id = 'date';
  right.append(clock, date);
  right.append(el('p', 'OUTDOOR WEATHER', 'eyebrow'));
  const reading = el('div', undefined, 'weather-reading'),
    temp = el('span', '—', 'temperature'),
    art = el('span');
  temp.id = 'temperature';
  art.id = 'weather-art';
  art.className = 'weather-art';
  art.setAttribute('aria-hidden', 'true');
  reading.append(temp, art);
  right.append(reading);
  const condition = el('p', undefined, 'condition');
  condition.id = 'condition';
  right.append(condition);
  const stats = el('dl', undefined, 'weather-stats');
  stats.id = 'weather-stats';
  for (const [key, label] of [
    ['feels', 'Feels like'],
    ['rain', 'Rain today'],
    ['high', 'High'],
    ['low', 'Low'],
  ]) {
    const item = el('div', undefined, 'weather-metric'),
      value = el('dd', '—');
    value.id = 'weather-' + key;
    item.append(el('dt', label), value);
    stats.append(item);
  }
  right.append(stats);
  const notice = el('p', undefined, 'weather-notice');
  notice.id = 'weather-notice';
  notice.hidden = true;
  right.append(notice);
  const day = el('div', undefined, 'daylight');
  day.id = 'daylight';
  const label = el('p');
  label.id = 'daylight-label';
  const track = el('div', undefined, 'track'),
    fill = el('div');
  fill.id = 'daylight-fill';
  track.append(fill);
  const times = el('div', undefined, 'daylight-times');
  const rise = el('span'),
    set = el('span');
  rise.id = 'sunrise';
  set.id = 'sunset';
  times.append(rise, set);
  day.append(label, track, times);
  right.append(day);
  const details = el('details'),
    summary = el('summary', 'Weather details'),
    source = el('p', undefined, 'subtle');
  source.id = 'weather-source';
  details.append(summary, source);
  right.append(details);
  row.append(left, right);
  root.append(row);
}
const pages = [
  ['Lighting', 'lighting'],
  ['Experiment mode', 'experiment'],
  ['Appearance', 'appearance'],
  ['Date & weather', 'clock'],
  ['Screen & controls', 'screen'],
  ['System & help', 'system'],
  ['About', 'about'],
];
// One settings row: title and explanation on the left, its control on the right.
function setting(parent, title, note) {
  const row = el('section', undefined, 'setting'),
    text = el('div', undefined, 'setting-text'),
    control = el('div', undefined, 'setting-control');
  text.append(el('h3', title), el('p', note, 'muted'));
  row.append(text, control);
  parent.append(row);
  return control;
}
// A segmented choice; sync() marks the saved value as selected.
function choices(parent, items) {
  const group = el('div', undefined, 'segmented');
  group.setAttribute('role', 'group');
  for (const [label, action, value] of items)
    group.append(
      button(label, () => command(action, { value }), { action, choice: [action, value] }),
    );
  parent.append(group);
}
function tools(root, page) {
  let tab = page.startsWith('lighting-') ? page.slice(9) : page === 'scenes' ? 'channels' : 'white';
  if (!['white', 'scenes', 'programmes', 'channels'].includes(tab)) tab = 'white';
  if (page.startsWith('lighting-') || ['white', 'scenes'].includes(page)) page = 'lighting';
  if (!pages.some((p) => p[1] === page)) page = 'lighting';
  const shell = el('div', undefined, 'tools-layout'),
    nav = el('nav', undefined, 'sidebar'),
    detail = el('section');
  nav.setAttribute('aria-label', 'Room tools');
  nav.append(el('h2', 'Room tools'));
  for (const [label, key] of pages) {
    const a = link(label, 'tools-' + key, key);
    if (key === page) a.setAttribute('aria-current', 'page');
    nav.append(a);
  }
  const mobile = el('label', undefined, 'tools-mobile');
  mobile.append(el('span', 'Room tools'));
  const picker = el('select');
  picker.id = 'tool-picker';
  for (const [label, key] of pages) {
    const option = el('option', label);
    option.value = key;
    picker.append(option);
  }
  picker.value = page;
  picker.onchange = () => {
    location.hash = 'tools-' + picker.value;
  };
  mobile.append(picker);
  shell.append(nav, mobile, detail);
  root.append(shell);
  detail.append(el('h2', pages.find((p) => p[1] === page)[0]));
  if (page === 'lighting') lighting(detail, tab);
  else if (page === 'experiment') {
    detail.append(
      el('p', 'Recorder not connected · instructions and panel annotations only', 'muted'),
    );
    const card = el('div', undefined, 'card'),
      title = el('h3'),
      stage = el('p', undefined, 'session-stage'),
      timer = el('p', undefined, 'timer'),
      status = el('p', undefined, 'muted');
    title.id = 'profile-title';
    stage.id = 'instruction';
    timer.id = 'elapsed';
    status.id = 'session-state';
    card.append(title, stage, timer, status);
    detail.append(card);
    const row = el('div', undefined, 'row');
    row.append(
      button('Start instructions', () => command('start'), { action: 'start', primary: true }),
      button('Pause', () => command('pause'), { action: 'pause' }),
    );
    detail.append(row);
    const steps = el('div', undefined, 'row');
    steps.append(
      button('Previous instruction', () => command('previous'), { action: 'previous' }),
      button('Next instruction', () => command('next'), { action: 'next' }),
    );
    detail.append(steps);
    const marks = el('div', undefined, 'row');
    marks.id = 'marks';
    detail.append(marks);
    const note = el('p', undefined, 'subtle');
    note.id = 'annotation';
    detail.append(note);
  } else if (page === 'appearance') {
    choices(
      setting(
        detail,
        'Theme',
        'Auto switches at the times below, waiting while the panel is in use.',
      ),
      [
        ['Light', 'theme', 'light'],
        ['Dark', 'theme', 'dark'],
        ['Auto', 'theme', 'auto'],
      ],
    );
    for (const [title, which] of [
      ['Light theme starts', 'light_at'],
      ['Dark theme starts', 'dark_at'],
    ]) {
      const control = setting(detail, title, '');
      control.previousElementSibling.querySelector('p').id = 'schedule-' + which;
      const group = el('div', undefined, 'segmented');
      group.append(
        button('−1 h', () => command('schedule', { which, delta: -60 }), { action: 'schedule' }),
        button('+1 h', () => command('schedule', { which, delta: 60 }), { action: 'schedule' }),
      );
      control.append(group);
    }
    choices(setting(detail, 'Touch tips', 'Short explanations on the touch panel.'), [
      ['On', 'tips', true],
      ['Off', 'tips', false],
    ]);
  } else if (page === 'clock') {
    choices(setting(detail, 'Clock', 'Time zone: America/New_York'), [
      ['12-hour', 'clock', '12'],
      ['24-hour', 'clock', '24'],
    ]);
    choices(setting(detail, 'Temperature', 'Used for outdoor weather.'), [
      ['Celsius (°C)', 'temperature', 'c'],
      ['Fahrenheit (°F)', 'temperature', 'f'],
    ]);
    const source = el('p', undefined, 'subtle');
    source.id = 'weather-source';
    detail.append(source);
  } else if (page === 'screen') {
    choices(
      setting(
        detail,
        'Screen saver',
        'A first touch on the screen saver opens Home without pressing anything.',
      ),
      [
        ['Off', 'idle', 0],
        ['1 min', 'idle', 60],
        ['5 min', 'idle', 300],
        ['15 min', 'idle', 900],
      ],
    );
    const display = setting(
      detail,
      'Touch panel screen',
      'Blank shows black pixels; hold one spot for two seconds to return.',
    );
    const actions = el('div', undefined, 'actions');
    actions.append(
      button('Preview screen saver', () => command('clock_view'), { action: 'clock_view' }),
      button('Blank', () => command('blank'), { action: 'blank' }),
      button('Wake to Home', () => command('home'), { action: 'home' }),
    );
    display.append(actions);
    const blinds = setting(detail, 'Blind controls', '');
    blinds.previousElementSibling.querySelector('p').id = 'blind-reason';
    const permission = el('div');
    permission.id = 'blind-permission';
    permission.hidden = !state?.blinds?.connected;
    choices(permission, [
      ['Locked', 'blinds_enabled', false],
      ['Unlocked', 'blinds_enabled', true],
    ]);
    blinds.append(permission);
    choices(setting(detail, 'Blinds on Home', 'Show the blind buttons on Home.'), [
      ['Show', 'blinds_display', 'disabled'],
      ['Hide', 'blinds_display', 'hidden'],
    ]);
  } else if (page === 'system') system(detail);
  else {
    const version = el('p', undefined, 'muted'),
      build = el('p', undefined, 'subtle');
    version.id = 'app-version';
    build.id = 'app-build';
    build.hidden = true;
    detail.append(
      el('h3', 'Smart Conference Room'),
      el('p', 'Touch panel and browser', 'muted'),
      version,
      build,
      el('p', 'Built by Diyanko Bhowmik'),
      el('p', 'Original contributors are credited in the repository history.', 'muted'),
    );
    const a = el('a', 'github.com/LESA-RPI/scr.touch_panel');
    a.href = 'https://github.com/LESA-RPI/scr.touch_panel';
    detail.append(a, el('p', 'Icons: Lucide · lucide.dev', 'subtle'));
  }
}
function lighting(detail, tab) {
  const tabs = el('nav', undefined, 'lighting-tabs');
  tabs.setAttribute('aria-label', 'Lighting');
  for (const [label, key] of content.lighting_tabs || [
    ['White light', 'white'],
    ['Scenes', 'scenes'],
    ['Programmes', 'programmes'],
    ['Channels', 'channels'],
  ]) {
    const a = link(label, 'tools-lighting-' + key);
    if (key === tab) a.setAttribute('aria-current', 'page');
    tabs.append(a);
  }
  detail.append(tabs);
  if (tab === 'scenes') {
    detail.append(el('p', 'Original scene names and mixtures from Legacy.', 'muted'));
    const grid = el('div', undefined, 'scene-grid');
    for (const scene of content.scenes || []) {
      const card = el('section', undefined, 'card'),
        b = button('Apply scene', () => command('preset', { name: scene.id }), {
          action: 'preset',
        });
      b.dataset.preset = scene.id;
      card.append(el('h3', scene.label), el('p', scene.detail, 'muted'), b);
      grid.append(card);
    }
    const gradient = el('section', undefined, 'card');
    gradient.id = 'gradient-controls';
    gradient.hidden = !state?.lights?.capabilities?.gradient;
    const apply = button('Apply gradient', () => command('gradient'), {
      action: 'gradient',
    });
    apply.dataset.preset = 'Gradient';
    gradient.append(
      el('h3', content.gradient?.label || 'Gradient'),
      el(
        'p',
        content.gradient?.detail || 'Original spatial pattern across the ten room lights.',
        'muted',
      ),
      apply,
    );
    grid.append(gradient);
    detail.append(grid);
    feedback(detail);
  } else if (tab === 'programmes') {
    const unavailable = el(
      'p',
      content.unavailable_lighting || 'Original lighting programmes are unavailable on this panel.',
      'muted',
    );
    unavailable.id = 'programmes-unavailable';
    const controls = el('div');
    controls.id = 'programme-controls';
    controls.hidden = !state?.lights?.capabilities?.programmes;
    const grid = el('div', undefined, 'scene-grid');
    for (const programme of content.programmes || [
      {
        id: 'Sun',
        label: 'Original Sun programme',
        detail: 'A spatially staggered colour-temperature curve.',
      },
      {
        id: 'Circ',
        label: 'Original Circ programme',
        detail: 'A whole-room colour-temperature curve.',
      },
    ]) {
      const card = el('section', undefined, 'card');
      const start = button(
        'Start ' + programme.id,
        () => command('programme', { name: programme.id }),
        { action: 'programme' },
      );
      start.dataset.programme = programme.id;
      card.append(el('h3', programme.label), el('p', programme.detail, 'muted'), start);
      grid.append(card);
    }
    const stop = button(
      'Stop programmes',
      () => command('programme', { name: 'Stop' }),
      { action: 'programme' },
    );
    stop.dataset.programme = 'Stop';
    const status = el('p', '', 'muted');
    status.id = 'programme-status';
    status.setAttribute('role', 'status');
    controls.append(grid, stop, status);
    detail.append(unavailable, controls);
  } else if (tab === 'channels') {
    detail.append(el('p', 'Adjust the eight room-wide channel percentages.', 'muted'));
    const grid = el('div', undefined, 'channel-grid');
    for (const [i, label] of [
      'Blue 1',
      'Blue 2',
      'Blue 3',
      'Lime',
      'Amber',
      'Orange',
      'Red 1',
      'Red 2',
    ].entries())
      range(grid, label, 'channel-' + i, 0, 100, 1, '%');
    detail.append(grid);
    feedback(detail);
  } else {
    detail.append(el('p', 'Selected values apply after your touch settles.', 'muted'));
    const grid = el('div', undefined, 'white-grid');
    range(grid, 'Colour temperature', 'cct', 1600, 10000, 100, 'K');
    range(grid, 'Light level', 'intensity', 0, 1900, 25, 'controller units');
    detail.append(grid);
    feedback(detail);
  }
}
function range(parent, title, key, low, high, step, unit) {
  const box = el('section', undefined, 'range-card'),
    heading = el('h3', title);
  const row = el('div', undefined, 'range-value'),
    output = el('input');
  output.type = 'number';
  output.required = true;
  output.id = 'value-' + key;
  output.className = 'numeric-value';
  output.min = low;
  output.max = high;
  output.step = step;
  output.inputMode = 'numeric';
  output.setAttribute('aria-label', title + ' value');
  const units = el('small', unit),
    steps = el('div', undefined, 'steps');
  const input = el('input');
  input.type = 'range';
  input.id = key;
  input.min = low;
  input.max = high;
  input.step = step;
  input.dataset.range = key;
  input.dataset.unit = unit;
  input.setAttribute('aria-label', title);
  function selected() {
    dragging = true;
    rangeRevision ??= state?.revision;
    output.value = input.value;
    input.setAttribute('aria-valuetext', input.value + ' ' + unit);
  }
  input.oninput = selected;
  input.onchange = () => {
    selected();
    commitRange(key);
  };
  output.onfocus = () => {
    dragging = true;
    rangeRevision ??= state?.revision;
  };
  let cancelEdit = false;
  output.onchange = () => {
    if (cancelEdit) return;
    if (!output.checkValidity()) {
      output.reportValidity();
      return;
    }
    input.value = output.value;
    selected();
    commitRange(key);
  };
  output.onblur = () => {
    if (!posting) {
      dragging = false;
      rangeRevision = null;
      sync();
    }
  };
  output.onkeydown = (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      output.blur();
    } else if (event.key === 'Escape') {
      cancelEdit = true;
      output.value = input.value;
      dragging = false;
      rangeRevision = null;
      output.blur();
      cancelEdit = false;
      sync();
    }
  };
  for (const [label, delta] of key.startsWith('channel')
    ? []
    : [
        ['−', -step],
        ['+', step],
      ]) {
    const b = button(
      label,
      () => {
        input.value = Math.max(low, Math.min(high, Number(input.value) + delta));
        selected();
        commitRange(key);
      },
      { action: key.startsWith('channel') ? 'channels' : 'cct' },
    );
    b.setAttribute('aria-label', (delta < 0 ? 'Decrease ' : 'Increase ') + title.toLowerCase());
    steps.append(b);
  }
  const value = el('span', undefined, 'value-group');
  value.append(output, units);
  row.append(value, steps);
  const limits = el('div', undefined, 'limits');
  limits.append(
    el('span', 'Min ' + low.toLocaleString() + ' ' + unit),
    el('span', 'Max ' + high.toLocaleString() + ' ' + unit),
  );
  box.append(heading, row, input, limits);
  parent.append(box);
}
function commitRange(key) {
  if (key.startsWith('channel'))
    command(
      'channels',
      { values: Array.from({ length: 8 }, (_, i) => Number($('channel-' + i).value)) },
      rangeRevision,
    );
  else
    command(
      'cct',
      { cct: Number($('cct').value), intensity: Number($('intensity').value) },
      rangeRevision,
    );
}
function guide(root, index) {
  const topics = state?.guide || content.guide;
  root.append(el('h2', 'Demo & guide'));
  if (index < 0 || !topics[index]) {
    root.append(
      el('p', 'Choose a topic. Exploring this guide does not operate equipment.', 'muted'),
    );
    const grid = el('div', undefined, 'topics');
    for (const [i, t] of topics.entries()) {
      const a = link(
        t.title,
        'guide-' + i,
        { on: 'white', home: 'home', experiment: 'experiment', health: 'system', room: 'white' }[
          t.icon
        ],
      );
      a.className = 'topic';
      grid.append(a);
    }
    root.append(grid);
    return;
  }
  const t = topics[index],
    card = el('article', undefined, 'card topic-body'),
    head = el('div', undefined, 'topic-head');
  head.append(
    icon(
      { on: 'white', home: 'home', experiment: 'experiment', health: 'system', room: 'white' }[
        t.icon
      ],
    ),
    el('h3', t.title),
  );
  card.append(head);
  for (const p of t.text.split('\n\n')) card.append(el('p', p));
  root.append(card);
  const nav = el('nav', undefined, 'row');
  nav.append(link('All topics', 'guide', 'guide'));
  if (index > 0) nav.append(link('Previous', 'guide-' + (index - 1)));
  if (index < topics.length - 1) nav.append(link('Next', 'guide-' + (index + 1)));
  root.append(nav);
}
function system(parent) {
  const cards = el('div', undefined, 'health-grid');
  for (const [id, title] of [
    ['panel-health', 'Panel health'],
    ['room-health', 'Room connection'],
  ]) {
    const card = el('section', undefined, 'card'),
      text = el(id === 'panel-health' ? 'div' : 'p', undefined, 'muted');
    text.id = id;
    if (id === 'panel-health')
      for (const key of ['panel-memory', 'panel-storage', 'panel-power']) {
        const line = el('p');
        line.id = key;
        text.append(line);
      }
    card.append(el('h3', title), text);
    cards.append(card);
  }
  parent.append(cards);
  const views = el('section', undefined, 'card');
  views.id = 'panel-view-controls';
  const viewActions = el('div', undefined, 'row');
  viewActions.append(
    button('Show Legacy view', () => command('legacy'), { action: 'legacy' }),
    button('Open Original fallback', () => command('original_fallback'), {
      action: 'original_fallback',
    }),
  );
  views.append(
    el('h3', 'Panel views'),
    el('p', 'Legacy uses the same controller and keeps current settings.', 'muted'),
    el(
      'p',
      'Original fallback opens the separate original application after controller release. Website controls pause until it returns.',
      'muted',
    ),
    viewActions,
  );
  parent.append(views);
  powerControls(parent);
  const row = el('label', undefined, 'help-select');
  row.append(el('span', 'Help topic'));
  const select = el('select');
  select.setAttribute('aria-label', 'Help topic');
  select.id = 'help-topic';
  row.append(select);
  parent.append(row);
  const topics = state?.help || content.help;
  for (const [i, t] of topics.entries()) {
    const option = el('option', t.title);
    option.value = i;
    select.append(option);
  }
  select.value = chosenHelp;
  select.onchange = () => {
    chosenHelp = Number(select.value);
    renderHelp();
  };
  const detail = el('div');
  detail.id = 'help-detail';
  parent.append(detail);
  renderHelp();
  const a = el('a', 'More diagnostics', 'help-diagnostics');
  a.href = window.SCR_DEMO ? '#tools-system' : '/diagnostics';
  parent.append(a);
}
function powerControls(parent) {
  const card = el('section', undefined, 'card power-controls');
  card.id = 'panel-power-controls';
  card.append(
    el('h3', 'Panel power'),
    el(
      'p',
      'These actions affect this touch panel and its website. They do not stop the room computer or connected recorders. Stop recordings and experiments first.',
      'muted',
    ),
  );
  const status = el('p', 'Power controls unavailable.', 'power-status');
  status.id = 'power-status';
  status.setAttribute('role', 'status');
  card.append(status);
  const actions = el('div', undefined, 'row');
  for (const [operation, label] of [
    ['reboot', 'Restart panel'],
    ['shutdown', 'Shut down panel'],
  ]) {
    const b = button(label, () => {
      if (!powerAllowed(operation)) return;
      powerChoice = { operation, revision: state.revision };
      $('power-confirm-title').textContent =
        operation === 'reboot' ? 'Restart this panel?' : 'Shut down this panel?';
      $('power-confirm-text').textContent =
        operation === 'reboot'
          ? 'Controls and this website will be unavailable while the panel restarts.'
          : 'Controls and this website will be unavailable until the panel is powered on again.';
      $('power-ack').checked = false;
      $('power-confirm').textContent =
        operation === 'reboot' ? 'Confirm restart' : 'Confirm shutdown';
      $('power-confirmation').hidden = false;
      syncPower();
      $('power-ack').focus();
    });
    b.id = 'power-' + operation;
    b.disabled = true;
    actions.append(b);
  }
  card.append(actions);
  const confirm = el('section', undefined, 'power-confirmation');
  confirm.id = 'power-confirmation';
  confirm.hidden = true;
  confirm.setAttribute('aria-labelledby', 'power-confirm-title');
  const title = el('h3');
  title.id = 'power-confirm-title';
  const text = el('p');
  text.id = 'power-confirm-text';
  const ack = el('label', undefined, 'power-ack'),
    input = el('input');
  input.type = 'checkbox';
  input.id = 'power-ack';
  input.onchange = syncPower;
  ack.append(input, el('span', 'I have stopped any recording or experiment'));
  const row = el('div', undefined, 'row'),
    cancel = button('Cancel', () => {
      const operation = powerChoice?.operation;
      powerChoice = null;
      confirm.hidden = true;
      $('power-' + operation)?.focus();
    }),
    submit = button('Confirm', () => {
      if (!powerChoice || !input.checked || !powerAllowed(powerChoice.operation)) return;
      const choice = powerChoice;
      command('power', { operation: choice.operation, confirmed: true }, choice.revision);
    });
  submit.id = 'power-confirm';
  submit.className = 'power-submit';
  submit.disabled = true;
  row.append(cancel, submit);
  confirm.append(title, text, ack, row);
  card.append(confirm);
  parent.append(card);
}
function powerAllowed(operation) {
  return (
    !!state?.available &&
    !!state?.power?.available &&
    state.power.actions?.[operation] === true &&
    !posting &&
    !unknown &&
    !state.busy &&
    !state.experiment?.running &&
    state.mode !== 'original' &&
    state.lights?.state !== 'failed' &&
    !powerRequest?.accepted
  );
}
function syncPower() {
  if (!$('panel-power-controls')) return;
  for (const operation of ['reboot', 'shutdown'])
    $('power-' + operation).disabled = !powerAllowed(operation);
  if ($('power-confirm'))
    $('power-confirm').disabled =
      !powerChoice || !$('power-ack').checked || !powerAllowed(powerChoice.operation);
  let text =
    state?.power?.message || 'Power controls unavailable. Ask the room host to check this panel.';
  if (
    powerRequest?.accepted &&
    state?.available &&
    state.power?.phase === 'ready' &&
    state.session === powerRequest.session
  )
    text =
      powerRequest.operation === 'reboot'
        ? 'Restart requested. Waiting for this panel to finish.'
        : 'Shutdown requested. Waiting for this panel to finish.';
  if (powerRequest?.accepted && !state?.available)
    text =
      powerRequest.operation === 'reboot'
        ? 'The panel is restarting. This website will reconnect when it is ready.'
        : 'The panel is shutting down. This website will disconnect until the panel is powered on again.';
  update('power-status', text);
}
function renderHelp() {
  if (!$('help-detail')) return;
  const topic = (state?.help || content.help)[chosenHelp];
  $('help-detail').replaceChildren();
  if (!topic) return;
  const card = el('section', undefined, 'card');
  for (const p of topic.text.split('\n\n')) card.append(el('p', p));
  $('help-detail').append(card);
  if (topic.commands) {
    $('help-detail').append(
      el(
        'p',
        'Room host reference · copy only. These commands are never run by this website.',
        'subtle',
      ),
    );
    const reference = topic.reference,
      steps = reference?.steps?.length
        ? reference.steps
        : [{ title: topic.title, commands: topic.commands, command_tokens: topic.command_tokens }];
    const head = el('div', undefined, 'reference-head');
    head.append(
      el(
        'div',
        reference ? reference.machine + ' · ' + reference.effect : 'Reference commands',
        ['Start services', 'Restart computer'].includes(topic.title)
          ? 'reference-warning'
          : 'muted',
      ),
      copyButton('Copy commands', topic.commands),
    );
    $('help-detail').append(head);
    for (const [index, step] of steps.entries()) {
      const block = el('article', undefined, 'command command-step'),
        bar = el('div', undefined, 'command-head'),
        pre = el('pre'),
        code = el('code');
      bar.append(
        el('h3', (steps.length > 1 ? index + 1 + '. ' : '') + step.title),
        copyButton('Copy command', step.commands),
      );
      block.append(bar);
      if (step.why) block.append(el('p', step.why, 'command-why'));
      for (const token of step.command_tokens || [{ text: step.commands, kind: 'text' }])
        code.append(el('span', token.text, 'syntax-' + token.kind));
      pre.append(code);
      block.append(pre);
      if (step.expect) {
        const expected = el('div', undefined, 'command-expect');
        expected.append(el('strong', 'What to expect'), el('p', step.expect));
        block.append(expected);
      }
      $('help-detail').append(block);
    }
    if (reference?.documentation) {
      const a = el('a', reference.documentation.label, 'documentation-link');
      a.href = reference.documentation.url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      $('help-detail').append(a);
    }
  }
}
function copyButton(label, value) {
  return button(label, async (event) => {
    const b = event.currentTarget;
    try {
      await copy(value);
      b.textContent = 'Copied';
    } catch (_) {
      b.textContent = 'Select text to copy';
    }
    setTimeout(() => {
      if (b.isConnected) b.textContent = label;
    }, 1800);
  });
}
async function copy(value) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(value);
      return;
    } catch (_) {}
  }
  const active = document.activeElement,
    input = el('textarea');
  input.value = value;
  input.className = 'visually-hidden';
  document.body.append(input);
  input.select();
  const ok = document.execCommand('copy');
  input.remove();
  active?.focus({ preventScroll: true });
  if (!ok) throw Error('Copy unavailable');
}
function update(id, text) {
  if ($(id) && $(id).textContent !== String(text)) $(id).textContent = text;
}
function sync() {
  const p = state?.preferences || {},
    s = state?.lights || {},
    available = state?.available === true;
  const version =
    String(state?.app_version || content.app_version || '').match(/^\d+\.\d+\.\d+/)?.[0] || '';
  update('app-version', version ? 'Version ' + version : '');
  if ($('app-build')) {
    const build = state?.build_commit;
    $('app-build').hidden = !/^[0-9a-f]{7,40}$/.test(build || '');
    update('app-build', build ? 'Build ' + build.slice(0, 7) : '');
  }
  if (state?.palette) window.SCRDesign.apply(state.palette, p.resolved_theme);
  update(
    'connection',
    state === null && reachable
      ? 'Connecting…'
      : !available && powerRequest?.accepted
        ? powerRequest.operation === 'reboot'
          ? 'Restarting panel'
          : 'Shutting down panel'
        : !reachable
          ? 'Website offline'
          : !available
            ? 'Panel unavailable'
            : state.mode === 'original'
              ? 'Original fallback'
              : state.mode === 'classic' && !state.busy
                ? 'Legacy'
                : state.busy
                  ? 'Sending'
                  : state.can_control
                    ? 'Ready'
                    : s.state === 'failed'
                      ? 'Uncertain'
                      : 'Controls unavailable',
  );
  // Colour the header status: ready, waiting (connecting/sending/Legacy) or problem.
  $('connection').dataset.state =
    state === null && reachable
      ? 'waiting'
      : !available || s.state === 'failed'
        ? 'problem'
        : state.can_control
          ? 'ready'
          : 'waiting';
  const panelMessage =
    state?.mode === 'original'
      ? 'The touch panel is showing Original fallback, the separate original application. Return it to Home to use website controls.'
      : state?.mode === 'black'
        ? 'The touch panel is blank. Return it to Home to use lighting.'
        : state?.mode === 'experiment' && !state.experiment?.running && !state.can_control
          ? 'Experiment mode is paused. Return the touch panel to Home to use lighting.'
          : '';
  $('legacy-banner').hidden = !(available && panelMessage);
  update('panel-mode-message', panelMessage);
  if ($('blind-group')) {
    $('blind-group').hidden = p.blinds_display === 'hidden';
    $('essentials').classList.toggle('single', p.blinds_display === 'hidden');
    $('blind-group').classList.toggle('disabled-group', !state?.blinds?.available);
    update('blind-status', state?.blinds?.available ? 'Ready' : 'Disabled');
  }
  update(
    'blind-reason',
    state?.blinds?.connected ? state.blinds.reason : content.blinds_unavailable,
  );
  if ($('blind-permission')) $('blind-permission').hidden = !state?.blinds?.connected;
  if ($('gradient-controls')) $('gradient-controls').hidden = !s.capabilities?.gradient;
  if ($('programme-controls')) $('programme-controls').hidden = !s.capabilities?.programmes;
  if ($('programmes-unavailable'))
    $('programmes-unavailable').hidden = !!s.capabilities?.programmes;
  update(
    'programme-status',
    s.programme
      ? s.programme + ' programme requested. Running state is not confirmed.'
      : 'No programme selected by this panel. Running state is not confirmed.',
  );
  for (const b of document.querySelectorAll('[data-action]')) {
    const a = b.dataset.action,
      lighting = ['on', 'off', 'cct', 'preset', 'channels', 'gradient'].includes(a),
      session = ['start', 'pause', 'previous', 'next', 'mark'].includes(a);
    b.disabled =
      posting ||
      Boolean(unknown) ||
      !available ||
      state.busy ||
      (['original_fallback', 'blank', 'clock_view'].includes(a) && state.experiment?.running) ||
      (a === 'programme'
        ? state.can_programme === false || !s.capabilities?.programmes ||
          (b.dataset.programme !== 'Stop' && !state.can_control)
        : a === 'gradient'
          ? !s.capabilities?.gradient || !state.can_control
          : a === 'blind'
            ? !state?.blinds?.available
            : lighting
              ? !state.can_control
              : session
                ? !state.can_session
                : false);
  }
  for (const input of document.querySelectorAll('[data-range]')) {
    const number = $('value-' + input.dataset.range);
    input.disabled = number.disabled =
      posting || Boolean(unknown) || !available || !state.can_control;
    if (!dragging) {
      const k = input.dataset.range,
        value = k.startsWith('channel') ? s.channels?.[Number(k.split('-')[1])] : s[k];
      if (value !== undefined && value !== null) {
        input.value = value;
        number.value = value;
        input.setAttribute('aria-valuetext', value + ' ' + input.dataset.unit);
      }
    }
  }
  for (const b of document.querySelectorAll('[data-choice]')) {
    const chosen = String(p[b.dataset.choice]) === b.dataset.value;
    b.classList.toggle('selected', chosen);
    b.setAttribute('aria-pressed', String(chosen));
  }
  for (const b of document.querySelectorAll('[data-action=on],[data-action=off]'))
    b.classList.toggle(
      'selected',
      available && !posting && !unknown && s.power === b.dataset.action && state.can_control,
    );
  for (const b of document.querySelectorAll('[data-preset]')) {
    const selected =
      available && !posting && !unknown && s.scene === b.dataset.preset && state.can_control;
    b.classList.toggle('selected', selected);
    b.setAttribute('aria-pressed', String(selected));
  }
  update(
    'light-message',
    !available
      ? !reachable
        ? 'This website is not answering. Check the network, then reload the page.'
        : state?.detail || 'Panel unavailable. Controls are disabled.'
      : state.experiment?.running
        ? 'Instructions are running. Pause Experiment mode before using lighting.'
        : !state.can_control && ['original', 'black', 'experiment'].includes(state.mode)
          ? 'Return the touch panel to Home to use lighting.'
          : s.programme
            ? 'Manual lighting stops programmes before applying.'
            : s.message || 'Lighting unavailable.',
  );
  update(
    'light-recent',
    'Recent settings: ' +
      (s.recent || 'Not checked') +
      (s.confirmed_age_s === null || s.confirmed_age_s === undefined
        ? ''
        : ' · ' +
          (s.confirmed_age_s < 60 ? 'just now' : Math.floor(s.confirmed_age_s / 60) + ' min ago')),
  );
  const e = state?.experiment;
  if (e) {
    update('profile-title', e.profile.title);
    update('instruction', e.profile.stages[e.stage]);
    update(
      'elapsed',
      Math.floor(e.elapsed_s / 60)
        .toString()
        .padStart(2, '0') +
        ':' +
        (e.elapsed_s % 60).toString().padStart(2, '0'),
    );
    update(
      'session-state',
      'Instruction ' +
        (e.stage + 1) +
        ' of ' +
        e.profile.stages.length +
        ' · ' +
        (e.running ? 'Running' : 'Paused'),
    );
    update('annotation', e.annotation);
    if ($('marks') && !$('marks').children.length)
      for (const label of e.profile.annotations) {
        const b = button(label, () => command('mark', { label }), { action: 'mark' });
        b.disabled = posting || Boolean(unknown) || !available || !state.can_session;
        $('marks').append(b);
      }
  }
  update('schedule-light_at', minutes(p.light_at ?? 420));
  update('schedule-dark_at', minutes(p.dark_at ?? 1140));
  const h = state?.health;
  if (h) {
    update(
      'panel-memory',
      h.error
        ? 'Resource reading unavailable'
        : `Memory: ${h.ram_available ?? '—'} / ${h.ram_total ?? '—'} MiB free`,
    );
    update(
      'panel-storage',
      h.error
        ? ''
        : `Storage: ${h.disk_available ?? '—'} GiB free · CPU: ${h.temperature ?? '—'} °C`,
    );
    update('panel-power', h.power ? 'Power: ' + h.power : 'Power reading unavailable');
    $('panel-power')?.classList.toggle('system-warning', h.power?.startsWith('Current') === true);
  }
  update('room-health', state?.room_status || 'No current room observation.');
  syncPower();
  weather();
}
function minutes(value) {
  return (
    Math.floor(value / 60)
      .toString()
      .padStart(2, '0') +
    ':' +
    (value % 60).toString().padStart(2, '0')
  );
}
function weather() {
  const p = state?.preferences || {},
    value = state?.weather,
    tz = state?.timezone || 'America/New_York',
    now = new Date();
  update(
    'clock',
    new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      hour: 'numeric',
      minute: '2-digit',
      hour12: p.clock !== '24',
    }).format(now),
  );
  update(
    'date',
    new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    }).format(now),
  );
  if (!value) {
    update('condition', 'Weather unavailable');
    update('temperature', '—');
    update(
      'weather-source',
      'No current outdoor reading. Outdoor weather is separate from room sensors.',
    );
    if ($('weather-stats')) $('weather-stats').hidden = true;
    if ($('weather-notice')) {
      $('weather-notice').hidden = false;
      update('weather-notice', 'No current outdoor reading.');
    }
    if ($('daylight')) $('daylight').hidden = true;
    if ($('weather-art')) {
      $('weather-art').replaceChildren();
      delete $('weather-art').dataset.symbol;
    }
    return;
  }
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', {
      timeZone: tz,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    })
      .formatToParts(now)
      .map((v) => [v.type, v.value]),
  );
  const today = `${parts.year}-${parts.month}-${parts.day}`,
    local = `${today}T${parts.hour}:${parts.minute}`,
    current = value.sunrise.slice(0, 10) === today && value.sunset.slice(0, 10) === today,
    night = current && (local < value.sunrise || local >= value.sunset),
    old =
      !current ||
      value.model_time.slice(0, 10) !== today ||
      (state.weather_age_s ?? Infinity) > 1800;
  const unit = p.temperature || 'f',
    convert = (v) => (unit === 'c' ? ((v - 32) * 5) / 9 : v),
    degree = (v) => Math.round(convert(v)) + '°';
  update('temperature', degree(value.temperature_f) + ' ' + unit.toUpperCase());
  update('condition', value.condition);
  if ($('weather-stats')) $('weather-stats').hidden = old;
  if ($('weather-notice')) $('weather-notice').hidden = !old;
  update('weather-notice', old ? 'Earlier reading: ' + value.model_time.replace('T', ' ') : '');
  for (const [key, reading, isRain] of [
    ['feels', value.feels_like_f, false],
    ['rain', value.rain_chance, true],
    ['high', value.high_f, false],
    ['low', value.low_f, false],
  ])
    update(
      'weather-' + key,
      Number.isFinite(reading) ? (isRain ? Math.round(reading) + '%' : degree(reading)) : '—',
    );
  update(
    'weather-source',
    'Open-Meteo · model ' +
      value.model_time.replace('T', ' ') +
      ' · Outdoor weather is separate from room sensors.',
  );
  let name =
    value.code === 0
      ? night
        ? 'moon'
        : 'sun'
      : [1, 2].includes(value.code)
        ? night
          ? 'cloud-moon'
          : 'cloud-sun'
        : value.code === 3
          ? 'cloud'
          : [45, 48].includes(value.code)
            ? 'cloud-fog'
            : [71, 73, 75, 77, 85, 86].includes(value.code)
              ? 'cloud-snow'
              : [95, 96, 99].includes(value.code)
                ? 'cloud-lightning'
                : [51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82].includes(value.code)
                  ? 'cloud-rain'
                  : 'circle-question-mark';
  if (!current && [0, 1, 2].includes(value.code)) name = 'circle-question-mark';
  if ($('weather-art')) {
    $('weather-art').style.color =
      state?.palette?.[content.weather_accents?.[name] || 'icon_colour'] || 'var(--icon-colour)';
    if ($('weather-art').dataset.symbol !== name) {
      $('weather-art').replaceChildren(icon('weather-' + name));
      $('weather-art').dataset.symbol = name;
    }
  }
  if ($('daylight')) {
    $('daylight').hidden = old;
    if (!old) {
      const minute = (s) => Number(s.slice(11, 13)) * 60 + Number(s.slice(14, 16)),
        rise = minute(value.sunrise),
        set = minute(value.sunset),
        time = Number(parts.hour) * 60 + Number(parts.minute);
      $('daylight-fill').style.width =
        Math.max(0, Math.min(1, (time - rise) / (set - rise))) * 100 + '%';
      const remaining = (time < rise ? rise : set) - time;
      update(
        'daylight-label',
        time >= set
          ? 'After sunset · night'
          : `Sun ${time < rise ? 'rises' : 'sets'} in ${Math.floor(remaining / 60)} h ${remaining % 60} min`,
      );
      update('sunrise', 'Sunrise ' + value.sunrise.slice(11, 16));
      update('sunset', 'Sunset ' + value.sunset.slice(11, 16));
    }
  }
}
let fetching = false,
  failures = 0;
async function refresh() {
  if (fetching || document.hidden) return;
  fetching = true;
  try {
    const response = await fetch('/api/controller', {
      cache: 'no-store',
      signal: AbortSignal.timeout(3500),
    });
    if (!response.ok) throw Error();
    state = await response.json();
    reachable = true;
    failures = 0;
    if (unknown && state.session && unknownSession && state.session !== unknownSession) {
      // The panel restarted, so the old receipt can no longer be found. The panel now owns
      // the current light state; show it rather than locking this page indefinitely.
      unknown = null;
      message('The panel restarted. Check the current settings before trying again.');
    }
    const receipt = unknown && state.receipts?.find((r) => r.id === unknown);
    if (receipt) {
      if (powerRequest?.id === unknown) {
        if (receipt.ok) {
          powerRequest.accepted = true;
          powerChoice = null;
          if ($('power-confirmation')) $('power-confirmation').hidden = true;
          message('The panel received the power request. Check its progress below.');
        } else {
          powerRequest = null;
          message(receipt.detail || 'Power request was not accepted.');
        }
      } else message('The panel received the command. Check its current confirmation below.');
      unknown = null;
    }
    if (powerRequest && state.power?.phase === 'failed') {
      powerRequest = null;
      message(state.power.message || 'Power operation stopped. The panel remains available.');
    }
    if (
      powerRequest?.accepted &&
      state.available === true &&
      state.session !== powerRequest.session &&
      state.power?.phase === 'ready'
    ) {
      const operation = powerRequest.operation;
      powerRequest = null;
      message(
        operation === 'reboot'
          ? 'Panel restarted. This website is connected again.'
          : 'The panel is back online. This website is connected again.',
      );
    }
    if (state.guide) content = { ...content, guide: state.guide, help: state.help };
    if (
      !view ||
      (!$('help-topic') && view === 'tools-system') ||
      (view.startsWith('guide') && !$('app').children.length)
    ) {
      view = '';
      layout();
    }
    sync();
  } catch (_) {
    reachable = false;
    failures++;
    if (state) state.available = false;
    if (powerRequest?.accepted)
      message(
        powerRequest.operation === 'reboot'
          ? 'The panel is restarting. This website will reconnect when it is ready.'
          : 'The panel is shutting down. This website will disconnect until the panel is powered on again.',
      );
    sync();
  } finally {
    fetching = false;
  }
}
// Only explicit buttons change the panel; moving around this website never does.
$('legacy-return').onclick = () => command('home');
window.addEventListener('hashchange', layout);
phoneLayout.addEventListener('change', () => {
  if ($('blind-group')) $('blind-group').open = !phoneLayout.matches;
});
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) refresh();
});
window.addEventListener('scr-preview-change', () => {
  view = '';
  layout();
});
(async () => {
  try {
    content = await (await fetch('/room-content.json')).json();
  } catch (_) {}
  layout();
  // Poll every second; slow to every 5 s while the website is not answering.
  for (;;) {
    await refresh();
    await new Promise((done) => setTimeout(done, failures > 2 ? 5000 : 1000));
  }
})();
setInterval(weather, 1000);
