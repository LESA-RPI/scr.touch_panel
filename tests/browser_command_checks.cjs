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

function profileWebsite(respond = request => ({status:202, ok:true, json:async () => ({ok:true, code:202, id:request.id})})) {
  let site;
  site = website(respond, () => JSON.parse(site.run('JSON.stringify(state)')));
  site.run(`
    const profileElements = new Map(['profile-file', 'profile-preview', 'profile-download', 'profile-status', 'profile-load', 'marks'].map(id => [id, {
      textContent:'', value:'', dataset:{}, children:[],
      replaceChildren(...children) {this.children = children;},
      append(...children) {this.children.push(...children);},
    }]));
    const originalGet = document.getElementById;
    document.getElementById = id => profileElements.get(id) || originalGet(id);
    document.createElement = tag => ({
      tagName:tag, dataset:{}, children:[], textContent:'',
      setAttribute(name, value) {this[name] = value;}, append(...children) {this.children.push(...children);},
    });
    content.default_profile = {title:'Default instructions', sensors:'Room sensors', stages:['Sit still'], annotations:['Started']};
    state = {available:true, session:'owner-one', revision:'one', csrf:'local', can_session:true,
      experiment:{profile:content.default_profile, can_load_profile:true, running:false, stage:0, elapsed_s:0}};
    function chooseProfile(value, name = 'instructions.json', size = 200) {
      return previewProfile({name, size, text:async () => JSON.stringify(value)}, $('profile-file'));
    }
  `);
  return site;
}

