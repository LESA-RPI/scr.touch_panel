// Exercise the shipped command/receipt logic using Node's standard library only.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../browser/room.js'), 'utf8');

function website(respond, snapshot = () => ({available:true, session:'owner-one', revision:'one'})) {
  const elements = new Map();
  for (const id of ['legacy-return', 'message', 'connection', 'legacy-banner', 'panel-mode-message', 'light-message', 'light-recent', 'blind-permission', 'gradient-controls', 'programme-controls', 'programmes-unavailable', 'programme-status'])
    elements.set(id, {dataset:{}, textContent:''});
  const commands = [];
  const actionButtons = [];
  const context = vm.createContext({
    document: {getElementById:id => elements.get(id) || null, querySelectorAll:selector => selector === '[data-action]' ? actionButtons : [], addEventListener() {}, hidden:false},
    window: {addEventListener() {}}, matchMedia:() => ({addEventListener() {}}),
    setInterval() {}, setTimeout() {return 1;}, clearTimeout() {},
    crypto: require('node:crypto').webcrypto, AbortSignal,
    fetch:async (url, options) => {
      if (url === '/room-content.json') return new Promise(() => {}); // Leave initial rendering idle.
      if (url === '/api/controller') return {ok:true, json:async () => snapshot()};
      const request = JSON.parse(options.body);
      commands.push(request);
      return respond(request, context);
    },
  });
  vm.runInContext(source, context);
  context.shippedSync = vm.runInContext('sync', context);
  vm.runInContext("sync = () => {}; state = {available:true, session:'owner-one', revision:'one', csrf:'local'}; view='home';", context);
  return {context, commands, actionButtons, run:script => vm.runInContext(script, context)};
}

