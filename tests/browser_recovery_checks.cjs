// Exercise the shipped website against a simulated owner; no browser or room access.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../browser/room.js'), 'utf8');

function website() {
  const elements = new Map();
  for (const id of ['legacy-return', 'message', 'connection', 'legacy-banner', 'panel-mode-message',
    'light-message', 'light-recent', 'lighting-recovery', 'recovery-title', 'recovery-detail',
    'recovery-staff', 'check-connection']) {
    elements.set(id, {dataset: {}, textContent: '', hidden: false});
  }
  elements.get('lighting-recovery').dataset.always = 'false';
  const actions = ['on', 'off', 'programme', 'legacy', 'check_connection'].map(action => ({
    dataset: {action, programme: 'Stop'}, setAttribute() {}, removeAttribute() {},
  }));
  const requests = [];
  let snapshot = {available: true, session: 'owner-one', revision: 'one', csrf: 'local',
    mode: 'room', can_control: false, lights: {state: 'failed', capabilities: {programmes: true}},
    lighting_recovery: {status: 'needs_staff', title: 'Lighting result unconfirmed',
      detail: 'Check the current fixtures before changing lighting.', can_check: true, needs_staff: true}};
  let lostCheck = false, offline = false;
  const context = vm.createContext({
    document: {getElementById: id => elements.get(id) || null,
      querySelectorAll: selector => selector === '[data-action]' ? actions : [],
      addEventListener() {}, hidden: false},
    window: {addEventListener() {}}, matchMedia: () => ({addEventListener() {}}),
    setInterval() {}, setTimeout() {return 1;}, clearTimeout() {},
    crypto: require('node:crypto').webcrypto, AbortSignal,
    fetch: async (url, options) => {
      if (url === '/room-content.json') return new Promise(() => {});
      if (url === '/api/controller') {
        if (offline) throw Error('Website disconnected');
        return {ok: true, json: async () => structuredClone(snapshot)};
      }
      const request = JSON.parse(options.body);
      requests.push(request);
      if (lostCheck) throw Error('Lost check reply');
      return {ok: true, status: 202, json: async () => ({ok: true, code: 202, id: request.id})};
    },
  });
  vm.runInContext(source, context);
  vm.runInContext("view = 'home';", context);
  return {requests, actions, elements, run: script => vm.runInContext(script, context),
    state: value => {snapshot = {...snapshot, ...value};},
    loseCheck: () => {lostCheck = true;}, offline: () => {offline = true;}};
}

(async () => {
  const site = website();
  await site.run('refresh()');
  assert.equal(site.elements.get('lighting-recovery').hidden, false);
  assert.equal(site.elements.get('recovery-title').textContent, 'Lighting result unconfirmed');
  assert.equal(site.actions.find(b => b.dataset.action === 'check_connection').disabled, false);
  site.run("unknown = 'original-command'; unknownSession = 'owner-one'; unknownAction = 'off'; sync();");
  assert.equal(site.actions.find(b => b.dataset.action === 'off').disabled, true);
  assert.equal(site.actions.find(b => b.dataset.action === 'check_connection').disabled, false,
    'Read-only checking can be allowed while the actuator receipt is unknown');
  assert.equal(await site.run("command('check_connection')"), true);
  assert.equal(site.requests[0].action, 'check_connection');
  assert.deepEqual(site.requests[0].arguments, {});
  assert.notEqual(site.requests[0].id, 'original-command');
  assert.equal(site.run('unknown'), 'original-command', 'Checking never clears an old unknown receipt');
  assert.equal(await site.run("command('off')"), false);
  assert.equal(site.requests.length, 1, 'No actuator command is repeated after checking');

  site.loseCheck();
  assert.equal(await site.run("command('check_connection')"), false);
  assert.equal(site.run('unknown'), 'original-command', 'A lost check reply preserves the original lock');
  assert.match(site.elements.get('message').textContent, /No light change was sent/);
  const clean = website();
  await clean.run('refresh()');
  clean.loseCheck();
  await clean.run("command('check_connection')");
  assert.equal(clean.run('unknown'), null, 'A read-only check cannot create actuator uncertainty');

  for (const status of ['reserved', 'releasing', 'returning', 'checking']) {
    const reserved = website();
    reserved.state({can_control: true, lights: {state: 'ready', capabilities: {programmes: true}},
      lighting_recovery: {status, title: 'Lighting reserved for an experiment',
        detail: 'Everyday lighting returns when the experiment releases control.', can_check: true}});
    await reserved.run('refresh()');
    for (const action of ['on', 'off', 'programme', 'legacy'])
      assert.equal(reserved.actions.find(b => b.dataset.action === action).disabled, true,
        `${status} blocks ${action}, even with an older can_control value`);
    assert.equal(reserved.elements.get('check-connection').hidden, true);
    assert.equal(await reserved.run("command('check_connection')"), false,
      'An experiment reservation blocks fixture queries even if can_check is stale');
    assert.equal(reserved.requests.length, 0);
    assert.equal(reserved.elements.get('connection').dataset.state, 'waiting');
    assert.equal(reserved.elements.get('lighting-recovery').hidden, false);
    assert.equal(reserved.elements.get('recovery-staff').hidden, true);
  }

  const connection = website();
  connection.state({lighting_recovery: {status: 'offline', title: 'Lighting service unavailable',
    detail: 'Ask the room host to check the lighting service.', can_check: true}});
  await connection.run('refresh()');
  assert.equal(connection.elements.get('connection').textContent, 'Lighting unavailable');
  assert.equal(connection.elements.get('recovery-title').textContent, 'Lighting service unavailable');
  connection.offline();
  await connection.run('refresh()');
  assert.equal(connection.elements.get('connection').textContent, 'Website offline');
  assert.equal(connection.elements.get('recovery-title').textContent, 'Website offline');
  assert.equal(connection.elements.get('check-connection').hidden, true);
  assert.match(connection.elements.get('recovery-detail').textContent, /reconnects automatically/);
  assert.equal(connection.requests.length, 0);
  for (const [status, expected] of [['writing', 'Sending'], ['legacy', 'Legacy']]) {
    const display = website();
    display.state({lighting_recovery: {status, title: expected, detail: 'Current owner is busy.',
      can_check: false, write_blocked: true}});
    await display.run('refresh()');
    assert.equal(display.elements.get('connection').textContent, expected);
  }
  const legacyHeld = website();
  legacyHeld.state({lighting_recovery: {status: 'needs_staff', title: 'Legacy still owns lighting',
    detail: 'Use Legacy for room controls until the room host checks programmes and pending commands.',
    can_check: false, needs_staff: true, write_blocked: true}});
  await legacyHeld.run('refresh()');
  assert.equal(legacyHeld.elements.get('connection').textContent, 'Legacy still owns lighting');
  assert.equal(legacyHeld.elements.get('check-connection').hidden, true);
  assert.match(legacyHeld.elements.get('recovery-detail').textContent, /Use Legacy for room controls/);
  console.log('Browser recovery states, ownership guards and read-only checks passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
