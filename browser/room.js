'use strict';
// Shared state and commands come from the existing panel owner. No device driver lives here.
const $=id=>document.getElementById(id);
let state=null,content={guide:[],help:[]},posting=false,unknown=null,view='',dragging=false,rangeRevision=null,chosenHelp=0;
let powerChoice=null,powerRequest=null;
const paths={home:'M3 10 12 3l9 7v11h-6v-7H9v7H3Z',white:'M9 18h6m-5 3h4M8 13a6 6 0 1 1 8 0l-1 3H9Z',scenes:'m12 3 10 5-10 5L2 8Zm-10 9 10 5 10-5M2 16l10 5 10-5',experiment:'M9 3h6m-5 0v7L4 20h16l-6-10V3',appearance:'M12 3v2m0 14v2M3 12h2m14 0h2M6 6l1 1m10 10 1 1M6 18l1-1M17 7l1-1M16 12a4 4 0 1 1-4-4',clock:'M8 2v4m8-4v4M3 9h18M3 4h18v18H3Z',screen:'M3 4h18v13H3Zm9 13v4m-5 0h10',system:'M2 12h5l3-8 4 16 3-8h5',about:'M12 11v6m0-10v1M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',guide:'M12 5v16M3 3l9 2 9-2v16l-9 2-9-2Z',legacy:'M14 3h7v7m0-7L10 14M9 5H3v16h16v-6',off:'M9 18h6m-5 3h4M8 13a6 6 0 0 1-2-5m3-4a6 6 0 0 1 7 9l-1 3H9M3 3l18 18'};
function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function icon(name){const n=document.createElementNS('http://www.w3.org/2000/svg','svg');n.setAttribute('viewBox','0 0 24 24');n.setAttribute('aria-hidden','true');for(const shape of content.icons?.[name]||[{tag:'path',attributes:{d:paths[name]||paths.about}}]){const child=document.createElementNS(n.namespaceURI,shape.tag);for(const [key,value] of Object.entries(shape.attributes))child.setAttribute(key,value);n.append(child);}return n;}
function asset(path){return window.SCR_ASSETS?.[path]||path;}
function button(text,fn,opts={}){const n=el('button',text,opts.primary?'primary':'');n.type='button';if(opts.icon)n.prepend(icon(opts.icon));n.onclick=fn;if(opts.action)n.dataset.action=opts.action;if(opts.choice){n.dataset.choice=opts.choice[0];n.dataset.value=String(opts.choice[1]);}return n;}
function link(text,hash,kind){const a=el('a',text);a.href='#'+hash;if(kind)a.prepend(icon(kind));return a;}
function command(action,args={},revision=state?.revision){
  if(posting||unknown||!state?.available)return Promise.resolve(false);
  const id=Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('');
  if(action==='power')powerRequest={operation:args.operation,session:state.session,id,accepted:false};
  posting=true;sync();
  return fetch('/api/command',{method:'POST',headers:{'Content-Type':'application/json','X-SCR-Token':state.csrf},
    body:JSON.stringify({id,revision,action,arguments:args}),signal:AbortSignal.timeout(5000)}).then(async response=>{
    const reply=await response.json().catch(()=>null);
    if(!reply&&[400,403,405].includes(response.status)){if(action==='power')powerRequest=null;message('Command was rejected. Refresh the page before trying a new action.');return false;}
    if(!reply){unknown=id;message(action==='power'?'Power request status is unknown. Check the touch panel before trying again.':'Command receipt unknown. Check the panel; do not repeat the action.');return false;}
    if(!response.ok||!reply.ok){if(action==='power')powerRequest=null;message(reply.detail||'Command was not accepted.');return false;}
    if(action==='power'){powerRequest.accepted=true;powerChoice=null;if($('power-confirmation'))$('power-confirmation').hidden=true;message(powerRequest.operation==='reboot'?'Restart requested. The panel is preparing to restart.':'Shutdown requested. The panel is preparing to shut down.');return true;}
    message(action==='on'||action==='off'||['cct','channels','preset'].includes(action)?'Sent. Waiting for controller confirmation.':'Accepted by the panel.');return true;
  }).catch(()=>{unknown=id;message(action==='power'?'Power request status is unknown. Check the touch panel before trying again.':'Command receipt unknown. Check the panel; do not repeat the action.');return false;})
    .finally(async()=>{posting=false;dragging=false;rangeRevision=null;await refresh();sync();});
}
function message(text){$('message').textContent=text;$('message').hidden=!text;}
function route(){return (location.hash.slice(1)|| (location.pathname==='/guide'?'guide':location.pathname==='/tools'?'tools-lighting':'home'));}
function layout(){
  const next=route();if(next===view)return;view=next;dragging=false;rangeRevision=null;powerChoice=null;
  const root=$('app');root.replaceChildren();
  for(const a of document.querySelectorAll('.header a'))a.setAttribute('aria-current',a.hash.slice(1)===view||(a.hash==='#tools-lighting'&&view.startsWith('tools-'))?'page':'false');
  if(view.startsWith('tools-'))tools(root,view.slice(6));
  else if(view.startsWith('guide'))guide(root,view==='guide'?-1:Number(view.split('-')[1]));
  else if(view==='legacy')legacy(root);else home(root);
  sync();
}
function feedback(parent){const box=el('div',undefined,'feedback');const current=el('p');current.id='light-message';const recent=el('p',undefined,'muted');recent.id='light-recent';box.append(current,recent);parent.append(box);}
function home(root){
  const row=el('div',undefined,'room-layout'),left=el('section'),right=el('section');
  const groups=el('div',undefined,'essential-grid');groups.id='essentials';
  for(const [title,caption,isBlind] of [['Lights','Whole room',false],['Blinds','Whole room',true]]){
    const group=el(isBlind?'details':'div',undefined,'essential-group');group.id=isBlind?'blind-group':'light-group';
    let actions=group;
    if(isBlind){group.open=!matchMedia('(max-width:650px)').matches;const summary=el('summary');summary.append(el('h2',title));const note=el('span','Disabled','muted');note.id='blind-status';summary.append(note);group.append(summary);actions=el('div',undefined,'blind-actions');group.append(actions);}
    else group.append(el('h2',title),el('p',caption,'muted'));
    for(const [name,label] of isBlind?content.blind_actions||[['lift','Lift blinds'],['open','Open slats'],['close','Close & lower']]:[['on','Lights on'],['off','Lights off']]){
      const action=isBlind?'blind':name,b=button(label,()=>command(action,isBlind?{name}:{}),{icon:isBlind?null:action==='on'?'white':'off',action});
      actions.append(b);
    }if(!isBlind)group.append(el('small','Standard room lighting'));groups.append(group);
  }left.append(groups);feedback(left);
  right.append(el('p','Troy, NY','eyebrow'));const clock=el('p',undefined,'clock');clock.id='clock';const date=el('p',undefined,'date');date.id='date';right.append(clock,date);
  right.append(el('p','OUTDOOR WEATHER','eyebrow'));
  const reading=el('div',undefined,'weather-reading'),temp=el('span','—','temperature'),art=el('span');temp.id='temperature';art.id='weather-art';art.className='weather-art';art.setAttribute('aria-hidden','true');reading.append(temp,art);right.append(reading);
  const condition=el('p',undefined,'condition');condition.id='condition';right.append(condition);
  const stats=el('dl',undefined,'weather-stats');stats.id='weather-stats';for(const [key,label] of [['feels','Feels like'],['rain','Rain today'],['high','High'],['low','Low']]){const item=el('div',undefined,'weather-metric'),value=el('dd','—');value.id='weather-'+key;item.append(el('dt',label),value);stats.append(item);}right.append(stats);
  const notice=el('p',undefined,'weather-notice');notice.id='weather-notice';notice.hidden=true;right.append(notice);
  const day=el('div',undefined,'daylight');day.id='daylight';const label=el('p');label.id='daylight-label';const track=el('div',undefined,'track'),fill=el('div');fill.id='daylight-fill';track.append(fill);const times=el('div',undefined,'daylight-times');
  const rise=el('span'),set=el('span');rise.id='sunrise';set.id='sunset';times.append(rise,set);day.append(label,track,times);right.append(day);
  const details=el('details'),summary=el('summary','Weather details'),source=el('p',undefined,'subtle');source.id='weather-source';details.append(summary,source);right.append(details);
  row.append(left,right);root.append(row);const nav=el('nav',undefined,'footer-tools');nav.append(link('Room tools','tools-lighting','tools'),link('Demo & guide','guide','guide'));root.append(nav);
}
const pages=[['Lighting','lighting'],['Experiment mode','experiment'],['Appearance','appearance'],['Date & weather','clock'],['Screen & controls','screen'],['System & help','system'],['About','about']];
function choices(parent,items){const row=el('div',undefined,'row');for(const [label,action,value] of items)row.append(button(label,()=>command(action,{value}),{action,choice:[action,value]}));parent.append(row);}
function tools(root,page){
  let tab=page.startsWith('lighting-')?page.slice(9):page==='scenes'?'channels':'white';
  if(!['white','scenes','programmes','channels'].includes(tab))tab='white';
  if(page.startsWith('lighting-')||['white','scenes'].includes(page))page='lighting';
  if(!pages.some(p=>p[1]===page))page='lighting';
  const shell=el('div',undefined,'tools-layout'),nav=el('nav',undefined,'sidebar'),detail=el('section');nav.setAttribute('aria-label','Room tools');nav.append(el('h2','Room tools'));
  for(const [label,key] of pages){const a=link(label,'tools-'+key,key);if(key===page)a.setAttribute('aria-current','page');nav.append(a);}
  const mobile=el('label',undefined,'tools-mobile');mobile.append(el('span','Room tools'));const picker=el('select');picker.id='tool-picker';for(const [label,key] of pages){const option=el('option',label);option.value=key;picker.append(option);}picker.value=page;picker.onchange=()=>{location.hash='tools-'+picker.value;};mobile.append(picker);
  shell.append(nav,mobile,detail);root.append(shell);detail.append(el('h2',pages.find(p=>p[1]===page)[0]));
  if(page==='lighting')lighting(detail,tab);
  else if(page==='experiment'){
    detail.append(el('p','Recorder not connected · instructions and panel annotations only','muted'));
    const card=el('div',undefined,'card'),title=el('h3'),stage=el('p',undefined,'session-stage'),timer=el('p',undefined,'timer'),status=el('p',undefined,'muted');title.id='profile-title';stage.id='instruction';timer.id='elapsed';status.id='session-state';card.append(title,stage,timer,status);detail.append(card);
    const row=el('div',undefined,'row');row.append(button('Start instructions',()=>command('start'),{action:'start',primary:true}),button('Pause',()=>command('pause'),{action:'pause'}));detail.append(row);
    const steps=el('div',undefined,'row');steps.append(button('Previous instruction',()=>command('previous'),{action:'previous'}),button('Next instruction',()=>command('next'),{action:'next'}));detail.append(steps);
    const marks=el('div',undefined,'row');marks.id='marks';detail.append(marks);const note=el('p',undefined,'subtle');note.id='annotation';detail.append(note);
  }else if(page==='appearance'){
    choices(detail,[['Light','theme','light'],['Dark','theme','dark'],['Auto','theme','auto']]);detail.append(el('h3','Automatic schedule'));
    const note=el('p');note.id='schedule';detail.append(note);
    for(const [title,which] of [['Light starts','light_at'],['Dark starts','dark_at']]){
      const row=el('div',undefined,'row');row.append(button(title+' −30 min',()=>command('schedule',{which,delta:-30}),{action:'schedule'}),button(title+' +30 min',()=>command('schedule',{which,delta:30}),{action:'schedule'}));detail.append(row);
    }detail.append(el('p','Automatic theme changes wait while the panel is in use or instructions are running.','muted'));
    detail.append(el('h3','Touch explanations'));choices(detail,[['Tips on','tips',true],['Tips off','tips',false]]);
  }else if(page==='clock'){
    detail.append(el('p','America/New_York','muted'));choices(detail,[['12-hour','clock','12'],['24-hour','clock','24']]);detail.append(el('h3','Weather temperature'));choices(detail,[['Celsius (°C)','temperature','c'],['Fahrenheit (°F)','temperature','f']]);
    const source=el('p',undefined,'subtle');source.id='weather-source';detail.append(source);
  }else if(page==='screen'){
    detail.append(el('h3','Screen saver'));choices(detail,[['Off','idle',0],['1 min','idle',60],['5 min','idle',300],['15 min','idle',900]]);
    detail.append(el('p','A first touch on the screen saver opens Home without activating a control. The preview uses the same screen as the idle timer.','muted'));detail.append(el('h3','Touch panel display'));
    const row=el('div',undefined,'row');row.append(button('Preview screen saver',()=>command('clock_view'),{action:'clock_view'}),button('Blank touch panel',()=>command('blank'),{action:'blank'}),button('Wake to Home',()=>command('home'),{action:'home'}));detail.append(row);detail.append(el('p','Blank shows black pixels; the backlight stays on. Hold one spot on the panel for two seconds to return.','muted'));
    detail.append(el('h3','Blind controls'));
    if(state?.blinds?.connected)choices(detail,[['Locked','blinds_enabled',false],['Unlocked','blinds_enabled',true]]);
    const reason=el('p',undefined,'muted');reason.id='blind-reason';detail.append(reason);
    detail.append(el('h3','Blinds on Home'));choices(detail,[['Show','blinds_display','disabled'],['Hide','blinds_display','hidden']]);
  }else if(page==='system')system(detail);
  else{const version=el('p',undefined,'muted'),build=el('p',undefined,'subtle');version.id='app-version';build.id='app-build';build.hidden=true;detail.append(el('h3','Smart Conference Room'),el('p','Touch panel and browser','muted'),version,build,el('p','Built by Diyanko Bhowmik'),el('p','Original contributors are credited in the repository history.','muted'));const a=el('a','github.com/LESA-RPI/scr.touch_panel');a.href='https://github.com/LESA-RPI/scr.touch_panel';detail.append(a,el('p','Icons: Lucide · lucide.dev','subtle'));}
}
function lighting(detail,tab){
  const tabs=el('nav',undefined,'lighting-tabs');tabs.setAttribute('aria-label','Lighting');
  for(const [label,key] of content.lighting_tabs||[['White light','white'],['Scenes','scenes'],['Programmes','programmes'],['Channels','channels']]){
    const a=link(label,'tools-lighting-'+key);if(key===tab)a.setAttribute('aria-current','page');tabs.append(a);
  }detail.append(tabs);
  if(tab==='scenes'){
    detail.append(el('p','Original scene names and mixtures from Legacy.','muted'));
    const grid=el('div',undefined,'scene-grid');
    for(const scene of content.scenes||[]){
      const card=el('section',undefined,'card'),b=button('Apply scene',()=>command('preset',{name:scene.id}),{action:'preset'});
      b.dataset.preset=scene.id;
      card.append(el('h3',scene.label),el('p',scene.detail,'muted'),b);grid.append(card);
    }detail.append(grid,el('p',content.unavailable_lighting,'muted'));feedback(detail);
  }else if(tab==='programmes'){
    detail.append(el('p',content.unavailable_lighting,'muted'));
  }else if(tab==='channels'){
    detail.append(el('p','Adjust the eight room-wide channel percentages.','muted'));
    const grid=el('div',undefined,'channel-grid');for(const [i,label] of ['Blue 1','Blue 2','Blue 3','Lime','Amber','Orange','Red 1','Red 2'].entries())range(grid,label,'channel-'+i,0,100,1,'%');detail.append(grid);feedback(detail);
  }else{
    detail.append(el('p','Selected values apply after your touch settles.','muted'));
    const grid=el('div',undefined,'white-grid');range(grid,'Colour temperature','cct',1600,10000,100,'K');range(grid,'Light level','intensity',0,1900,25,'controller units');detail.append(grid);feedback(detail);
  }
}
function range(parent,title,key,low,high,step,unit){
  const box=el('section',undefined,'range-card'),heading=el('h3',title);const row=el('div',undefined,'range-value'),output=el('input');output.type='number';output.required=true;output.id='value-'+key;output.className='numeric-value';output.min=low;output.max=high;output.step=step;output.inputMode='numeric';output.setAttribute('aria-label',title+' value');const units=el('small',unit),steps=el('div',undefined,'steps');
  const input=el('input');input.type='range';input.id=key;input.min=low;input.max=high;input.step=step;input.dataset.range=key;input.setAttribute('aria-label',title);
  function selected(){dragging=true;rangeRevision??=state?.revision;output.value=input.value;}
  input.oninput=selected;input.onchange=()=>{selected();commitRange(key);};
  output.onfocus=()=>{dragging=true;rangeRevision??=state?.revision;};
  let cancelEdit=false;
  output.onchange=()=>{if(cancelEdit)return;if(!output.checkValidity()){output.reportValidity();return;}input.value=output.value;selected();commitRange(key);};
  output.onblur=()=>{if(!posting){dragging=false;rangeRevision=null;sync();}};
  output.onkeydown=event=>{if(event.key==='Enter'){event.preventDefault();output.blur();}else if(event.key==='Escape'){cancelEdit=true;output.value=input.value;dragging=false;rangeRevision=null;output.blur();cancelEdit=false;sync();}};
  for(const [label,delta] of (key.startsWith('channel')?[]:[['−',-step],['+',step]])){const b=button(label,()=>{input.value=Math.max(low,Math.min(high,Number(input.value)+delta));selected();commitRange(key);},{action:key.startsWith('channel')?'channels':'cct'});b.setAttribute('aria-label',(delta<0?'Decrease ':'Increase ')+title.toLowerCase());steps.append(b);}
  row.append(output,units,steps);const limits=el('div',undefined,'limits');limits.append(el('span','Min '+low.toLocaleString()+' '+unit),el('span','Max '+high.toLocaleString()+' '+unit));box.append(heading,row,input,limits);parent.append(box);
}
function commitRange(key){if(key.startsWith('channel'))command('channels',{values:Array.from({length:8},(_,i)=>Number($('channel-'+i).value))},rangeRevision);else command('cct',{cct:Number($('cct').value),intensity:Number($('intensity').value)},rangeRevision);}
function guide(root,index){
  const topics=(state?.guide||content.guide);root.append(el('h2','Demo & guide'));
  if(index<0||!topics[index]){root.append(el('p','Choose a topic. Exploring this guide does not operate equipment.','muted'));const grid=el('div',undefined,'topics');for(const [i,t] of topics.entries()){const a=link(t.title,'guide-'+i,({on:'white',home:'home',experiment:'experiment',health:'system',room:'white'})[t.icon]);a.className='topic';grid.append(a);}root.append(grid);return;}
  const t=topics[index],card=el('article',undefined,'card topic-body'),head=el('div',undefined,'topic-head');head.append(icon(({on:'white',home:'home',experiment:'experiment',health:'system',room:'white'})[t.icon]),el('h3',t.title));card.append(head);for(const p of t.text.split('\n\n'))card.append(el('p',p));root.append(card);
  const nav=el('nav',undefined,'row');nav.append(link('All topics','guide','guide'));if(index>0)nav.append(link('Previous','guide-'+(index-1)));if(index<topics.length-1)nav.append(link('Next','guide-'+(index+1)));root.append(nav);
}
function system(parent){
  const cards=el('div',undefined,'health-grid');for(const [id,title] of [['panel-health','Panel health'],['room-health','Room connection']]){const card=el('section',undefined,'card'),text=el(id==='panel-health'?'div':'p',undefined,'muted');text.id=id;if(id==='panel-health')for(const key of ['panel-memory','panel-storage','panel-power']){const line=el('p');line.id=key;text.append(line);}card.append(el('h3',title),text);cards.append(card);}parent.append(cards);
  powerControls(parent);
  const row=el('label',undefined,'help-select');row.append(el('span','Help topic'));const select=el('select');select.setAttribute('aria-label','Help topic');select.id='help-topic';row.append(select);parent.append(row);
  const topics=state?.help||content.help;for(const [i,t] of topics.entries()){const option=el('option',t.title);option.value=i;select.append(option);}select.value=chosenHelp;select.onchange=()=>{chosenHelp=Number(select.value);renderHelp();};const detail=el('div');detail.id='help-detail';parent.append(detail);renderHelp();
  const a=el('a','More diagnostics');a.href=window.SCR_DEMO?'#tools-system':'/diagnostics';parent.append(a);
}
function powerControls(parent){
  const card=el('section',undefined,'card power-controls');card.id='panel-power-controls';card.append(el('h3','Panel power'),el('p','These actions affect this touch panel and its website. They do not stop the room computer or connected recorders. Stop recordings and experiments first.','muted'));
  const status=el('p','Power controls unavailable.','power-status');status.id='power-status';status.setAttribute('role','status');card.append(status);
  const actions=el('div',undefined,'row');for(const [operation,label] of [['reboot','Restart panel'],['shutdown','Shut down panel']]){const b=button(label,()=>{if(!powerAllowed(operation))return;powerChoice={operation,revision:state.revision};$('power-confirm-title').textContent=operation==='reboot'?'Restart this panel?':'Shut down this panel?';$('power-confirm-text').textContent=operation==='reboot'?'Controls and this website will be unavailable while the panel restarts.':'Controls and this website will be unavailable until the panel is powered on again.';$('power-ack').checked=false;$('power-confirm').textContent=operation==='reboot'?'Confirm restart':'Confirm shutdown';$('power-confirmation').hidden=false;syncPower();$('power-ack').focus();});b.id='power-'+operation;b.disabled=true;actions.append(b);}card.append(actions);
  const confirm=el('section',undefined,'power-confirmation');confirm.id='power-confirmation';confirm.hidden=true;confirm.setAttribute('aria-labelledby','power-confirm-title');const title=el('h3');title.id='power-confirm-title';const text=el('p');text.id='power-confirm-text';const ack=el('label',undefined,'power-ack'),input=el('input');input.type='checkbox';input.id='power-ack';input.onchange=syncPower;ack.append(input,el('span','I have stopped any recording or experiment'));
  const row=el('div',undefined,'row'),cancel=button('Cancel',()=>{const operation=powerChoice?.operation;powerChoice=null;confirm.hidden=true;$('power-'+operation)?.focus();}),submit=button('Confirm',()=>{if(!powerChoice||!input.checked||!powerAllowed(powerChoice.operation))return;const choice=powerChoice;command('power',{operation:choice.operation,confirmed:true},choice.revision);});submit.id='power-confirm';submit.className='power-submit';submit.disabled=true;row.append(cancel,submit);confirm.append(title,text,ack,row);card.append(confirm);parent.append(card);
}
function powerAllowed(operation){return !!state?.available&&!!state?.power?.available&&state.power.actions?.[operation]===true&&!posting&&!unknown&&!state.busy&&!state.experiment?.running&&state.mode!=='original'&&state.lights?.state!=='failed'&&!powerRequest?.accepted;}
function syncPower(){
  if(!$('panel-power-controls'))return;
  for(const operation of ['reboot','shutdown'])$('power-'+operation).disabled=!powerAllowed(operation);
  if($('power-confirm'))$('power-confirm').disabled=!powerChoice||!$('power-ack').checked||!powerAllowed(powerChoice.operation);
  let text=state?.power?.message||'Power controls unavailable. Ask the room host to check this panel.';
  if(powerRequest?.accepted&&state?.available&&state.power?.phase==='ready'&&state.session===powerRequest.session)text=powerRequest.operation==='reboot'?'Restart requested. Waiting for this panel to finish.':'Shutdown requested. Waiting for this panel to finish.';
  if(powerRequest?.accepted&&!state?.available)text=powerRequest.operation==='reboot'?'The panel is restarting. This website will reconnect when it is ready.':'The panel is shutting down. This website will disconnect until the panel is powered on again.';
  update('power-status',text);
}
function renderHelp(){if(!$('help-detail'))return;const topic=(state?.help||content.help)[chosenHelp];$('help-detail').replaceChildren();if(!topic)return;
  const card=el('section',undefined,'card');for(const p of topic.text.split('\n\n'))card.append(el('p',p));$('help-detail').append(card);
  if(topic.commands){$('help-detail').append(el('p','Room host reference · copy only. These commands are never run by this website.','subtle'));
    const reference=topic.reference,steps=reference?.steps?.length?reference.steps:[{title:topic.title,commands:topic.commands,command_tokens:topic.command_tokens}];
    const head=el('div',undefined,'reference-head');head.append(el('div',reference?reference.machine+' · '+reference.effect:'Reference commands',['Start services','Restart computer'].includes(topic.title)?'reference-warning':'muted'),copyButton('Copy commands',topic.commands));$('help-detail').append(head);
    for(const [index,step] of steps.entries()){
      const block=el('article',undefined,'command command-step'),bar=el('div',undefined,'command-head'),pre=el('pre'),code=el('code');
      bar.append(el('h3',(steps.length>1?(index+1)+'. ':'')+step.title),copyButton('Copy command',step.commands));block.append(bar);
      if(step.why)block.append(el('p',step.why,'command-why'));
      for(const token of step.command_tokens||[{text:step.commands,kind:'text'}])code.append(el('span',token.text,'syntax-'+token.kind));
      pre.append(code);block.append(pre);
      if(step.expect){const expected=el('div',undefined,'command-expect');expected.append(el('strong','What to expect'),el('p',step.expect));block.append(expected);}
      $('help-detail').append(block);
    }
    if(reference?.documentation){const a=el('a',reference.documentation.label,'documentation-link');a.href=reference.documentation.url;a.target='_blank';a.rel='noopener noreferrer';$('help-detail').append(a);}
  }
}
function copyButton(label,value){return button(label,async event=>{const b=event.currentTarget;try{await copy(value);b.textContent='Copied';}catch(_){b.textContent='Select text to copy';}setTimeout(()=>{if(b.isConnected)b.textContent=label;},1800);});}
async function copy(value){
  if(navigator.clipboard&&window.isSecureContext){try{await navigator.clipboard.writeText(value);return;}catch(_){}}
  const active=document.activeElement,input=el('textarea');input.value=value;input.className='visually-hidden';document.body.append(input);input.select();const ok=document.execCommand('copy');input.remove();active?.focus({preventScroll:true});if(!ok)throw Error('Copy unavailable');
}
function legacy(root){root.append(el('h2','Legacy view'),el('p','Legacy is the original application on the touch panel. Its device controls remain on that panel.','muted'));
  const preview=el('div',undefined,'legacy-preview'),head=el('div',undefined,'legacy-header');head.append(el('strong','Smart Conference Room'),el('span','Legacy view','badge'),button('Home',()=>command('home').then(ok=>{if(ok)location.hash='home';}),{icon:'home',action:'home'}));preview.append(head,el('p','The matching panel header stays visible above the original controls. Use Home to return to everyday lighting.'));root.append(preview);
  root.append(button('Open Legacy on touch panel',()=>command('legacy'),{action:'legacy'}),el('p','Opening Legacy restores the starting light settings before handing over. Blind controls remain disabled here; do not operate the original blind controls.','subtle'));
}
function update(id,text){if($(id)&&$(id).textContent!==String(text))$(id).textContent=text;}
function sync(){
  const p=state?.preferences||{},s=state?.lights||{},available=state?.available===true;
  const version=String(state?.app_version||content.app_version||'').match(/^\d+\.\d+\.\d+/)?.[0]||'';
  for(const badge of document.querySelectorAll('.version-badge')){badge.textContent=version;badge.hidden=!version;}
  update('app-version',version?'Version '+version:'');
  if($('app-build')){const build=state?.build_commit;$('app-build').hidden=!/^[0-9a-f]{7,40}$/.test(build||'');update('app-build',build?'Build '+build.slice(0,7):'');}
  if(state?.palette)window.SCRDesign.apply(state.palette,p.resolved_theme);
  update('connection',!available&&powerRequest?.accepted?(powerRequest.operation==='reboot'?'Restarting panel':'Shutting down panel'):!available?'Panel unavailable':state.mode==='original'?'Legacy':state.busy?'Sending':state.can_control?'Ready':s.state==='failed'?'Uncertain':'Controls unavailable');
  if($('blind-group')){$('blind-group').hidden=p.blinds_display==='hidden';$('essentials').classList.toggle('single',p.blinds_display==='hidden');$('blind-group').classList.toggle('disabled-group',!state?.blinds?.available);update('blind-status',state?.blinds?.available?'Ready':'Disabled');}
  update('blind-reason',state?.blinds?.connected?state.blinds.reason:content.blinds_unavailable);
  for(const b of document.querySelectorAll('[data-action]')){const a=b.dataset.action,lighting=['on','off','cct','preset','channels'].includes(a),session=['start','pause','previous','next','mark'].includes(a);b.disabled=posting||Boolean(unknown)||!available||state.busy||(a==='blind'?!state?.blinds?.available:lighting?!state.can_control:session?!state.can_session:false);}
  for(const input of document.querySelectorAll('[data-range]')){const number=$('value-'+input.dataset.range);input.disabled=number.disabled=posting||Boolean(unknown)||!available||!state.can_control;if(!dragging){const k=input.dataset.range,value=k.startsWith('channel')?s.channels?.[Number(k.split('-')[1])]:s[k];if(value!==undefined){input.value=value;number.value=value;}}}
  for(const b of document.querySelectorAll('[data-choice]'))b.classList.toggle('selected',String(p[b.dataset.choice])===b.dataset.value);
  for(const b of document.querySelectorAll('[data-action=on],[data-action=off]'))b.classList.toggle('selected',available&&!posting&&!unknown&&s.power===b.dataset.action&&state.can_control);
  for(const b of document.querySelectorAll('[data-preset]'))b.classList.toggle('selected',available&&!posting&&!unknown&&s.scene===b.dataset.preset&&state.can_control);
  update('light-message',!available?'Panel unavailable. Controls are disabled.':state.experiment?.running?'Instructions are running. Pause Experiment mode before using lighting.':state.mode==='original'?'Use Home to return from Legacy.':s.message||'Lighting unavailable.');update('light-recent','Recent settings: '+(s.recent||'Not checked')+(s.confirmed_age_s===null||s.confirmed_age_s===undefined?'':' · '+(s.confirmed_age_s<60?'just now':Math.floor(s.confirmed_age_s/60)+' min ago')));
  const e=state?.experiment;if(e){update('profile-title',e.profile.title);update('instruction',e.profile.stages[e.stage]);update('elapsed',Math.floor(e.elapsed_s/60).toString().padStart(2,'0')+':'+(e.elapsed_s%60).toString().padStart(2,'0'));update('session-state','Instruction '+(e.stage+1)+' of '+e.profile.stages.length+' · '+(e.running?'Running':'Paused'));update('annotation',e.annotation);
    if($('marks')&&!$('marks').children.length)for(const label of e.profile.annotations){const b=button(label,()=>command('mark',{label}),{action:'mark'});b.disabled=posting||Boolean(unknown)||!available||!state.can_session;$('marks').append(b);}
  }
  update('schedule','Light from '+minutes(p.light_at??420)+' · Dark from '+minutes(p.dark_at??1140));
  const h=state?.health;if(h){update('panel-memory',h.error?'Resource reading unavailable':`Memory: ${h.ram_available??'—'} / ${h.ram_total??'—'} MiB free`);update('panel-storage',h.error?'':`Storage: ${h.disk_available??'—'} GiB free · CPU: ${h.temperature??'—'} °C`);update('panel-power',h.power?'Power: '+h.power:'Power reading unavailable');$('panel-power')?.classList.toggle('system-warning',h.power?.startsWith('Current')===true);}update('room-health',state?.room_status||'No current room observation.');
  syncPower();weather();
}
function minutes(value){return Math.floor(value/60).toString().padStart(2,'0')+':'+(value%60).toString().padStart(2,'0');}
function weather(){
  const p=state?.preferences||{},value=state?.weather,tz=state?.timezone||'America/New_York',now=new Date();
  update('clock',new Intl.DateTimeFormat('en-US',{timeZone:tz,hour:'numeric',minute:'2-digit',hour12:p.clock!=='24'}).format(now));update('date',new Intl.DateTimeFormat('en-US',{timeZone:tz,weekday:'long',year:'numeric',month:'long',day:'numeric'}).format(now));
  if(!value){update('condition','Weather unavailable');update('temperature','—');update('weather-source','No current outdoor reading. Outdoor weather is separate from room sensors.');if($('weather-stats'))$('weather-stats').hidden=true;if($('weather-notice')){$('weather-notice').hidden=false;update('weather-notice','No current outdoor reading.');}if($('daylight'))$('daylight').hidden=true;if($('weather-art')){$('weather-art').replaceChildren();delete $('weather-art').dataset.symbol;}return;}
  const parts=Object.fromEntries(new Intl.DateTimeFormat('en-CA',{timeZone:tz,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(now).map(v=>[v.type,v.value]));
  const today=`${parts.year}-${parts.month}-${parts.day}`,local=`${today}T${parts.hour}:${parts.minute}`,current=value.sunrise.slice(0,10)===today&&value.sunset.slice(0,10)===today,night=current&&(local<value.sunrise||local>=value.sunset),old=!current||value.model_time.slice(0,10)!==today||(state.weather_age_s??Infinity)>1800;
  const unit=p.temperature||'f',convert=v=>unit==='c'?(v-32)*5/9:v,degree=v=>Math.round(convert(v))+'°';update('temperature',degree(value.temperature_f)+' '+unit.toUpperCase());update('condition',value.condition);
  if($('weather-stats'))$('weather-stats').hidden=old;if($('weather-notice'))$('weather-notice').hidden=!old;update('weather-notice',old?'Earlier reading: '+value.model_time.replace('T',' '):'');
  for(const [key,reading,isRain] of [['feels',value.feels_like_f,false],['rain',value.rain_chance,true],['high',value.high_f,false],['low',value.low_f,false]])update('weather-'+key,Number.isFinite(reading)?(isRain?Math.round(reading)+'%':degree(reading)):'—');
  update('weather-source','Open-Meteo · model '+value.model_time.replace('T',' ')+' · Outdoor weather is separate from room sensors.');
  let name=value.code===0?(night?'moon':'sun'):[1,2].includes(value.code)?(night?'cloud-moon':'cloud-sun'):value.code===3?'cloud':[45,48].includes(value.code)?'cloud-fog':[71,73,75,77,85,86].includes(value.code)?'cloud-snow':[95,96,99].includes(value.code)?'cloud-lightning':[51,53,55,56,57,61,63,65,66,67,80,81,82].includes(value.code)?'cloud-rain':'circle-question-mark';if(!current&&[0,1,2].includes(value.code))name='circle-question-mark';
  if($('weather-art')){$('weather-art').style.color=state?.palette?.[content.weather_accents?.[name]||'icon_colour']||'var(--icon-colour)';if($('weather-art').dataset.symbol!==name){$('weather-art').replaceChildren(icon('weather-'+name));$('weather-art').dataset.symbol=name;}}
  if($('daylight')){$('daylight').hidden=old;if(!old){const minute=s=>Number(s.slice(11,13))*60+Number(s.slice(14,16)),rise=minute(value.sunrise),set=minute(value.sunset),time=Number(parts.hour)*60+Number(parts.minute);$('daylight-fill').style.width=(Math.max(0,Math.min(1,(time-rise)/(set-rise)))*100)+'%';const remaining=(time<rise?rise:set)-time;update('daylight-label',time>=set?'After sunset · night':`Sun ${time<rise?'rises':'sets'} in ${Math.floor(remaining/60)} h ${remaining%60} min`);update('sunrise','Sunrise '+value.sunrise.slice(11,16));update('sunset','Sunset '+value.sunset.slice(11,16));}}
}
let fetching=false;
async function refresh(){
  if(fetching||document.hidden)return;
  fetching=true;
  try{
    const response=await fetch('/api/controller',{cache:'no-store',signal:AbortSignal.timeout(3500)});
    if(!response.ok)throw Error();
    state=await response.json();
    const receipt=unknown&&state.receipts?.find(r=>r.id===unknown);
    if(receipt){
      if(powerRequest?.id===unknown){
        if(receipt.ok){powerRequest.accepted=true;powerChoice=null;if($('power-confirmation'))$('power-confirmation').hidden=true;message('The panel received the power request. Check its progress below.');}
        else{powerRequest=null;message(receipt.detail||'Power request was not accepted.');}
      }else message('The panel received the command. Check its current confirmation below.');
      unknown=null;
    }
    if(powerRequest&&state.power?.phase==='failed'){powerRequest=null;message(state.power.message||'Power operation stopped. The panel remains available.');}
    if(powerRequest?.accepted&&state.available===true&&state.session!==powerRequest.session&&state.power?.phase==='ready'){const operation=powerRequest.operation;powerRequest=null;message(operation==='reboot'?'Panel restarted. This website is connected again.':'The panel is back online. This website is connected again.');}
    if(state.guide)content={...content,guide:state.guide,help:state.help};
    if(!view||(!$('help-topic')&&view==='tools-system')||(view.startsWith('guide')&&!$('app').children.length)){view='';layout();}
    sync();
  }catch(_){
    if(state)state.available=false;
    if(powerRequest?.accepted)message(powerRequest.operation==='reboot'?'The panel is restarting. This website will reconnect when it is ready.':'The panel is shutting down. This website will disconnect until the panel is powered on again.');
    sync();
  }finally{fetching=false;}
}
document.addEventListener('click',event=>{const a=event.target.closest('a[href="#home"]');if(a&&state?.available&&state.mode!=='room'){event.preventDefault();command('home').then(ok=>{if(ok)location.hash='home';});}});
window.addEventListener('hashchange',layout);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
window.addEventListener('scr-preview-change',()=>{view='';layout();});
(async()=>{try{content=await(await fetch('/room-content.json')).json();}catch(_){}layout();await refresh();setInterval(refresh,1000);setInterval(weather,1000);})();
