// Exercise the shipped command/receipt logic using Node's standard library only.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../browser/room.js'), 'utf8');

function website(respond, snapshot = () => ({available:true, session:'owner-one', revision:'one'})) {
  const elements = new Map();
  for (const id of ['legacy-return', 'message', 'connection', 'legacy-banner', 'panel-mode-message', 'light-feedback', 'light-message', 'light-recent', 'blind-permission', 'gradient-controls', 'programme-controls', 'programmes-unavailable', 'programme-status'])
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

function preferencesWebsite(page, roomContent = {}) {
  let site;
  site = website((request, context) => {
    context.preferenceRequest = request;
    vm.runInContext('state.preferences[preferenceRequest.action] = preferenceRequest.arguments.value;', context);
    return {status:202, ok:true, json:async () => ({ok:true, code:202, id:request.id})};
  }, () => JSON.parse(site.run('JSON.stringify(state)')));
  site.context.settingsPage = page;
  site.context.settingsContent = roomContent;
  site.run(`
    content = settingsContent;
    const preferenceNodes = [], preferenceIds = new Map();
    function preferenceDescendants(node) {return [node, ...node.children.flatMap(preferenceDescendants)];}
    function preferenceNode(tag) {
      const node = {tagName:tag, children:[], dataset:{}, style:{}, textContent:'', value:'',
        get options() {return this.children;},
        get id() {return this.elementId;}, set id(value) {this.elementId = value; preferenceIds.set(value, this);},
        append(...children) {this.children.push(...children); this.attach();},
        prepend(...children) {this.children.unshift(...children); this.attach();},
        replaceChildren(...children) {this.children = children; this.attach();},
        attach() {this.children.forEach((child, index) => {child.parentElement = this; child.previousElementSibling = this.children[index - 1];});},
        setAttribute(name, value) {this[name] = value;},
        querySelector(tag) {return preferenceDescendants(this).find(child => child.tagName === tag) || null;},
      };
      preferenceNodes.push(node);
      return node;
    }
    const originalGet = document.getElementById;
    document.getElementById = id => preferenceIds.get(id) || originalGet(id);
    document.createElement = preferenceNode;
    document.createElementNS = (namespace, tag) => ({...preferenceNode(tag), namespaceURI:namespace});
    document.querySelectorAll = selector => selector === '[data-action]'
      ? preferenceNodes.filter(node => node.dataset.action)
      : selector === '[data-preference]'
        ? preferenceNodes.filter(node => node.dataset.preference)
        : selector === '[data-auto-schedule]'
          ? preferenceNodes.filter(node => node.dataset.autoSchedule)
          : [];
    state = {available:true, session:'owner-one', revision:'one', csrf:'local',
      preferences:{theme:'light', tips:true, clock:'12', temperature:'f', idle:300, blinds_display:'disabled', blinds_enabled:false},
      lights:{}, blinds:{connected:true, reason:'Controls locked in settings'}};
    view = 'tools-' + settingsPage;
    const settingsRoot = preferenceNode('main');
    tools(settingsRoot, settingsPage);
    sync = shippedSync;
    sync();
  `);
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
    const diagnosticsElements = new Map(['room-diagnostics-services', 'room-diagnostics-status', 'room-diagnostics-observed', 'room-diagnostics-check', 'room-health'].map(id => [id, {
      textContent:'', dataset:{}, children:[], replaceChildren(...children) {this.children = children;}, append(...children) {this.children.push(...children);},
    }]));
    const originalGet = document.getElementById;
    document.getElementById = id => diagnosticsElements.get(id) || originalGet(id);
    document.createElement = tag => ({tagName:tag, textContent:'', children:[], append(...children) {this.children.push(...children);}});
    state.room_diagnostics = {state:'available', can_check:true, checking:false, observed_at:'2026-10-30T15:00:00Z', age_s:20,
      services:[{name:'Lighting', state:'listed'}, {name:'Environment', state:'missing'}]};
    syncRoomDiagnostics();
  `);
  assert.equal(diagnosticRows.run("$('room-diagnostics-services').children.length"), 4, 'Room services stays a compact four-row summary even before every group is observed');
  assert.equal(diagnosticRows.run("$('room-diagnostics-services').children[0].children[1].textContent"), 'Advertised');
  assert.equal(diagnosticRows.run("$('room-diagnostics-services').children.find(row => row.children[0].textContent === 'Environment').children[1].textContent"), 'Missing');
  assert.equal(diagnosticRows.run("$('room-health').hidden"), true, 'Structured rows replace duplicate connection prose');
  assert.equal(diagnosticRows.run("$('room-diagnostics-status').hidden"), true, 'Successful checks need no duplicate status paragraph');
  diagnosticRows.run("state.room_diagnostics.state = 'unavailable'; state.room_diagnostics.detail = 'Room connection timed out.'; state.room_diagnostics.age_s = 180; syncRoomDiagnostics();");
  assert.equal(diagnosticRows.run("$('room-diagnostics-services').children[0].children[1].textContent"), 'Advertised', 'A failed recheck retains the last successful registration observation');
  assert.match(diagnosticRows.run("$('room-diagnostics-status').textContent"), /latest room check failed.*timed out.*Earlier results/);
  assert.equal(diagnosticRows.run("$('room-diagnostics-status').hidden"), false);
  assert.match(diagnosticRows.run("$('room-diagnostics-observed').textContent"), /3 min ago/);
  assert.equal(diagnosticRows.commands.length, 0);
  const panelHealth = website(() => {throw Error('Formatting health cannot post commands');});
  panelHealth.run(`
    const healthElements = new Map(['panel-memory', 'panel-storage', 'panel-temperature', 'panel-power'].map(id => [id, {
      textContent:'', classList:{toggle() {}},
    }]));
    const originalGet = document.getElementById;
    document.getElementById = id => healthElements.get(id) || originalGet(id);
    state = {available:true, can_control:true, lights:{}, health:{ram_available:123.9, ram_total:999.1, disk_available:41.234, temperature:54.678, power:'No current undervoltage'}};
    shippedSync();
  `);
  assert.equal(panelHealth.run("$('panel-memory').textContent"), 'Memory: 124 / 999 MiB free');
  assert.equal(panelHealth.run("$('panel-storage').textContent"), 'Storage: 41.2 GiB free');
  assert.equal(panelHealth.run("$('panel-temperature').textContent"), 'CPU: 54.7 °C');
  panelHealth.run("state.health = {ram_available:null, ram_total:NaN, disk_available:'41.234', temperature:Infinity, power:42}; shippedSync();");
  assert.equal(panelHealth.run("$('panel-memory').textContent"), 'Memory: — / — MiB free');
  assert.equal(panelHealth.run("$('panel-storage').textContent"), 'Storage: — GiB free');
  assert.equal(panelHealth.run("$('panel-temperature').textContent"), 'CPU: — °C');
  assert.equal(panelHealth.run("$('panel-power').textContent"), 'Power: —');
  panelHealth.run("state.can_control = false; state.experiment = {running:true, profile:{title:'Instructions', stages:['Sit still'], annotations:[]}, stage:0, elapsed_s:0}; shippedSync();");
  assert.equal(panelHealth.run("$('connection').textContent"), 'Instructions running');
  assert.equal(panelHealth.commands.length, 0);

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
    let displayedHeading = null, displayedTab = null, displayedSectionHeading = null, focusedHeading = null, sectionScrolls = 0;
    function pageHeading(text) {
      return {textContent:text, setAttribute(name, value) {this[name] = value;}, focus() {focusedHeading = this;}, scrollIntoView() {sectionScrolls++;}};
    }
    const main = {replaceChildren() {displayedHeading = displayedTab = displayedSectionHeading = null;}, querySelector(selector) {
      return selector === '.lighting-tabs a[aria-current="page"]' ? displayedTab
        : selector === '#guide-controls-topics' ? displayedSectionHeading : displayedHeading;
    }};
    const originalGet = document.getElementById;
    document.getElementById = id => id === 'app' ? main : originalGet(id);
    document.querySelectorAll = selector => selector === '.header a' ? anchors : [];
    location = {hash:'#tools-lighting-scenes', pathname:'/'};
    home = () => {displayedHeading = pageHeading('Lights');};
    tools = (root, page) => {
      displayedHeading = pageHeading(page.startsWith('lighting') ? 'Lighting' : 'System & help');
      if (page === 'lighting-scenes') displayedTab = {textContent:'Scenes'};
    };
    guide = (root, index) => {
      displayedHeading = pageHeading(index >= 0 ? 'Sensors in the ceiling' : 'Demo & guide');
      if (index < 0) displayedSectionHeading = pageHeading('Control help');
    };
    view = '';
    layout();
  `);
  assert.equal(navigation.run('anchors[1]["aria-current"]'), 'page');
  assert.equal(navigation.run('document.title'), 'Lighting · Scenes · Smart Conference Room');
  assert.equal(navigation.run('displayedHeading["aria-label"]'), 'Lighting · Scenes');
  navigation.run("location.hash = '#guide-1'; layout();");
  assert.equal(navigation.run('anchors[1].hash'), '#tools-lighting-scenes', 'Guide browsing retains the last Lighting tab');
  assert.equal(navigation.run('anchors[2]["aria-current"]'), 'page');
  assert.equal(navigation.run('document.title'), 'Sensors in the ceiling · Smart Conference Room');
  assert.equal(navigation.run('focusedHeading'), navigation.run('displayedHeading'), 'Page focus follows the actual topic heading');
  assert.equal(navigation.run('anchors[2].hash'), '#guide', 'Persistent Guide navigation opens topics from a long leaf');
  navigation.run('const previousGuideLeaf = lastGuide; location.hash = anchors[2].hash; layout();');
  assert.equal(navigation.run('view'), 'guide');
  navigation.run("location.hash = '#' + previousGuideLeaf; layout();");
  assert.equal(navigation.run('view'), 'guide-1', 'Returning through hash history still restores the leaf');
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
  navigation.run("location.hash = '#guide-controls'; layout();");
  assert.equal(navigation.run('focusedHeading.textContent'), 'Control help', 'A control-help return focuses its heading on the shared index');
  assert.equal(navigation.run('sectionScrolls'), 1);
  navigation.run("view = ''; layout();");
  assert.equal(navigation.run('focusedHeading.textContent'), 'Control help', 'An initial legacy control-help route also has a visible focused destination');
  assert.equal(navigation.run('sectionScrolls'), 2);
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
    const topicIndex = guideNode('main');
    guide(topicIndex, -1);
    const topicLinks = descendants(topicIndex).filter(node => node.className === 'topic');
    const oldControlIndex = guideNode('main');
    guide(oldControlIndex, -1, 'controls');
  `);
  const sharedTopics = guideContent.context.generatedContent.guide;
  assert.equal(guideContent.run('topicLinks.length'), sharedTopics.length);
  assert.deepEqual(Array.from(guideContent.run("descendants(topicIndex).filter(node => node.tagName === 'h3')"), node => node.textContent), ['Room tour', 'Control help']);
  assert.equal(guideContent.run("descendants(oldControlIndex).filter(node => node.className === 'topic').length"), sharedTopics.length, 'The old section route retains every topic in the shared index');
  assert.equal(guideContent.run("descendants(topicIndex).some(node => node.className === 'guide-sections')"), false, 'The index does not require a section-selector step');
  for (const [index, topic] of sharedTopics.entries()) {
    assert.equal(guideContent.run(`topicLinks.filter(node => node.href === '#guide-${index}').length`), 1);
    assert.equal(guideContent.run(`descendants(topicLinks.find(node => node.href === '#guide-${index}')).find(node => node.tagName === 'small').textContent`), topic.caption);
    guideContent.run(`const topic${index} = guideNode('main'); guide(topic${index}, ${index});`);
    const section = topic.section || 'controls';
    const sectionTopics = sharedTopics.filter(item => (item.section || 'controls') === section);
    const position = sectionTopics.indexOf(topic);
    const heading = guideContent.run(`descendants(topic${index}).filter(node => node.tagName === 'h2')`);
    assert.equal(heading.length, 1);
    assert.equal(heading[0].textContent, topic.title, 'Each leaf has its actual topic as the page heading');
    assert.match(guideContent.run(`topic${index}.children[0].textContent`), new RegExp((section === 'controls' ? 'Control help' : 'Room tour') + '.*' + (position + 1) + ' of ' + sectionTopics.length));
    const back = guideContent.run(`descendants(topic${index}).find(node => node.tagName === 'a' && node.textContent === '${section === 'controls' ? 'Control help topics' : 'Room tour topics'}')`);
    assert.equal(back.href, section === 'controls' ? '#guide-controls' : '#guide');
    assert.equal(guideContent.run(`topic${index}.children[1].children[0]`), back, 'The topic return is beside the breadcrumb, before the story');
    const neighbours = guideContent.run(`topic${index}.children.at(-1)`);
    assert.equal(neighbours['aria-label'], 'More ' + (section === 'controls' ? 'control help' : 'room tour') + ' topics');
    assert.deepEqual(Array.from(neighbours.children, node => node['aria-label']), [
      ...(position > 0 ? ['Previous topic: ' + sectionTopics[position - 1].title] : []),
      ...(position < sectionTopics.length - 1 ? ['Next topic: ' + sectionTopics[position + 1].title] : []),
    ], 'Neighbour links identify the destination and stay in one group');
    const destinations = guideContent.run(`descendants(topic${index}).filter(node => node.className === 'topic-destination')`);
    assert.deepEqual(Array.from(destinations, node => [node.textContent, node.href]),
      topic.links.map(destination => [destination.label, '#' + (destination.page === 'home' ? 'home' : 'tools-' + destination.page)]));
    assert.equal(destinations.every(node => node.onclick === undefined), true, 'Guide destinations use ordinary navigation links');
    assert.equal(destinations.every(node => node.children.some(child => child.textContent === '→' && child['aria-hidden'] === 'true')), true);
    assert.equal(topic.links.every(destination => destination.label.startsWith('Open ')), true, 'Navigation labels distinguish opening a page from applying a room action');
  }
  assert.equal(guideContent.commands.length, 0);
  guideContent.run("const roomServiceRoot = guideNode('main'); roomDiagnostics(roomServiceRoot);");
  assert.equal(guideContent.run("descendants(roomServiceRoot).some(node => node.tagName === 'details')"), false, 'Room services is always visible without a disclosure');
  assert.equal(guideContent.run("descendants(roomServiceRoot).find(node => node.tagName === 'h3').textContent"), 'Room services');
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
    const sceneButton = {dataset:{action:'preset', preset:'Fid'},
      classList:{toggle(name, value) {this[name] = Boolean(value);}},
      setAttribute(name, value) {this[name] = value;}, removeAttribute(name) {delete this[name];},
    };
    document.querySelectorAll = selector => selector === '[data-action=on],[data-action=off]' ? powerButtons
      : selector === '[data-preset]' ? [sceneButton]
      : selector === '[data-action]' ? [...powerButtons, sceneButton] : [];
    state = {available:true, can_control:true, lights:{message:'Light settings confirmed.', power:'on', confirmed_power:'on', scene:'Fid', recent:'Fid', confirmed_age_s:12}, blinds:{reason:'Locked in settings'}};
    shippedSync();
  `);
  assert.equal(homeState.run("$('blind-status').textContent"), 'Locked in settings');
  assert.equal(homeState.run("$('light-recent').textContent"), 'Last confirmed: Lights on · Fid · just now');
  assert.equal(homeState.run("$('light-message').className"), 'visually-hidden', 'Routine confirmation remains accessible without a second visible status line');
  for (const guard of ['posting = true', 'unknown = "receipt"', 'state.busy = true']) {
    homeState.run(`${guard}; shippedSync();`);
    assert.equal(homeState.run("$('light-message').className"), '', 'Work or uncertainty must not collapse the current status');
    homeState.run('posting = false; unknown = null; state.busy = false; shippedSync();');
  }
  assert.equal(homeState.run('powerButtons.some(button => button["aria-pressed"] !== undefined || button.classList.selected)'), false, 'Lighting commands remain ordinary action buttons');
  assert.equal(homeState.run('sceneButton["aria-pressed"]'), undefined);
  assert.equal(homeState.run('sceneButton.classList.selected'), undefined);
  homeState.run("state.blinds.reason = 'Not connected'; posting = true; state.lights.power = null; state.lights.message = 'Selected: Off / waiting to send'; shippedSync();");
  assert.equal(homeState.run("$('blind-status').textContent"), 'Not connected');
  assert.equal(homeState.run('powerButtons.every(button => button.disabled) && sceneButton.disabled'), true);
  assert.equal(homeState.run("$('light-message').textContent"), 'Selected: Off / waiting to send');
  assert.equal(homeState.run("$('light-message').className"), '');
  assert.equal(homeState.run("$('light-feedback').dataset.state"), 'pending');
  assert.equal(homeState.run("$('light-recent').textContent"), 'Last confirmed: Lights on · Fid · just now', 'A pending selection cannot replace historical confirmation');
  homeState.run("posting = false; state.can_control = false; state.lighting_recovery = {status:'needs_staff', write_blocked:true}; state.lights.confirmed_age_s = 180; shippedSync();");
  assert.equal(homeState.run('powerButtons.every(button => button.disabled) && sceneButton.disabled'), true);
  assert.equal(homeState.run("$('light-message').className"), '');
  assert.equal(homeState.run("$('light-recent').textContent"), 'Last confirmed: Lights on · Fid · 3 min ago', 'Uncertainty preserves separately aged confirmed readback');
  homeState.run("state.lighting_recovery = {status:'normal'}; state.can_control = true; state.lights.power = state.lights.confirmed_power = 'off'; state.lights.recent = 'Off'; state.blinds.available = true; shippedSync();");
  assert.equal(homeState.run("$('blind-status').textContent"), 'Ready');
  assert.equal(homeState.run("$('light-recent').textContent"), 'Last confirmed: Lights off · Off · 3 min ago');
  homeState.run('state.lights.power = state.lights.confirmed_power = null; shippedSync();');
  assert.equal(homeState.run("$('light-recent').textContent"), 'Last confirmed: Off · 3 min ago', 'Unknown confirmed power does not invent an On or Off state');
  assert.equal(homeState.run('powerButtons.some(button => button["aria-pressed"] !== undefined || button.classList.selected) || sceneButton["aria-pressed"] !== undefined || Boolean(sceneButton.classList.selected)'), false);
  for (const [recent, expected] of [
    ['Not checked', 'Lighting not checked yet.'],
    ['Programme request accepted; live state unavailable', 'Programme request accepted; live state unavailable'],
    ['Session ended', 'Session ended'],
    [undefined, 'Lighting not checked yet.'],
  ]) {
    homeState.context.untimedRecent = recent;
    homeState.run("state.lights.confirmed_age_s = null; state.lights.confirmed_power = 'on'; state.lights.recent = untimedRecent; state.lights.message = 'Waiting for controller confirmation.'; shippedSync();");
    assert.equal(homeState.run("$('light-recent').textContent"), expected, 'Untimed status cannot claim a confirmed power or lighting readback');
    assert.equal(homeState.run("$('light-message').textContent"), 'Waiting for controller confirmation.');
  }
  assert.equal(homeState.commands.length, 0);

  const whitePreset = preferencesWebsite('lighting-white', guideContent.context.generatedContent);
  whitePreset.run(`
    state.can_control = true;
    shippedSync();
    const quickApply = preferenceNodes.find(node => node['aria-label'] === 'Apply Warm white: 3500 K, level 1000.');
  `);
  assert.equal(whitePreset.run('quickApply.textContent'), 'Apply');
  assert.equal(whitePreset.run('quickApply.parentElement.parentElement.className'), 'white-heading', 'The preset belongs with the White light heading, before the sliders');
  assert.equal(whitePreset.run('quickApply.previousElementSibling.children[0].textContent'), 'Warm white');
  assert.equal(whitePreset.run('quickApply.previousElementSibling.children[1].textContent'), '3500 K, level 1000.');
  assert.equal(whitePreset.commands.length, 0, 'Rendering a preset never applies it');
  await whitePreset.run('quickApply.onclick();');
  assert.equal(whitePreset.commands.length, 1);
  assert.equal(whitePreset.commands[0].action, 'cct');
  assert.deepEqual(whitePreset.commands[0].arguments, {cct:3500, intensity:1000});
  whitePreset.run('state.can_control = false; shippedSync();');
  assert.equal(whitePreset.run('quickApply.disabled'), true, 'The integrated preset keeps the shared lighting guard');

  for (const [page, action, option, value, label] of [
    ['appearance', 'theme', '2', 'auto', 'Theme'],
    ['appearance', 'tips', '1', false, 'Touch tips'],
    ['clock', 'clock', '1', '24', 'Clock'],
    ['clock', 'temperature', '0', 'c', 'Temperature'],
    ['screen', 'idle', '0', 0, 'Screen saver'],
    ['screen', 'blinds_display', '1', 'hidden', 'Blinds on Home'],
  ]) {
    const preference = preferencesWebsite(page);
    preference.context.preferenceAction = action;
    preference.run("const select = preferenceNodes.find(node => node.dataset.preference === preferenceAction);");
    assert.equal(preference.run("select['aria-label']"), label);
    preference.run(`select.value = '${option}';`);
    await preference.run('select.onchange()');
    assert.equal(preference.commands.length, 1);
    assert.equal(preference.commands[0].action, action);
    assert.equal(preference.commands[0].arguments.value, value, 'Native options retain the command value type');
    assert.equal(preference.run('select.value'), option, 'The select reflects the confirmed preference');
  }
  const autoTheme = preferencesWebsite('appearance');
  assert.equal(autoTheme.run("preferenceNodes.filter(node => node.dataset.autoSchedule).every(node => node.hidden)"), true);
  autoTheme.run("state.preferences.theme = 'auto'; sync();");
  assert.equal(autoTheme.run("preferenceNodes.filter(node => node.dataset.autoSchedule).some(node => node.hidden)"), false);
  autoTheme.run("state.preferences.theme = 'dark'; sync();");
  assert.equal(autoTheme.run("preferenceNodes.filter(node => node.dataset.autoSchedule).every(node => node.hidden)"), true);
  const guardedPreference = preferencesWebsite('appearance');
  guardedPreference.run("unknown = 'pending-light'; sync(); const themeSelect = preferenceNodes.find(node => node.dataset.preference === 'theme'); themeSelect.value = '1';");
  assert.equal(guardedPreference.run('themeSelect.disabled'), true);
  await guardedPreference.run('themeSelect.onchange()');
  assert.equal(guardedPreference.commands.length, 0);
  assert.equal(guardedPreference.run('themeSelect.value'), '0', 'An unsent preference returns to its confirmed value');
  assert.equal(guardedPreference.run('unknown'), 'pending-light');
  const blindPermission = preferencesWebsite('screen');
  assert.equal(blindPermission.run("$('blind-lock').textContent"), 'Unlock blind controls');
  await blindPermission.run("$('blind-lock').onclick()");
  assert.equal(blindPermission.commands[0].arguments.value, true);
  assert.equal(blindPermission.run("$('blind-lock').textContent"), 'Lock blind controls');
  await blindPermission.run("$('blind-lock').onclick()");
  assert.equal(blindPermission.commands[1].arguments.value, false);
  blindPermission.run('state.blinds.connected = false; sync();');
  assert.equal(blindPermission.run("$('blind-permission').hidden"), true);
  assert.equal(blindPermission.run("$('blind-lock').disabled"), true);
  await blindPermission.run("$('blind-lock').onclick()");
  assert.equal(blindPermission.commands.length, 2, 'A disconnected adapter cannot be unlocked');
  const instructions = preferencesWebsite('experiment');
  instructions.run("state.can_session = true; state.experiment = {profile:{title:'Instructions', stages:['First', 'Last'], annotations:[]}, stage:0, elapsed_s:0, started:false, running:false}; sync();");
  assert.equal(instructions.run("$('instruction-start').textContent"), 'Start instructions');
  assert.equal(instructions.run("$('instruction-start').disabled"), false);
  assert.equal(instructions.run("$('instruction-pause').disabled"), true);
  assert.equal(instructions.run("$('instruction-previous').disabled"), true);
  instructions.run('state.experiment.running = true; state.experiment.started = true; sync();');
  assert.equal(instructions.run("$('instruction-start').disabled"), true);
  assert.equal(instructions.run("$('instruction-pause').disabled"), false);
  instructions.run('state.experiment.running = false; sync();');
  assert.equal(instructions.run("$('instruction-start').textContent"), 'Resume instructions', 'A pause before one whole second still resumes');
  instructions.run('state.experiment.stage = 1; sync();');
  assert.equal(instructions.run("$('instruction-next').textContent"), 'Finish instructions');
  assert.equal(instructions.run("$('instruction-previous').disabled"), false);
  instructions.run("state.experiment.started = false; state.experiment.stage = 0; sync();");
  assert.equal(instructions.run("$('instruction-start').textContent"), 'Start instructions', 'A reset profile restores the initial label');
  instructions.run("delete state.experiment.started; state.experiment.elapsed_s = 4; sync();");
  assert.equal(instructions.run("$('instruction-start').textContent"), 'Resume instructions', 'Older owners retain elapsed-time compatibility');
  instructions.run("unknown = 'unconfirmed-command'; sync();");
  assert.equal(instructions.run("['instruction-start', 'instruction-pause', 'instruction-previous', 'instruction-next'].every(id => $(id).disabled)"), true);
  assert.equal(instructions.commands.length, 0);

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