(async () => {
  for (const [status, body] of [[503,{ok:false,code:503,detail:'Receipt unknown; do not retry.'}], [200,{}], [202,{ok:true,code:202,id:'other-command'}]]) {
    const site = website(() => ({status, ok:status<400, json:async () => body}));
    assert.equal(await site.run("command('off')"), false);
    assert.equal(await site.run("command('on')"), false);
    assert.equal(site.commands.length, 1, 'An ambiguous reply must not enable a second command');
    assert.match(site.run("$('message').textContent"), /unknown/);
  }
  const rejected = website(() => ({status:409,ok:false,json:async () => ({ok:false,code:409,detail:'Review the current settings.'})}));
  await rejected.run("command('off')");
  await rejected.run("command('off')");
  assert.equal(rejected.commands.length, 2, 'A known rejection allows a newly reviewed action');

  let receipt;
  const recovered = website(request => {receipt={id:request.id,ok:true,code:202};return {status:503,ok:false,json:async () => ({ok:false,code:503})};}, () => ({available:true,session:'owner-one',revision:'two',receipts:receipt?[receipt]:[]}));
  await recovered.run("command('off')");
  assert.equal(recovered.run('unknown'), null, 'A matching owner receipt resolves the uncertainty');

  const restarted = website((request, context) => {
    vm.runInContext("state = {available:true, session:'owner-two', revision:'new'}", context);
    return Promise.reject(new Error('Lost reply while owner restarted'));
  }, () => ({available:true,session:'owner-two',revision:'new'}));
  await restarted.run("command('off')");
  assert.equal(restarted.run('unknown'), null, 'Restart recovery uses the session at send time');
  assert.match(restarted.run("$('message').textContent"), /restarted/);

  const display = website(() => {throw Error('Presentation must not send commands');});
  for (const mode of ['guide', 'settings', 'health', 'about', 'experiment', 'classic']) {
    display.run(`state = {available:true, mode:${JSON.stringify(mode)}, can_control:true, lights:{message:'Light settings confirmed.'}}; shippedSync();`);
    assert.equal(display.run("$('legacy-banner').hidden"), true);
    assert.equal(display.run("$('light-message').textContent"), 'Light settings confirmed.');
    if (mode === 'classic') assert.equal(display.run("$('connection').textContent"), 'Classic view');
  }
  for (const mode of ['original', 'black']) {
    display.run(`state = {available:true, mode:${JSON.stringify(mode)}, can_control:false, lights:{}}; shippedSync();`);
    assert.equal(display.run("$('legacy-banner').hidden"), false);
    assert.match(display.run("$('light-message').textContent"),
      mode === 'original' ? /Use Legacy on the touch panel/ : /Return the touch panel to Home/);
    if (mode === 'original') {
      assert.equal(display.run("$('connection').textContent"), 'Legacy');
      assert.match(display.run("$('panel-mode-message').textContent"), /separate original application/);
    }
  }
  display.run("state = {available:true, mode:'room', can_control:true, lights:{}, blinds:{connected:true}}; shippedSync();");
  assert.equal(display.run("$('blind-permission').hidden"), false, 'Connected blind settings appear without rebuilding the page');
  display.run('state.blinds.connected = false; shippedSync();');
  assert.equal(display.run("$('blind-permission').hidden"), true, 'Disconnected blind settings hide without rebuilding the page');
  const start = {dataset:{action:'programme', programme:'Sun'}},
    stop = {dataset:{action:'programme', programme:'Stop'}},
    gradient = {dataset:{action:'gradient'}};
  display.actionButtons.push(start, stop, gradient);
  display.run("state = {available:true, mode:'room', can_control:false, lights:{state:'failed', capabilities:{gradient:true, programmes:true}}}; shippedSync();");
  assert.equal(start.disabled, true);
  assert.equal(gradient.disabled, true);
  assert.equal(stop.disabled, false, 'Stop remains usable without lighting readiness');
  assert.equal(display.run("$('programme-controls').hidden"), false);
  display.run('state.can_control = true; shippedSync();');
  assert.equal(start.disabled, false);
  assert.equal(gradient.disabled, false);
  display.run('state.lights.capabilities = {}; shippedSync();');
  assert.equal(display.run("$('gradient-controls').hidden"), true);
  assert.equal(display.run("$('programme-controls').hidden"), true);
  assert.equal(stop.disabled, true);
  display.run("state.lights.state = 'ready'; state.lights.programme = 'Sun'; shippedSync();");
  assert.equal(display.run("$('light-message').textContent"), 'Manual lighting stops programmes before applying.');
  for (const name of ['Sun', 'Circ', 'Stop']) {
    const programme = website(request => ({status:202,ok:true,json:async () => ({ok:true,code:202,id:request.id})}));
    assert.equal(await programme.run(`command('programme', {name:${JSON.stringify(name)}})`), true);
    assert.equal(programme.commands[0].arguments.name, name);
    assert.match(programme.run("$('message').textContent"), /requested.*not confirmed/);
  }
  const original = website(request => ({status:202,ok:true,json:async () => ({ok:true,code:202,id:request.id})}));
  assert.equal(await original.run("command('original_fallback')"), true);
  assert.equal(original.commands[0].action, 'original_fallback');
  assert.deepEqual(original.commands[0].arguments, {});
  const legacyView = {dataset:{action:'legacy'}},
    originalFallback = {dataset:{action:'original_fallback'}};
  display.actionButtons.push(legacyView, originalFallback);
  display.run("state = {available:true, mode:'experiment', can_control:false, lights:{}, experiment:{running:true, profile:{title:'Practice', stages:['Instruction'], annotations:[]},stage:0,elapsed_s:0}}; shippedSync();");
  assert.equal(legacyView.disabled, true, 'Original Legacy is blocked during instructions');
  assert.equal(originalFallback.disabled, true, 'Separate Original fallback is blocked during instructions');
  assert.equal(display.commands.length, 0);
  console.log('Browser receipt ambiguity, rejection, recovery and restart checks passed');
})().catch(error => {console.error(error);process.exitCode=1;});
