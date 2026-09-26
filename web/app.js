const icons = {dentists:'✦',salons:'✂',restaurants:'◈',gyms:'↗',pharmacies:'✚'};
const state = {scenarios:[],selected:null,filter:'all',ai:false,preview:null};
const el = id => document.getElementById(id);

function node(tag, cls, content) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (content !== undefined) n.textContent = String(content);
  return n;
}

function format(value) {
  if (Array.isArray(value)) return value.map(x => typeof x === 'object' ? (x.label || JSON.stringify(x)) : String(x)).join(', ');
  if (value && typeof value === 'object') return Object.entries(value).map(([k,v]) => `${k.replaceAll('_',' ')}: ${v}`).join(' · ');
  return String(value);
}

function row(target,key,value) {
  const div = node('div');
  div.append(node('dt','',key),node('dd',typeof value === 'object' ? 'long' : '',format(value)));
  target.append(div);
}

function filters() {
  const wrap = el('filters'); wrap.replaceChildren();
  for (const category of ['all','dentists','salons','restaurants','gyms','pharmacies']) {
    const b=node('button',state.filter===category?'active':'',category);
    b.type='button';
    b.onclick=()=>{state.filter=category;filters();renderScenarios()};
    wrap.append(b);
  }
}

function renderScenarios() {
  const list=el('scenario-list');list.replaceChildren();
  const visible=state.scenarios.filter(s=>state.filter==='all'||s.category===state.filter);
  el('scenario-count').textContent=`${visible.length} cases`;
  for (const scenario of visible) {
    const b=node('button','scenario'+(state.selected===scenario.id?' active':''));
    b.type='button';
    b.append(node('span','scenario-icon',icons[scenario.category]||'✳'));
    const details=node('div','scenario-details');
    details.append(node('strong','',scenario.merchant),node('span','',scenario.kind.replaceAll('_',' ')+' · '+scenario.locality));
    b.append(details,node('span','arrow','↗'));
    b.onclick=()=>selectScenario(scenario.id);
    list.append(b);
  }
}

function bubble(sender,text,role) {
  const wrap=node('div','chat-message'+(role==='user'?' user':''));
  const title=node('div','sender');
  title.append(node('span','avatar',role==='user'?'U':'V'),node('span','',sender));
  wrap.append(title,node('p','',text),node('span','time','simulated · just now'));
  el('messages').append(wrap);
  el('chat-area').scrollTop=el('chat-area').scrollHeight;
}

function insight(data) {
  el('insight-empty').hidden=true;el('insight-content').hidden=false;
  el('decision-label').textContent=data.decision==='send'?'Send a useful message':'Stay quiet';
  el('rationale').textContent=data.message?.rationale||data.reason;
  const c=data.context;
  const business=el('business-facts');business.replaceChildren();
  row(business,'Business',c.business);row(business,'Locality',c.locality);
  if(c.customer)row(business,'Customer',c.customer);
  const event=el('event-facts');event.replaceChildren();row(event,'Event',c.event);
  for(const f of c.facts) row(event,f.name,f.value);
  const mf=el('message-facts');mf.replaceChildren();
  if(data.message){row(mf,'Sent as',data.message.send_as.replaceAll('_',' '));row(mf,'CTA',data.message.cta);row(mf,'AI rewrite',data.ai_used?'Applied':'Built-in wording')}
}

async function selectScenario(id) {
  state.selected=id;renderScenarios();
  const scenario=state.scenarios.find(x=>x.id===id);
  el('conversation-title').textContent=scenario?.merchant||'Scenario';
  el('messages').replaceChildren();el('empty-state').hidden=true;
  el('reply-form').hidden=true;
  el('insight-empty').hidden=false;el('insight-content').hidden=true;
  const waiting=node('div','wait-message','Evaluating the event…');el('messages').append(waiting);
  try{
    const res=await fetch('/demo/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({trigger_id:id,ai:state.ai})});
    if(!res.ok)throw Error((await res.json()).detail||`HTTP ${res.status}`);
    const data=await res.json();
    if(state.selected!==id)return;
    state.preview=data;el('messages').replaceChildren();insight(data);
    if(data.decision==='send'){
      bubble(data.message.send_as==='vera'?'Vera':'Merchant via Vera',data.message.body,'assistant');
      el('reply-form').hidden=false;el('reply-input').value='';
    }else{el('messages').append(node('div','wait-message','Vera chose not to send: '+data.reason))}
  }catch(err){el('messages').replaceChildren(node('div','wait-message','Could not load preview: '+err.message))}
}

async function sendReply(ev) {
  ev.preventDefault();const reply=el('reply-input').value.trim();
  if(!reply||!state.selected)return;
  el('reply-button').disabled=true;
  try{
    const res=await fetch('/demo/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({trigger_id:state.selected,reply,ai:false})});
    if(!res.ok)throw Error('Reply preview failed');
    const data=await res.json();
    bubble('Merchant or customer',reply,'user');
    if(data.followup?.action==='send')bubble('Vera',data.followup.text,'assistant');
    else el('messages').append(node('div','wait-message',data.followup?.text||'Vera is waiting.'));
    el('reply-input').value='';
  }catch(err){el('messages').append(node('div','wait-message',err.message))}
  finally{el('reply-button').disabled=false}
}

async function startup(){
  el('reply-form').addEventListener('submit',sendReply);
  filters();
  try{
    const [scenarios,health]=await Promise.all([fetch('/demo/scenarios').then(r=>r.json()),fetch('/v1/healthz').then(r=>r.json())]);
    state.scenarios=scenarios.scenarios;
    state.ai=scenarios.ai_available;
    el('status').innerHTML='';
    el('status').append(node('i'),document.createTextNode(health.status==='ok'?(state.ai?' AI ready':' Bot online'):' Offline'));
    renderScenarios();
    if(state.scenarios.length)selectScenario(state.scenarios[0].id);
  }catch(err){el('status').classList.add('offline');el('status').textContent=' Unable to connect';el('scenario-list').textContent='The service is unavailable. Check the server and refresh.'}
}
startup();