function diagnosticsWebsite(respond) {
  let site;
  site = website(respond, () => JSON.parse(site.run('JSON.stringify(state)')));
  site.run("state.room_diagnostics = {state:'available', can_check:true, checking:false, services:[]};");
  return site;
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

  const diagnostics = diagnosticsWebsite((request, context) => {
    vm.runInContext('state.room_diagnostics.checking = true; state.room_diagnostics.can_check = false;', context);
    return {status:202, ok:true, json:async () => ({ok:true, code:202, id:request.id})};
  });
  diagnostics.run("unknown = 'light-receipt'; unknownSession = 'owner-one'; unknownAction = 'off'; state.busy = true; setTimeout = fn => {noticeTimeout = fn; return 1;};");
  assert.equal(await diagnostics.run("command('refresh_status')"), true, 'A metadata check remains usable while lighting is unconfirmed');
  assert.equal(diagnostics.run('unknown'), 'light-receipt');
  assert.equal(diagnostics.run('unknownAction'), 'off');
  assert.deepEqual(diagnostics.commands[0].arguments, {});
  assert.match(diagnostics.run("$('message').textContent"), /diagnostics check requested/);
  diagnostics.run('noticeTimeout();');
  assert.equal(diagnostics.run("$('message').hidden"), true, 'Routine diagnostics acknowledgements fade');
  assert.equal(await diagnostics.run("command('refresh_status')"), false, 'An in-flight status worker cannot be queued again');
  assert.equal(await diagnostics.run("command('on')"), false, 'A status check does not release an uncertain lighting command');
  assert.equal(diagnostics.commands.length, 1);
  for (const setup of ['state.available = false', 'reachable = false', 'posting = true', 'state.room_diagnostics.can_check = false', 'state.room_diagnostics.checking = true']) {
    const blocked = diagnosticsWebsite(() => {throw Error('A blocked diagnostics check must not be posted');});
    blocked.run(setup);
    assert.equal(await blocked.run("command('refresh_status')"), false);
    assert.equal(blocked.commands.length, 0);
  }
  for (const respond of [
    () => Promise.reject(new Error('Reply lost')),
    () => ({status:503, ok:false, json:async () => null}),
  ]) {
    const failed = diagnosticsWebsite(respond);
    failed.run("unknown = 'light-receipt'; unknownAction = 'off'; unknownSession = 'owner-one';");
    assert.equal(await failed.run("command('refresh_status')"), false);
    assert.equal(failed.run('unknown'), 'light-receipt');
    assert.equal(failed.run('unknownAction'), 'off');
    assert.equal(failed.run('messageTimer'), null, 'An unconfirmed diagnostic acknowledgement stays visible');
    assert.match(failed.run("$('message').textContent"), /diagnostics check could not be confirmed/);
  }
  const diagnosticRows = diagnosticsWebsite(() => {throw Error('Rendering room observations must not post');});
  diagnosticRows.run(`
    const diagnosticsElements = new Map(['room-diagnostics-services', 'room-diagnostics-status', 'room-diagnostics-observed', 'room-diagnostics-check'].map(id => [id, {
      textContent:'', dataset:{}, children:[], replaceChildren(...children) {this.children = children;}, append(...children) {this.children.push(...children);},
    }]));
    const originalGet = document.getElementById;
    document.getElementById = id => diagnosticsElements.get(id) || originalGet(id);
    document.createElement = tag => ({tagName:tag, textContent:'', children:[], append(...children) {this.children.push(...children);}});
    state.room_diagnostics = {state:'available', can_check:true, checking:false, observed_at:'2026-10-30T15:00:00Z', age_s:20,
      services:[{name:'Lighting', state:'listed'}, {name:'Environment', state:'missing'}]};
    syncRoomDiagnostics();
  `);
  assert.equal(diagnosticRows.run("$('room-diagnostics-services').children[0].children[1].textContent"), 'Advertised');
  assert.equal(diagnosticRows.run("$('room-diagnostics-services').children[1].children[1].textContent"), 'Missing');
  diagnosticRows.run("state.room_diagnostics.state = 'unavailable'; state.room_diagnostics.detail = 'Room connection timed out.'; state.room_diagnostics.age_s = 180; syncRoomDiagnostics();");
  assert.equal(diagnosticRows.run("$('room-diagnostics-services').children[0].children[1].textContent"), 'Advertised', 'A failed recheck retains the last successful registration observation');
  assert.match(diagnosticRows.run("$('room-diagnostics-status').textContent"), /latest room check failed.*timed out.*Earlier results/);
  assert.match(diagnosticRows.run("$('room-diagnostics-observed').textContent"), /3 min ago/);
  assert.equal(diagnosticRows.commands.length, 0);

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

  const navigation = website(() => {throw Error('Browsing must not send commands');});
  navigation.run(`
    const anchors = ['#home', '#tools-lighting', '#guide'].map(hash => ({
      hash, setAttribute(name, value) {this[name] = value;},
    }));
    const main = {replaceChildren() {}, querySelector() {return null;}};
    const originalGet = document.getElementById;
    document.getElementById = id => id === 'app' ? main : originalGet(id);
    document.querySelectorAll = selector => selector === '.header a' ? anchors : [];
    location = {hash:'#tools-lighting-scenes', pathname:'/'};
    home = tools = guide = () => {};
    view = '';
    layout();
  `);
  assert.equal(navigation.run('anchors[1]["aria-current"]'), 'page');
  navigation.run("location.hash = '#guide-1'; layout();");
  assert.equal(navigation.run('anchors[1].hash'), '#tools-lighting-scenes', 'Guide browsing retains the last Lighting tab');
  assert.equal(navigation.run('anchors[2]["aria-current"]'), 'page');
  navigation.run('location.hash = anchors[1].hash; layout();');
  assert.equal(navigation.run('view'), 'tools-lighting-scenes');
  assert.equal(navigation.run('anchors[2].hash'), '#guide-1', 'Opening a tool preserves the last guide topic');
  navigation.run('location.hash = anchors[2].hash; layout();');
  assert.equal(navigation.run('view'), 'guide-1');
  assert.equal(navigation.run('anchors[2]["aria-current"]'), 'page');
  navigation.run("location.hash = '#tools-system'; layout(); location.hash = '#home'; layout();");
  assert.equal(navigation.run('anchors[1].hash'), '#tools-system', 'Home retains the last Room tool');
  assert.equal(navigation.run('anchors[2].hash'), '#guide-1', 'Home retains the last guide topic');
  assert.equal(navigation.run('anchors[0]["aria-current"]'), 'page');
  navigation.run("location.hash = '#guide'; layout(); location.hash = '#home'; layout();");
  assert.equal(navigation.run('anchors[2].hash'), '#guide', 'All topics becomes the remembered guide destination');
  assert.equal(navigation.commands.length, 0);

  const guideContent = website(() => {throw Error('Guide links must not send commands');});
  guideContent.context.generatedContent = JSON.parse(fs.readFileSync(path.join(__dirname, '../browser/room-content.json'), 'utf8'));
  guideContent.run(`
    content = generatedContent;
    function guideNode(tag) {
      return {tagName:tag, children:[], dataset:{}, style:{}, textContent:'',
        append(...children) {this.children.push(...children);},
        prepend(...children) {this.children.unshift(...children);},
        replaceChildren(...children) {this.children = children;},
        classList:{toggle(name, value) {this[name] = value;}},
        setAttribute(name, value) {this[name] = value;},
      };
    }
    document.createElement = guideNode;
    document.createElementNS = (namespace, tag) => ({...guideNode(tag), namespaceURI:namespace});
    function descendants(node) {return [node, ...node.children.flatMap(descendants)];}
    const topicLinks = [];
    for (const section of ['room', 'controls']) {
      const topicIndex = guideNode('main');
      guide(topicIndex, -1, section);
      topicLinks.push(...descendants(topicIndex).filter(node => node.className === 'topic'));
    }
  `);
  const sharedTopics = guideContent.context.generatedContent.guide;
  assert.equal(guideContent.run('topicLinks.length'), sharedTopics.length);
  for (const [index, topic] of sharedTopics.entries()) {
    assert.equal(guideContent.run(`topicLinks.filter(node => node.href === '#guide-${index}').length`), 1);
    assert.equal(guideContent.run(`topicLinks.find(node => node.href === '#guide-${index}').children.find(node => node.tagName === 'small').textContent`), topic.caption);
    guideContent.run(`const topic${index} = guideNode('main'); guide(topic${index}, ${index});`);
    const destinations = guideContent.run(`descendants(topic${index}).filter(node => node.className === 'topic-destination')`);
    assert.deepEqual(Array.from(destinations, node => [node.textContent, node.href]),
      topic.links.map(destination => [destination.label, '#' + (destination.page === 'home' ? 'home' : 'tools-' + destination.page)]));
    assert.equal(destinations.every(node => node.onclick === undefined), true, 'Guide destinations use ordinary navigation links');
  }
  assert.equal(guideContent.commands.length, 0);
  guideContent.context.ceilingReference = JSON.parse(fs.readFileSync(path.join(__dirname, '../app/ceiling_map.json'), 'utf8'));
  guideContent.run(`
    content.ceiling_map = ceilingReference;
    state = null;
    reachable = false;
    const ceilingRoot = guideNode('main');
    ceilingMap(ceilingRoot);
    const familyControls = descendants(ceilingRoot).filter(node => node.tagName === 'button');
    const ceilingDiagram = descendants(ceilingRoot).find(node => node.tagName === 'svg');
    const familyDescription = descendants(ceilingRoot).find(node => node.className === 'ceiling-map-description');
  `);
  assert.equal(guideContent.run('familyControls.length'), 3);
  for (const [index, family] of guideContent.context.ceilingReference.families.entries()) {
    const expected = {color:53, combo:40, irma:18}[family.id];
    assert.equal(family.positions.length, expected, 'The map keeps the recorded family totals');
    assert.equal(new Set(family.positions.map(position => position.join(','))).size, expected);
    assert.ok(family.positions.every(([column, row]) => Number.isInteger(column) && column >= 1 && column <= 14 && Number.isInteger(row) && row >= 1 && row <= 5));
    guideContent.run(`familyControls[${index}].onclick();`);
    assert.equal(guideContent.run("ceilingDiagram.children.filter(node => node.tagName === 'circle').length"), expected);
    assert.match(guideContent.run('familyDescription.textContent'), new RegExp(family.label + '.*' + expected));
    assert.equal(guideContent.run(`familyControls[${index}]['aria-pressed']`), 'true');
    assert.match(guideContent.run("ceilingDiagram['aria-label']"), /reference grid cells.*not live status/);
  }
  guideContent.run("const irmaDots = ceilingDiagram.children.filter(node => node.tagName === 'circle');");
  assert.ok(guideContent.run('irmaDots[0].cy > irmaDots[2].cy'), 'Row 1 is displayed below row 5');
  assert.equal(guideContent.commands.length, 0, 'Changing reference-map families works offline without hardware commands');
  guideContent.run(`
    const channelsRoot = guideNode('main'), distanceRoot = guideNode('main');
    guideVisual(channelsRoot, 'channels');
    guideVisual(distanceRoot, 'distance');
    const channelSwatches = descendants(channelsRoot).filter(node => node.className === 'guide-channel-colour');
    const distanceGrids = descendants(distanceRoot).filter(node => node.tagName === 'svg');
  `);
  assert.equal(guideContent.run('channelSwatches.length'), 8);
  assert.deepEqual(Array.from(guideContent.run('channelSwatches'), node => node.style.backgroundColor),
    guideContent.context.generatedContent.channels.map(channel => channel.colour));
  assert.equal(guideContent.run('distanceGrids.length'), 2);
  assert.match(guideContent.run("distanceGrids[0]['aria-label']"), /COMBO: 8 rows by 8 columns.*without live readings/);
  assert.match(guideContent.run("distanceGrids[1]['aria-label']"), /IRMA: 25 rows by 20 columns.*without live readings/);
  assert.equal(guideContent.commands.length, 0, 'Static learning visuals need no equipment connection');

  const homeState = website(() => {throw Error('Updating Home must not send commands');});
  homeState.run(`
    const homeElements = new Map(['blind-group', 'blind-status', 'essentials'].map(id => [id, {
      textContent:'', classList:{toggle() {}},
    }]));
    const originalGet = document.getElementById;
    document.getElementById = id => homeElements.get(id) || originalGet(id);
    const powerButtons = ['on', 'off'].map(action => ({
      dataset:{action}, classList:{toggle(name, value) {this[name] = Boolean(value);}},
      setAttribute(name, value) {this[name] = value;}, removeAttribute(name) {delete this[name];},
    }));
    document.querySelectorAll = selector => selector === '[data-action=on],[data-action=off]' ? powerButtons : [];
    state = {available:true, can_control:true, lights:{power:'on'}, blinds:{reason:'Controls locked in settings'}};
    shippedSync();
  `);
  assert.equal(homeState.run("$('blind-status').textContent"), 'Controls locked in settings');
  assert.equal(homeState.run('powerButtons[0]["aria-pressed"]'), 'true');
  assert.equal(homeState.run('powerButtons[1]["aria-pressed"]'), 'false');
  homeState.run("state.blinds.reason = 'Controller not connected'; posting = true; shippedSync();");
  assert.equal(homeState.run("$('blind-status').textContent"), 'Controller not connected');
  assert.equal(homeState.run('powerButtons[0]["aria-pressed"]'), 'false', 'Pending writes clear the announced selection');
  homeState.run("posting = false; state.lights.power = 'off'; state.lighting_recovery = {write_blocked:true}; shippedSync();");
  assert.equal(homeState.run('powerButtons[1]["aria-pressed"]'), 'false', 'Uncertain lighting does not announce a selected button');
  homeState.run('state.lighting_recovery = {}; state.blinds.available = true; shippedSync();');
  assert.equal(homeState.run("$('blind-status').textContent"), 'Ready');
  assert.equal(homeState.run('powerButtons[1]["aria-pressed"]'), 'true');
  assert.equal(homeState.commands.length, 0);

  const profile = profileWebsite();
  await profile.run("chooseProfile({title:'Visitor demo', stages:['Sit still', 'Walk'], annotations:['Beginning', 'Finished']})");
  assert.equal(profile.commands.length, 0, 'Selecting a file only previews it');
  assert.equal(profile.run('profilePreview.value.sensors'), 'Room sensors', 'Partial files use the panel-owned defaults');
  assert.match(profile.run("$('profile-preview').textContent"), /Visitor demo.*2 instructions.*2 annotation buttons/);
  profile.run('shippedSync(); shippedSync();');
  assert.equal(profile.run('profilePreview.value.title'), 'Visitor demo', 'Ordinary polls retain the preview');
  profile.run("state.revision = 'two'; syncProfile();");
  assert.equal(profile.run("$('profile-load').disabled"), true);
  assert.equal(profile.run("$('profile-file').disabled"), false, 'A changed panel permits choosing the same file again');
  assert.match(profile.run("$('profile-status').textContent"), /panel changed/);
  await profile.run('loadSelectedProfile()');
  assert.equal(profile.commands.length, 0, 'A preview from an old revision cannot be loaded');
  await profile.run("chooseProfile({title:'Visitor demo', stages:['Sit still', 'Walk'], annotations:['Beginning', 'Finished']})");
  await profile.run('loadSelectedProfile()');
  assert.equal(profile.commands.length, 1);
  assert.equal(profile.commands[0].action, 'profile');
  assert.equal(profile.commands[0].revision, 'two');
  assert.deepEqual(profile.commands[0].arguments.value, {title:'Visitor demo', sensors:'Room sensors', stages:['Sit still', 'Walk'], annotations:['Beginning', 'Finished']});
  assert.equal(profile.run('profilePreview'), null, 'A confirmed load clears its preview');
  for (const accepted of [true, false]) {
    const recoveredProfile = profileWebsite((request, context) => {
      context.ownerReceipt = {id:request.id, ok:accepted, code:accepted ? 202 : 409, detail:'Shorten the instruction title to fit the panel.'};
      vm.runInContext("state.receipts = [ownerReceipt]; state.revision = 'two';", context);
      return {status:503, ok:false, json:async () => ({ok:false, code:503})};
    });
    await recoveredProfile.run("chooseProfile({title:'Recovered profile'})");
    await recoveredProfile.run('loadSelectedProfile()');
    assert.equal(recoveredProfile.run('unknown'), null);
    assert.equal(recoveredProfile.commands.length, 1, 'Receipt recovery never repeats a profile load');
    if (accepted) {
      assert.equal(recoveredProfile.run('profilePreview'), null, 'A recovered successful receipt clears the stale preview');
      assert.match(recoveredProfile.run('profileNotice'), /Profile loaded for this panel session/);
      assert.match(recoveredProfile.run("$('message').textContent"), /Profile loaded for this panel session/);
      assert.notEqual(recoveredProfile.run('messageTimer'), null);
    } else {
      assert.equal(recoveredProfile.run('profilePreview.value.title'), 'Recovered profile', 'A rejected load keeps its preview for review');
      assert.match(recoveredProfile.run("$('message').textContent"), /Shorten the instruction title/);
      assert.doesNotMatch(recoveredProfile.run('profileNotice'), /Profile loaded/);
    }
  }

  for (const [setup, explanation] of [
    ['state.experiment.running = true', /Pause instructions/],
    ['state.busy = true', /current panel action/],
    ['state.available = false', /Connect to the panel/],
    ["unknown = 'unconfirmed'", /current panel action/],
    ["state.session = 'owner-two'", /panel changed/],
  ]) {
    const blocked = profileWebsite();
    await blocked.run('chooseProfile({})');
    blocked.run(setup + '; syncProfile();');
    assert.equal(blocked.run("$('profile-load').disabled"), true);
    assert.match(blocked.run("$('profile-status').textContent"), explanation);
    await blocked.run('loadSelectedProfile()');
    assert.equal(blocked.commands.length, 0);
  }
  for (const selection of [
    "chooseProfile({}, 'instructions.txt')",
    "chooseProfile({}, 'instructions.json', 32769)",
    "previewProfile({name:'broken.json', size:4, text:async () => '{bad'}, $('profile-file'))",
    "chooseProfile({path:'/not/a/profile'})",
    "chooseProfile({stages:['Duplicate', 'Duplicate']})",
  ]) {
    const invalid = profileWebsite();
    await invalid.run('chooseProfile({})');
    await invalid.run(selection);
    assert.equal(invalid.run('profilePreview'), null, 'An invalid selection clears the previous file');
    assert.ok(invalid.run('profileNotice'));
    assert.equal(invalid.commands.length, 0);
  }
  const lateFile = profileWebsite();
  const reading = lateFile.run("previewProfile({name:'old.json', size:30, text:() => new Promise(resolve => {resolveOld = resolve;})}, $('profile-file'))");
  await lateFile.run("chooseProfile({title:'Latest file'})");
  lateFile.run("resolveOld(JSON.stringify({title:'Old file'}))");
  await reading;
  assert.equal(lateFile.run('profilePreview.value.title'), 'Latest file', 'A slow earlier read cannot replace the latest selection');

  const exported = profileWebsite();
  exported.context.Blob = Blob;
  exported.run(`
    let downloadedBlob, downloadName, revoked;
    URL = {createObjectURL(blob) {downloadedBlob = blob; return 'blob:local-profile';}, revokeObjectURL(value) {revoked = value;}};
    document.body = {append() {}};
    document.createElement = () => ({click() {downloadName = this.download;}, remove() {}});
    setTimeout = fn => fn();
    downloadProfile();
  `);
  assert.deepEqual(JSON.parse(await exported.run('downloadedBlob.text()')), JSON.parse(exported.run('JSON.stringify(state.experiment.profile)')));
  assert.equal(exported.run('downloadName'), 'room-instructions.json');
  assert.equal(exported.run('revoked'), 'blob:local-profile');
  assert.equal(exported.commands.length, 0, 'Downloading a profile is local');

  const annotations = profileWebsite();
  annotations.run('shippedSync();');
  const firstMark = annotations.run("$('marks').children[0]");
  annotations.run('shippedSync();');
  assert.equal(annotations.run("$('marks').children[0]"), firstMark, 'Unchanged profiles retain their annotation buttons');
  annotations.run("state.experiment.profile = {...state.experiment.profile, annotations:['Visitor arrived', 'Visitor left']}; shippedSync();");
  assert.equal(annotations.run("$('marks').children.length"), 2);
  assert.equal(annotations.run("$('marks').children[0].textContent"), 'Visitor arrived');
  await annotations.run("$('marks').children[0].onclick()");
  assert.equal(annotations.commands[0].arguments.label, 'Visitor arrived', 'Replacement buttons send the current profile label');

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
