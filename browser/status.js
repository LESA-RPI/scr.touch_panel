'use strict';
const byId = id => document.getElementById(id);
const text = (id, value) => { const node = byId(id); if (node && node.textContent !== value) node.textContent = value; };
const numeric = value => typeof value === 'number' && Number.isFinite(value);
const diagnostic = document.body.dataset.view === 'diagnostics';
const roomTime = new Intl.DateTimeFormat('en-US', {timeZone:'America/New_York',hour:'numeric',minute:'2-digit'});
const roomDate = new Intl.DateTimeFormat('en-US', {timeZone:'America/New_York',weekday:'long',month:'long',day:'numeric',year:'numeric'});
const roomParts = new Intl.DateTimeFormat('en-CA', {timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
const age = seconds => seconds < 60 ? `${Math.floor(seconds)} seconds ago` : `${Math.floor(seconds/60)} minutes ago`;
function localTime(value) { const [h,m] = value.slice(11,16).split(':').map(Number); return `${h%12||12}:${String(m).padStart(2,'0')} ${h<12?'AM':'PM'}`; }
function badge(node, value, colour='') { if (!node) return; node.textContent=value; node.className=(node.id==='connection'||node.id==='room-connection'?'connection':'service-state')+' '+colour; }
let snapshot=null, receivedAt=0, pending=false, failed=false;
function weather(elapsed) {
  const info=snapshot.weather || {state:'unconfigured',data:null};
  const value=info.data;
  if (!value) {
    text('weather-temperature','—'); text('weather-condition',info.state==='unconfigured'?'Weather not configured':'Weather unavailable');
    text('weather-source','No sample values are substituted.');
    if (byId('daylight')) byId('daylight').hidden=true;
    return;
  }
  const parts=Object.fromEntries(roomParts.formatToParts(new Date()).map(item=>[item.type,item.value]));
  const today=`${parts.year}-${parts.month}-${parts.day}`;
  const stale=failed||info.state!=='available'||!numeric(info.observation_age_s)||info.observation_age_s+elapsed>1800||value.model_time.slice(0,10)!==today;
  text('weather-temperature',`${Math.round(value.temperature_f)} °F`);
  text('weather-condition',value.condition);
  text('weather-secondary',`${Math.round(value.temperature_c)} °C · Troy outdoors`);
  text('weather-source',`${stale?'Earlier weather · '+value.model_time.slice(0,10)+' · ':''}Weather as of ${localTime(value.model_time)} · Open-Meteo`);
  const daylight=byId('daylight');
  if (!daylight) return;
  daylight.hidden=stale||value.sunrise.slice(0,10)!==today||value.sunset.slice(0,10)!==today;
  if (daylight.hidden) return;
  const minutes=value=>Number(value.slice(11,13))*60+Number(value.slice(14,16));
  const rise=minutes(value.sunrise), set=minutes(value.sunset), now=Number(parts.hour)*60+Number(parts.minute);
  const progress=Math.max(0,Math.min(1,(now-rise)/(set-rise)));
  byId('daylight-fill').style.width=`${progress*100}%`;
  text('sunrise',`Sunrise ${localTime(value.sunrise)}`); text('sunset',`Sunset ${localTime(value.sunset)}`);
  const remaining=(now<rise?rise:set)-now;
  text('daylight-note',now>=set?'After sunset · Night':`${now<rise?'Sunrise':'Sunset'} in ${Math.floor(remaining/60)} h ${remaining%60} min`);
}
function render() {
  text('clock',roomTime.format(new Date())); text('date',roomDate.format(new Date()));
  if (!snapshot) { badge(byId('connection'),failed?'Page connection lost':'Checking…',failed?'warning':''); return; }
  const elapsed=Math.max(0,(performance.now()-receivedAt)/1000);
  if (!diagnostic) {
    weather(elapsed);
    text('preview-note',snapshot.room.state==='unconfigured'?'Local preview · No room connection is configured. Use the cabinet panel for controls.':'Use the cabinet panel for lighting. Blind controls are not enabled; this website operates no equipment.');
    return;
  }
  const sampleAge=snapshot.sample_age_s+elapsed, stale=failed||sampleAge>90;
  const host=snapshot.host, room=snapshot.room;
  badge(byId('connection'),failed?'Page connection lost':stale?'Readings are stale':'Updating normally',stale?'warning':'good');
  text('freshness',`Computer readings ${age(sampleAge)}${stale?' · not current':''}.`);
  text('host-label',snapshot.host_label);
  text('source-description',room.state==='unconfigured'?`Host-only preview · These readings are from ${snapshot.host_label}, not the cabinet Pi.`:`Host readings from ${snapshot.host_label}. Room interfaces are a separate observation.`);
  text('memory',numeric(host.memory_available_mib)?`${host.memory_available_mib} MiB`:'Unavailable');
  text('memory-note',numeric(host.memory_total_mib)?`Available of ${host.memory_total_mib} MiB total`:'Not supported on this host');
  text('temperature',numeric(host.temperature_c)?`${host.temperature_c.toFixed(1)} °C`:'Unavailable');
  const power={warning_now:'Low voltage now',warning_earlier:'Earlier low voltage',no_warning:'No voltage warning',unavailable:'Not available'};
  text('power',power[host.power]||'Not available');
  byId('power').className=`power-value ${String(host.power).startsWith('warning')?'warning':''}`;
  text('uptime',numeric(host.uptime_s)?`Uptime · ${(host.uptime_s/3600).toFixed(1)} hours`:'Uptime unavailable');
  const graphStale=stale||room.state!=='available'||!numeric(room.observation_age_s)||room.observation_age_s+elapsed>90;
  badge(byId('room-connection'),room.state==='unconfigured'?'Not configured':room.state==='available'&&!graphStale?'Service list received':'Current availability unknown',graphStale?'':'good');
  document.querySelectorAll('[data-service]').forEach(card=>{
    const service=room.services.find(item=>item.name===card.dataset.service);
    const labels={advertised:'Service listed',partial:'Some services listed',not_advertised:'Not listed'};
    const label=service?labels[service.state]||'Not checked':'Not checked';
    badge(card.querySelector('.service-state'),service&&graphStale?`Previous: ${label.toLowerCase()}`:label,graphStale?'':service?.state==='advertised'?'good':'warning');
  });
  text('room-note',room.observed_at?`Last service list ${age(room.observation_age_s+elapsed)}${graphStale?' · previous observation':''}.`:'No successful service-list observation.');
}
async function refresh() {
  if (pending||document.hidden) return;
  pending=true;
  const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),4000);
  try {
    const response=await fetch('/api/status',{signal:controller.signal,cache:'no-store'});
    if (!response.ok) throw new Error('Unavailable');
    const next=await response.json();
    if (next.version!==1||next.read_only!==true||!next.host||!next.room||!Array.isArray(next.room.services)||!numeric(next.sample_age_s)) throw new Error('Invalid status');
    snapshot=next; receivedAt=performance.now(); failed=false;
  } catch (_) { failed=true; }
  finally {clearTimeout(timer);pending=false;render();}
}
render(); refresh(); setInterval(render,1000); setInterval(refresh,30000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
