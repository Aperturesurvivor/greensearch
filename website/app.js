/* ═══════════════════════════════════════════════
   Pure logic, same module.exports contract
═══════════════════════════════════════════════ */
function shrinkSegment(raw) {
  var s = ' ' + raw + ' ';
  var fillers = [
    'i was just wondering if you could possibly','i was just wondering if','just wondering if',
    "i hope you're doing well",'i hope you are doing well',
    'i would appreciate it if you could','i would like you to','i was hoping you could',
    'could you please kindly','could you please','would you please','can you please','please kindly',
    'thank you so much in advance','thanks so much',
    'it is important to note that','please note that','note that',
    'in my opinion','i think that','i believe that',
    'as mentioned before','as i mentioned earlier',
    'to be honest','frankly speaking','in summary','to summarize',
    'hi there','hello','and also','in other words',
    'basically','actually','honestly','obviously','really','very','please','just'
  ];
  fillers.forEach(function(p){
    var re=new RegExp('\\b'+p.replace(/[.*+?^${}()|[\]\\]/g,'\\$&').replace(/ /g,'\\s+')+'\\b','gi');
    s=s.replace(re,'');
  });
  var verbose=[
    ['due to the fact that','because'],['in spite of the fact that','although'],
    ['in order to','to'],['at this point in time','now'],['at the present time','now'],
    ['in the event that','if'],['for the purpose of','for'],
    ['a large number of','many'],['has the ability to','can'],['is able to','can'],
    ['each and every','each'],['first and foremost','first'],
    ['prior to','before'],['subsequent to','after'],
    ['with regard to','about'],['with respect to','about'],
    ['in the near future','soon'],['on a regular basis','regularly']
  ];
  verbose.forEach(function(pair){
    var re=new RegExp('\\b'+pair[0].replace(/ /g,'\\s+')+'\\b','gi');
    s=s.replace(re,pair[1]);
  });
  s=s.replace(/\s+/g,' ').trim();
  s=s.replace(/\s+([.,!?;:])/g,'$1');
  s=s.replace(/,([.!?])/g,'$1');
  s=s.replace(/,\s*$/,'');
  s=s.replace(/([.!?])[.!?]+/g,'$1');
  s=s.replace(/^[^A-Za-z0-9]+/,'');
  if(s) s=s.replace(/(^|[.!?]\s+)([a-z])/g,function(m,p,c){return p+c.toUpperCase();});
  return s;
}
function shrinkPrompt(raw){
  var lines=raw.split('\n');
  // Strip trailing blank lines, then a sign-off line, then a bare name line above it.
  while(lines.length&&!lines[lines.length-1].trim())lines.pop();
  var soRe=/^(best regards|kind regards|regards|cheers|sincerely|thanks|thank you)[,.]?(\s+[A-Za-z][A-Za-z .\-]{0,39})?\s*$/i;
  var nameRe=/^[A-Za-z][A-Za-z .\-]{0,39}$/;
  if(lines.length>=2){
    var last=lines[lines.length-1].trim(),prev=lines[lines.length-2].trim();
    if(soRe.test(prev)&&nameRe.test(last)&&last.split(/\s+/).length<=4){
      lines.pop();lines.pop();
    } else if(soRe.test(last)){
      lines.pop();
    }
  } else if(lines.length===1&&soRe.test(lines[0].trim())){
    lines.pop();
  }
  while(lines.length&&!lines[lines.length-1].trim())lines.pop();
  var cleaned=lines.join('\n');
  return cleaned.split(/(```[\s\S]*?```)/g).map(function(p){return p.startsWith('```')?p:shrinkSegment(p);}).join('').replace(/[ \t]+\n/g,'\n').trim();
}

/* LCS-based word diff with punctuation-normalised matching */
function normWord(w){return w.toLowerCase().replace(/[^a-z0-9]/g,'');}
function wordDiff(raw,shrunk){
  if(raw===shrunk)return null;
  var a=raw.split(/\s+/),b=shrunk.split(/\s+/);
  var na=a.map(normWord),nb=b.map(normWord);
  var m=a.length,n=b.length;
  var dp=[];
  for(var i=0;i<=m;i++){dp[i]=new Array(n+1).fill(0);}
  for(var i=1;i<=m;i++)for(var j=1;j<=n;j++)
    dp[i][j]=na[i-1]===nb[j-1]?dp[i-1][j-1]+1:Math.max(dp[i-1][j],dp[i][j-1]);
  var tokens=[],i=m,j=n;
  while(i>0&&j>0){
    if(na[i-1]===nb[j-1]){tokens.unshift({w:a[i-1],t:'k'});i--;j--;}
    else if(dp[i-1][j]>=dp[i][j-1]){tokens.unshift({w:a[i-1],t:'r'});i--;}
    else j--;
  }
  while(i>0){tokens.unshift({w:a[i-1],t:'r'});i--;}
  /* words in shrunk not matched in raw = substitutions */
  var rawNorm=new Set(na);
  var added=b.filter(function(w){return!rawNorm.has(normWord(w));});
  return{tokens:tokens,added:added};
}

function stripCodeFences(text){return text.replace(/```[\s\S]*?```/g,' ');}
function proseWordCount(text){var p=stripCodeFences(text).trim();return p?p.split(/\s+/).length:0;}
var SPROUT_MAX=12,FOREST_MIN=35;
var COMPLEXITY_MARKERS=['compare','pros and cons','versus','in detail','step by step','trade-off','trade-offs','explain both'];
function routeMode(shrunk){
  var prose=stripCodeFences(shrunk),p=prose.toLowerCase(),words=proseWordCount(shrunk);
  var hasMarker=COMPLEXITY_MARKERS.some(function(m){return p.indexOf(m)>-1;});
  var qCount=(prose.match(/\?/g)||[]).length;
  if(hasMarker||qCount>=2||words>=FOREST_MIN)return'forest';
  if(words<=SPROUT_MAX)return'sprout';
  return'canopy';
}
function cacheKey(shrunk){return shrunk.toLowerCase().replace(/[^a-z0-9 ]/g,'').replace(/\s+/g,' ').trim();}
function estTokens(text){return Math.max(1,Math.round(text.trim().split(/\s+/).length*1.33));}
if(typeof module!=='undefined'&&module.exports){
  module.exports={shrinkPrompt,routeMode,estTokens};
}

/* ═══════════════════════════════════════════════
   DOM
═══════════════════════════════════════════════ */
if(typeof document!=='undefined'){
document.addEventListener('DOMContentLoaded',function(){

/* ── V10: single locked palette. Drop any stored V9 theme choice. ── */
try{localStorage.removeItem('arboris-theme-v1');document.documentElement.removeAttribute('data-theme');}catch(e){}

/* State: live turns only. Old demo keys are deleted on load; live keys
   migrate from the old greensearch-* names once, never overwriting new keys. */
(function(){
  try{
    localStorage.removeItem('arboris-demo-v1');localStorage.removeItem('greensearch-demo-v1');
    var old=localStorage.getItem('greensearch-live-v1');
    if(old!==null){if(localStorage.getItem('arboris-live-v1')===null)localStorage.setItem('arboris-live-v1',old);localStorage.removeItem('greensearch-live-v1');}
    var oldUrl=localStorage.getItem('greensearch-live-backend-url');
    if(oldUrl!==null){if(localStorage.getItem('arboris-live-backend-url')===null)localStorage.setItem('arboris-live-backend-url',oldUrl);localStorage.removeItem('greensearch-live-backend-url');}
  }catch(e){}
})();
var epoch=0;
var seqCounter=0;
var reduceMotion=window.matchMedia('(prefers-reduced-motion:reduce)').matches;
var chatEl=document.getElementById('chat');
var inputEl=document.getElementById('ci');
var pendingAttachments=[],attachmentReads=0,filesDbPromise=null;
var attachmentListEl=document.getElementById('attachment-list');
var liveEl=document.getElementById('sr-live');

function attachmentRefs(files){
  return (files||[]).map(function(f){return{id:f.id,name:f.name,type:f.type,size:f.size};});
}
function fileStorage(action,value){
  if(!filesDbPromise)filesDbPromise=new Promise(function(resolve,reject){
    var request=indexedDB.open('arboris-files-v1',1);
    request.onupgradeneeded=function(){request.result.createObjectStore('files',{keyPath:'id'});};
    request.onsuccess=function(){resolve(request.result);};request.onerror=function(){reject(request.error);};
  });
  return filesDbPromise.then(function(db){return new Promise(function(resolve,reject){
    var tx=db.transaction('files',action==='get'?'readonly':'readwrite'),store=tx.objectStore('files');
    var request=action==='put'?store.put(value):action==='delete'?store.delete(value):store.get(value),result;
    request.onsuccess=function(){result=request.result;};
    tx.oncomplete=function(){resolve(result);};tx.onerror=tx.onabort=function(){reject(tx.error||request.error);};
  });});
}
function renderFileCards(container,files,removable){
  container.innerHTML='';
  files.forEach(function(file){
    var card=document.createElement('div');card.className='attachment-card';
    if(file.type&&file.type.indexOf('image/')===0){
      var image=document.createElement('img');image.alt=file.name;image.hidden=true;card.appendChild(image);
      if(file.data){image.src=file.data;image.hidden=false;}
      else fileStorage('get',file.id).then(function(stored){if(stored&&stored.data){image.src=stored.data;image.hidden=false;}}).catch(function(){});
    }else{
      var symbol=document.createElement('span');symbol.className='file-symbol';symbol.setAttribute('aria-hidden','true');
      symbol.innerHTML='<svg width="18" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 3H6v18h12V7l-4-4Z"/><path d="M14 3v5h4M9 12h6M9 16h6"/></svg>';card.appendChild(symbol);
    }
    var info=document.createElement('span'),name=document.createElement('span');name.className='attachment-name';name.textContent=file.name;info.appendChild(name);
    var size=document.createElement('small');size.className='attachment-size';size.textContent=file.loading?'Loading…':file.size>=1048576?(file.size/1048576).toFixed(1)+' MB':Math.max(1,Math.round((file.size||0)/1024))+' KB';info.appendChild(size);card.appendChild(info);
    if(removable){var remove=document.createElement('button');remove.type='button';remove.className='attachment-remove';remove.textContent='×';remove.dataset.removeAttachment=file.id;remove.setAttribute('aria-label','Remove '+file.name);card.appendChild(remove);}
    container.appendChild(card);
  });
}
function renderAttachments(){
  attachmentListEl.hidden=!pendingAttachments.length;renderFileCards(attachmentListEl,pendingAttachments,true);
}
function appendMessageFiles(parent,files){
  if(!files||!files.length)return;
  var list=document.createElement('div');list.className='message-attachments';renderFileCards(list,files,false);parent.appendChild(list);
}
function restoreDraftAttachments(refs){
  var id=activeChatId;
  pendingAttachments=(refs||[]).map(function(f){return Object.assign({},f,{loading:true});});renderAttachments();
  if(!pendingAttachments.length)return;
  Promise.all(pendingAttachments.map(function(f){return fileStorage('get',f.id).catch(function(){return null;});})).then(function(files){
    if(activeChatId!==id)return;
    pendingAttachments=pendingAttachments.map(function(f){var index=refs.findIndex(function(ref){return ref.id===f.id;});return index>=0?files[index]:f;}).filter(Boolean);renderAttachments();
    if(files.filter(Boolean).length!==refs.length){showToast('Some files could not be restored. Please attach them again.');saveLiveState();}
  });
}
async function addFiles(files){
  if(!files.length)return;
  if(!activeChatId)newChat();
  var targetId=activeChatId;attachmentReads++;
  try{
    for(var file of files){
      var chats=getChats(),target=chats.find(function(c){return c.id===targetId;});if(!target)break;
      var current=targetId===activeChatId?pendingAttachments:(target.draftAttachments||[]);
      if(current.length>=6){showToast('Attach up to 6 files at a time.');break;}
      if(file.size>5*1048576||current.reduce(function(n,f){return n+(f.size||0);},0)+file.size>10*1048576){showToast('Use files up to 5 MB each and 10 MB in total.');continue;}
      var kind=file.type,extension=file.name.split('.').pop().toLowerCase();
      var binary={png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',gif:'image/gif',webp:'image/webp',pdf:'application/pdf'};
      kind=binary[extension]||kind;
      var item={id:newLiveSession().replace('web-','f-'),name:file.name,type:kind,size:file.size};
      if(['image/png','image/jpeg','image/gif','image/webp','application/pdf'].indexOf(kind)>=0){
        item.data=await new Promise(function(resolve,reject){var reader=new FileReader();reader.onload=function(){resolve(reader.result);};reader.onerror=function(){reject(reader.error);};reader.readAsDataURL(file);});
        item.data=item.data.replace(/^data:[^;]*;/,'data:'+kind+';');
      }else if(kind.indexOf('text/')===0||/^(txt|md|markdown|csv|tsv|json|jsonl|xml|yaml|yml|log|html|htm|css|js|mjs|ts|tsx|jsx|py|rb|go|rs|java|c|h|cpp|cs|sh|sql|toml|ini|rtf)$/.test(extension)){
        item.type='text/plain';item.text=await file.text();
        if(item.text.length>200000||item.text.indexOf('\u0000')>=0){showToast('Use text files with up to 200,000 characters.');continue;}
      }else{showToast('Use a PNG, JPG, GIF, WebP, PDF or text file.');continue;}
      await fileStorage('put',item);
      if(targetId===activeChatId){pendingAttachments.push(item);renderAttachments();saveLiveState();}
      else{
        chats=getChats();target=chats.find(function(c){return c.id===targetId;});
        if(target){target.draftAttachments=(target.draftAttachments||[]).concat(attachmentRefs([item]));saveChats(chats);}
      }
    }
    if(targetId===activeChatId){inputEl.focus();announce(pendingAttachments.length+' files attached.');}
  }catch(e){showToast('The file could not be attached. Please try again.');}
  finally{attachmentReads--;}
}
document.getElementById('attach-btn').addEventListener('click',function(){document.getElementById('file-input').click();});
document.getElementById('file-input').addEventListener('change',function(e){addFiles(Array.from(e.target.files));e.target.value='';});
attachmentListEl.addEventListener('click',function(e){
  var button=e.target.closest('[data-remove-attachment]');if(!button)return;
  var id=button.dataset.removeAttachment;pendingAttachments=pendingAttachments.filter(function(f){return f.id!==id;});
  renderAttachments();saveLiveState();fileStorage('delete',id).catch(function(){});
});
var fileDragDepth=0;
function hasDraggedFiles(e){return e.dataTransfer&&Array.from(e.dataTransfer.types||[]).indexOf('Files')>=0;}
function clearFileDrag(){fileDragDepth=0;document.body.classList.remove('file-dragging');}
document.addEventListener('dragenter',function(e){if(!hasDraggedFiles(e))return;e.preventDefault();fileDragDepth++;document.body.classList.add('file-dragging');});
document.addEventListener('dragover',function(e){if(hasDraggedFiles(e)){e.preventDefault();e.dataTransfer.dropEffect='copy';}});
document.addEventListener('dragleave',function(e){
  if(!fileDragDepth)return;fileDragDepth=Math.max(0,fileDragDepth-1);
  if(!fileDragDepth||e.clientX<=0||e.clientY<=0||e.clientX>=innerWidth||e.clientY>=innerHeight)clearFileDrag();
});
document.addEventListener('drop',function(e){
  if(!hasDraggedFiles(e)&&!(e.dataTransfer&&e.dataTransfer.files.length))return;
  e.preventDefault();clearFileDrag();addFiles(Array.from(e.dataTransfer.files));
});
window.addEventListener('dragend',clearFileDrag);window.addEventListener('blur',clearFileDrag);

/* ── Composer textarea: auto-grow to 180px, then scroll (V9) ── */
function autosizeInput(){
  inputEl.style.height='auto';
  var h=Math.min(inputEl.scrollHeight,180);
  inputEl.style.height=h+'px';
  inputEl.style.overflowY=inputEl.scrollHeight>180?'auto':'hidden';
}
inputEl.addEventListener('input',autosizeInput);



/* ── Animated counter ── */
var _ctimers={};
function fmtInt(v){return Math.round(v).toString();}
function fmtCO2(v){
  if(v>=1)return v.toFixed(2)+' g';
  if(v>=0.001)return (v*1000).toFixed(v>=0.01?1:2)+' mg';
  return v>0?(v*1e6).toFixed(0)+' µg':'0 g';
}
function fmtWh(v){return v>=0.01?v.toFixed(3)+' Wh':v>0?(v*1000).toFixed(3)+' mWh':'0 Wh';}

/* ── Carbon-prevented baselines (V5) ──
   Provenance per entry. Only Google publishes a measured per-prompt CO2e
   figure; everything else converts a published Wh/query at a stated grid
   intensity and is labeled estimated. Grid default (400 g/kWh) matches the
   backend footprint module. */
var BASELINES = {
  /* OpenAI CEO, Jun 2025: "about 0.34 Wh" per average ChatGPT query, no
     methodology. CO2 = 0.34 Wh x 400 g/kWh = 136 mg. Estimated. */
  chatgpt: {label: 'ChatGPT', co2_mg: 136, estimated: true,
    source: 'OpenAI CEO Jun 2025: 0.34 Wh/query (no methodology); CO2 at 400 g/kWh'},
  /* No provider disclosure for Claude. Epoch AI's 0.3 Wh GPT-4-class
     estimate applied to Claude-class (same model class); CO2 = 0.3 Wh x
     400 g/kWh = 120 mg. Estimated. */
  claude: {label: 'Claude', co2_mg: 120, estimated: true,
    source: 'No provider disclosure; Epoch AI 0.3 Wh GPT-4-class estimate applied to Claude-class; CO2 at 400 g/kWh'},
  /* Google, Aug 2025 ("Measuring the Environmental Impact of AI Inference"):
     0.03 g CO2e per median Gemini text prompt, measured with published
     methodology (market-based accounting). Not an estimate. */
  gemini: {label: 'Gemini', co2_mg: 30, estimated: false,
    source: 'Google Aug 2025: 0.03 g CO2e per median text prompt, measured (market-based)'}
};
var BASELINE_KEY = 'arboris-baseline-v1';
function getBaselineId(){
  try{var v = localStorage.getItem(BASELINE_KEY); if(v && BASELINES[v]) return v;}catch(e){}
  return 'chatgpt';
}
function setBaselineId(id){
  if(!BASELINES[id])return;
  try{localStorage.setItem(BASELINE_KEY, id);}catch(e){}
  refreshReceipts();
}
function refreshReceipts(){
  liveTurns.forEach(function(t){
    if(!t.el)return;
    var old = t.el.querySelector('.saved-line');
    if(old)old.remove();
    var rl=liveMetaRow(t);if(rl)t.el.appendChild(rl);
  });
}

/* ── CO₂ equivalence ── */
function co2eq(g){
  /* Seconds of a 9 W LED bulb at the same assumed 400 g CO2e/kWh. */
  var led=g/(9/3600/1000*GRID_G_KWH);
  if(led<0.1)return'';
  return'≈'+(led<10?led.toFixed(1):Math.round(led))+' s of a 9 W LED';
}



/* ── Smart scroll: only auto-scroll when user is already near the bottom ── */
function nearBottom(){return chatEl.scrollHeight-chatEl.scrollTop-chatEl.clientHeight<90;}
function scrollBottom(){if(nearBottom())chatEl.scrollTop=chatEl.scrollHeight;}

/* ── Screen-reader announcement: used only for new or replaced bot answers ── */
function announce(text){
  liveEl.textContent='';
  setTimeout(function(){liveEl.textContent=text;},60);
}
function modeName(r){
  var lbl={sprout:'Sprout',canopy:'Canopy',forest:'Forest'};
  return r.cacheHit?'cache hit':(lbl[r.mode]||r.mode);
}

/* ── Thinking indicator ── */
function addTypingIndicator(parent){
  var row=document.createElement('div');row.className='mr bot';
  var b=document.createElement('div');b.className='thinking';b.setAttribute('aria-hidden','true');
  var w=document.createElement('span');w.textContent='Thinking';b.appendChild(w);
  var d=document.createElement('span');d.className='th-dots';d.setAttribute('aria-hidden','true');
  for(var i=0;i<3;i++){var dot=document.createElement('i');dot.textContent='.';d.appendChild(dot);}
  b.appendChild(d);
  row.appendChild(b);parent.appendChild(row);scrollBottom();
  return row;
}

/* ── Typewriter (stops if the chat was cleared or rebuilt meanwhile) ── */

/* ── Cache flash ── */
var cfEl=document.getElementById('cache-flash');
function showCacheFlash(){
  cfEl.classList.add('show');
  setTimeout(function(){cfEl.classList.remove('show');},1400);
}

/* ── Toast ── */
var toastEl=document.getElementById('toast');
var _toastTimer;
function showToast(msg){
  toastEl.textContent=msg;toastEl.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer=setTimeout(function(){toastEl.classList.remove('show');},2200);
}

/* ── Clipboard with fallback ── */
function copyText(txt,okMsg){
  function fallback(){
    var ok=false,ta=document.createElement('textarea');
    ta.value=txt;ta.setAttribute('readonly','');ta.style.position='fixed';ta.style.top='0';ta.style.opacity='0';
    document.body.appendChild(ta);ta.select();
    try{ok=document.execCommand('copy');}catch(e){ok=false;}
    ta.remove();
    showToast(ok?okMsg:'Copy failed: clipboard unavailable here. Select the text and copy it manually.');
  }
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(txt).then(function(){showToast(okMsg);},fallback);
  } else fallback();
}

/* ── Diff row ── */
function makeDiffRow(diff,shrunk,raw){
  if(!diff||raw===shrunk)return null;
  var el=document.createElement('div');el.className='diff-row';
  var hasChange=diff.tokens.some(function(t){return t.t==='r';});
  if(!hasChange&&!diff.added.length)return null;
  diff.tokens.forEach(function(tok){
    var s=document.createElement('span');
    s.className=tok.t==='r'?'dr':'dk';
    s.textContent=tok.w+' ';
    el.appendChild(s);
  });
  if(diff.added.length){
    var arr=document.createElement('span');arr.className='diff-arrow';arr.textContent='→';el.appendChild(arr);
    diff.added.forEach(function(w){
      var s=document.createElement('span');s.className='da';s.textContent=' '+w;el.appendChild(s);
    });
  }
  return el;
}

/* ── Tags ── */
function short(s){s=s.replace(/\s+/g,' ').trim();return s.length>48?s.slice(0,48)+'…':s;}
/* ── Welcome ── */
function addWelcome(){
  /* Welcome is handled by the hero landing state — no bubble needed */
}

/* Copy-stats and export nav icons removed in V5. Per-message Copy stays. */




inputEl.addEventListener('keydown',function(e){
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();doSend();}
});
document.getElementById('sb').addEventListener('click',doSend);
function doSend(){
  if((!inputEl.value.trim()&&!pendingAttachments.length)||liveTurns.some(function(t){return t.pending;}))return;
  if(attachmentReads||pendingAttachments.some(function(f){return f.loading;})){showToast('Wait for the files to finish attaching.');return;}
  var v=inputEl.value;inputEl.value='';
  var files=pendingAttachments.slice();pendingAttachments=[];renderAttachments();
  autosizeInput();
  sendLive(v.trim()||'What can you tell me about the attached files?',null,null,files);
}
/* Live only: every question goes to the backend. */
function ask(raw){sendLive(raw);}

/* ── Clear (also wipes the saved session) ── */
if(document.getElementById('cb'))document.getElementById('cb').addEventListener('click',function(){
  epoch++;
  chatEl.innerHTML='';
  clearLiveState();
  var heroEl=document.querySelector('.hero');if(heroEl)heroEl.classList.remove('chatting');
  resetLive();
  addWelcome();
  showToast('Chat cleared, saved session deleted.');
});

/* Export nav icon removed in V5. */

/* How-it-works dialog removed in V5; its content lives on features.html. */

/* ── Sidebar: drawer on narrow screens, collapsible on desktop (ChatGPT-style) ── */
var sideEl=document.getElementById('sidebar'),sideBtn=document.getElementById('side-toggle'),
    sideOpen=document.getElementById('side-open'),scrimEl=document.getElementById('scrim');
var SIDE_COLLAPSE_KEY='arboris-side-collapsed';
function isNarrow(){return window.matchMedia('(max-width:820px)').matches;}
function sideCollapsed(){try{return localStorage.getItem(SIDE_COLLAPSE_KEY)==='1';}catch(e){return false;}}
function applySideCollapsed(){
  var c=sideCollapsed();
  document.body.classList.toggle('side-collapsed',c);
  if(sideBtn)sideBtn.setAttribute('aria-expanded',c?'false':'true');
}
function toggleSide(){
  if(isNarrow()){setSide(!sideEl.classList.contains('open'));}
  else{
    var c=!document.body.classList.contains('side-collapsed');
    try{localStorage.setItem(SIDE_COLLAPSE_KEY,c?'1':'0');}catch(e){}
    applySideCollapsed();
  }
}
if(sideEl&&sideBtn){
function setSide(open){sideEl.classList.toggle('open',open);sideBtn.setAttribute('aria-expanded',open?'true':'false');}
sideBtn.addEventListener('click',toggleSide);
if(sideOpen)sideOpen.addEventListener('click',toggleSide);
if(scrimEl)scrimEl.addEventListener('click',function(){setSide(false);});}
applySideCollapsed();
/* ── Account: usage ring + popover (V8) ──
   Usage = messages sent in the rolling hour vs the backend's hourly rate
   limit (from /api/health; falls back to 30). Timestamps in localStorage. */
var USAGE_KEY='arboris-usage-v1';
var usageLimit=30;
function getUsage(){
  try{
    var u=JSON.parse(localStorage.getItem(USAGE_KEY)||'[]'),now=Date.now();
    if(!Array.isArray(u))return[];
    return u.filter(function(t){return typeof t==='number'&&now-t<3600000;});
  }catch(e){return[];}
}
function recordUsage(){
  var u=getUsage();u.push(Date.now());
  try{localStorage.setItem(USAGE_KEY,JSON.stringify(u));}catch(e){}
  refreshRing();
}
function refreshRing(){
  var used=getUsage().length;
  var frac=usageLimit>0?Math.max(0,Math.min(1,1-used/usageLimit)):1;
  var ring=document.getElementById('ring-fg');
  if(ring){var C=2*Math.PI*17;ring.style.strokeDasharray=String(C);ring.style.strokeDashoffset=String(C*(1-frac));}
  var btn=document.getElementById('acct-btn');
  if(btn)btn.title=used+' of '+usageLimit+' messages used in the last hour';
}
try{
  fetch(getLiveUrl().replace(/\/api\/chat$/,'/api/health'),{cache:'no-store'})
    .then(function(r){return r.json();})
    .then(function(j){
      var L=j&&isFinite(+j.rate_limit_per_hour)?+j.rate_limit_per_hour:0;
      if(L>0){usageLimit=L;refreshRing();}
    }).catch(function(){});
}catch(e){}
refreshRing();
var acctBtn=document.getElementById('acct-btn'),acctPop=document.getElementById('acct-pop');
if(acctBtn&&acctPop){
  acctBtn.addEventListener('click',function(e){
    e.stopPropagation();
    var willOpen=acctPop.hidden;
    acctPop.hidden=!willOpen;
    acctBtn.setAttribute('aria-expanded',willOpen?'true':'false');
  });
  document.addEventListener('click',function(e){
    if(!acctPop.hidden&&!acctPop.contains(e.target)&&e.target!==acctBtn){
      acctPop.hidden=true;acctBtn.setAttribute('aria-expanded','false');
    }
  });
}

/* ═══ Live mode ═══
   Every question goes to the backend URL below as the raw text: the backend
   runs PromptShrink, cache, routing, the cascade and the brevity trim, so
   nothing is shrunk twice. No API key ever lives in this page. The backend
   URL and live conversation history are saved to localStorage so the session
   survives a page reload. */
var LIVE_URL_KEY='arboris-live-backend-url';
var LIVE_STATE_KEY='arboris-live-v1';
/* On a Cloud Run host (*.run.app) the backend serves this page, so the
   live URL defaults to the same origin. Everywhere else (including the
   GitHub Pages site, which has no backend) it defaults to localhost,
   where a locally-run server is expected. A saved URL always wins. */
/* Backend is integrated on the same server (tailnet dev / Cloud Run):
   always same-origin /api/chat. No configurable URL. */
var LIVE_DEFAULT_URL=window.location.origin+'/api/chat';
var liveTurns=[],liveTotals=zeroLive(),liveCtrls=[];
var liveSession=newLiveSession();
function getLiveUrl(){return LIVE_DEFAULT_URL;}
function zeroLive(){return{calls:0,inTok:0,outTok:0,unreported:0,hits:0,esc:0,exp:0,measured:0,saved:0};}
/* Sidebar footer controls removed (V6): backend is same-origin, baseline
   picker UI gone (default ChatGPT baseline still applies to receipts). */
function newLiveSession(){
  var a=new Uint8Array(12),s='web-';
  if(window.crypto&&crypto.getRandomValues)crypto.getRandomValues(a);
  else for(var i=0;i<a.length;i++)a[i]=Math.floor(Math.random()*256);
  for(var j=0;j<a.length;j++)s+=(a[j]<16?'0':'')+a[j].toString(16);
  return s;
}
/* Backend URL + baseline picker UI removed (V6). */
function resetLive(){
  liveCtrls.forEach(function(c){try{c.abort();}catch(e){}});
  liveCtrls=[];liveTurns=[];liveTotals=zeroLive();liveSession=newLiveSession();
  clearLiveState();
  renderLiveTotals();
}
function saveLiveState(){
  upsertCurrentChat();
  if(!activeChatId)return;
  try{
    localStorage.setItem(LIVE_STATE_KEY,JSON.stringify({v:1,savedAt:new Date().toISOString(),
      turns:serializeLiveTurns(),draft:inputEl.value,draftAttachments:attachmentRefs(pendingAttachments),
      totals:liveTotals,session:liveSession,activeChatId:activeChatId}));
  }catch(e){}
}
function loadLiveState(){
  var s;
  try{s=JSON.parse(localStorage.getItem(LIVE_STATE_KEY)||'null');}catch(e){return null;}
  if(!s||s.v!==1||!Array.isArray(s.turns)||(!s.turns.length&&!s.activeChatId)||!s.totals)return null;
  var ok=s.turns.every(function(t){return t&&typeof t.raw==='string'&&typeof t.answer==='string';});
  return ok?s:null;
}
function clearLiveState(){try{localStorage.removeItem(LIVE_STATE_KEY);}catch(e){}}
function renderLiveTotals(){
  var T=liveTotals;
  function set(id,v){var el=document.getElementById(id);if(el)el.textContent=v;}
  set('lt-calls',T.calls);set('lt-in',T.inTok);set('lt-out',T.outTok);
  set('lt-hits',T.hits);set('lt-esc',T.esc);
  set('lt-unrep',T.unreported?('+'+T.unreported+' not reported'):'');
  set('lt-saved',T.measured?T.saved:'—');
  set('lt-saved-lbl',T.measured?('saved vs baseline (measured, '+T.measured+' msg'+(T.measured!==1?'s':'')+')'):'saved vs baseline (measured)');
}
function isNum(v){return typeof v==='number'&&isFinite(v);}
/* Receipt (V8): only the CO2-prevented brand line. Everything else stripped. */
function liveMetaRow(t){
  var m=t.meta||{};
  var bl=BASELINES[getBaselineId()];
  if(!(bl&&m.energy&&m.energy.status==='estimate'&&isNum(m.energy.co2e_g)))return null;
  var prevG=bl.co2_mg/1000-m.energy.co2e_g;
  if(!(prevG>0))return null;
  var line=document.createElement('div');line.className='saved-line';
  line.textContent=fmtCO2(prevG)+' CO\u2082 prevented vs '+bl.label+(bl.estimated?' (est.)':'');
  line.title='This message vs a typical '+bl.label+' query. Baseline: '+bl.source;
  return line;
}
/* Minimal SSE block parser: "event: x" + "data: <json>" lines. */
function parseSSEBlock(block){
  var ev='message',data=[];
  block.split(/\r?\n/).forEach(function(line){
    if(!line||line.charAt(0)===':')return;
    var i=line.indexOf(':'),f=i<0?line:line.slice(0,i),v=i<0?'':line.slice(i+1);
    if(v.charAt(0)===' ')v=v.slice(1);
    if(f==='event')ev=v;else if(f==='data')data.push(v);
  });
  if(!data.length)return null;
  try{return{event:ev,data:JSON.parse(data.join('\n'))};}catch(e){return null;}
}
/* POST to the backend; on = {chunk(text), meta(obj), error(msg), done()}. */
function liveRequest(url,body,on){
  var ctrl=window.AbortController?new AbortController():null;
  if(ctrl)liveCtrls.push(ctrl);
  var settled=false,gotResponse=false;
  function finish(){settled=true;if(ctrl)liveCtrls=liveCtrls.filter(function(c){return c!==ctrl;});}
  function fail(msg){if(settled)return;finish();on.error(msg);}
  function handle(block){
    if(settled)return;
    var e=parseSSEBlock(block);if(!e)return;
    if(e.event==='chunk'&&e.data&&typeof e.data.text==='string')on.chunk(e.data.text);
    else if(e.event==='meta')on.meta(e.data||{});
    else if(e.event==='error')fail(e.data&&typeof e.data.error==='string'?e.data.error:'The backend reported an error.');
    else if(e.event==='done'){finish();on.done();}
  }
  fetch(url,{method:'POST',headers:{'Content-Type':'application/json','Accept':'text/event-stream, application/json'},
    body:JSON.stringify(body),credentials:'omit',cache:'no-store',signal:ctrl?ctrl.signal:undefined})
  .then(function(res){
    gotResponse=true;
    var ct=res.headers.get('Content-Type')||'';
    if(!res.ok){
      return res.text().then(function(txt){
        var msg=null;try{var j=JSON.parse(txt);if(j&&typeof j.error==='string')msg=j.error;}catch(e){}
        fail(msg||('The backend returned an error (HTTP '+res.status+').'));
      });
    }
    if(ct.indexOf('text/event-stream')<0){
      /* Non-streaming JSON fallback: {answer, meta}. */
      return res.json().then(function(j){
        if(!j||typeof j.answer!=='string')throw new Error('bad shape');
        on.chunk(j.answer);on.meta(j.meta||{});finish();on.done();
      });
    }
    var reader=res.body.getReader(),dec=new TextDecoder(),buf='';
    function pump(){
      return reader.read().then(function(r){
        if(r.done){
          buf+=dec.decode();if(buf.trim())handle(buf);
          fail('The answer stream ended early. Try again.');
          return;
        }
        buf+=dec.decode(r.value,{stream:true});
        var parts=buf.split(/\r?\n\r?\n/);buf=parts.pop();
        parts.forEach(handle);
        if(!settled)return pump();
      });
    }
    return pump();
  })
  .catch(function(e){
    if(e&&e.name==='AbortError'){finish();return;}
    fail(gotResponse?'The backend sent a reply this page could not read. Try again.'
      :'Could not reach the backend at '+url+'. Is it running, and does it allow this page\'s origin?');
  });
}
function conversationHistory(turns){
  var history=[],chars=0;
  for(var i=turns.length-1;i>=0;i--){
    var t=turns[i];if(t.pending||t.error||!t.raw||!t.answer)continue;
    var size=t.raw.length+t.answer.length;
    if(history.length>=20||chars+size>24000)break;
    history.unshift({role:'user',content:t.raw},{role:'assistant',content:t.answer});chars+=size;
  }
  return history;
}
function sendLive(raw,display,expandOf,files){
  if(!raw.trim())return;
  var url=getLiveUrl();
  var t={live:true,raw:raw,seq:++seqCounter,answer:'',meta:null,error:null,pending:true,attachments:attachmentRefs(files)};
  liveTurns.push(t);
  saveLiveState();
  recordUsage();
  var wrap=document.createElement('div');wrap.className='turn';t.el=wrap;
  var urow=document.createElement('div');urow.className='mr user';
  var ub=document.createElement('div');ub.className='msg';ub.textContent=display||raw;
  appendMessageFiles(ub,files);
  urow.appendChild(ub);wrap.appendChild(urow);chatEl.appendChild(wrap);
  chatEl.scrollTop=chatEl.scrollHeight;
  var ind=addTypingIndicator(wrap),bubble=null;
  function ensureBubble(cls){
    if(ind){ind.remove();ind=null;}
    if(!bubble){
      var row=document.createElement('div');row.className='mr bot';
      bubble=document.createElement('div');bubble.className='msg'+(cls?' '+cls:'');
      row.appendChild(bubble);wrap.appendChild(row);
    }
    return bubble;
  }
  if(!/^https?:\/\//i.test(url)){
    t.error='The backend URL must start with http:// or https://.';t.pending=false;
    ensureBubble('err').textContent=t.error;saveLiveState();return;
  }
  var body={prompt:raw,session_id:liveSession,mode:expandOf?'full':'auto',stream:true,measure_baseline:false};
  body.history=conversationHistory(liveTurns);
  if(files&&files.length)body.attachments=files.map(function(f){var item={name:f.name,type:f.type};if(f.type==='text/plain')item.text=f.text;else item.data=f.data;return item;});
  if(expandOf)body.expand_of=expandOf;
  liveRequest(url,body,{
    chunk:function(text){
      if(liveTurns.indexOf(t)<0)return;
      t.answer+=text;ensureBubble('typing').textContent=t.answer;scrollBottom();
    },
    meta:function(m){t.meta=m;},
    error:function(msg){
      if(liveTurns.indexOf(t)<0)return;
      t.error=msg;var b=ensureBubble('err');b.classList.remove('typing');b.classList.add('err');
      t.pending=false;saveLiveState();
      b.textContent=(t.answer?t.answer+'\n\n':'')+msg;
      scrollBottom();announce('Live backend error: '+msg);
    },
    done:function(){
      if(liveTurns.indexOf(t)<0)return;
      t.pending=false;
      var b=ensureBubble();b.classList.remove('typing');
      var m=t.meta||{};t.meta=m;
      var rl2=liveMetaRow(t);if(rl2)wrap.appendChild(rl2);scrollBottom();
      if(m.cache_hit)showCacheFlash();
      var T=liveTotals;T.calls++;
      if(m.cache_hit)T.hits++;
      if(m.escalated)T.esc++;
      if(m.expansion)T.exp++;
      if(isNum(m.input_tokens)&&isNum(m.output_tokens)){T.inTok+=m.input_tokens;T.outTok+=m.output_tokens;}
      else T.unreported++;
      if(m.baseline&&isNum(m.baseline.saved_total_tokens)){T.measured++;T.saved+=m.baseline.saved_total_tokens;}
      renderLiveTotals();
      saveLiveState();
      announce('Live answer: '+t.answer);
    }
  });
}

/* ── Multi-chat sidebar (V5) ── */
var CHATS_KEY='arboris-chats-v1';
var activeChatId=null;
var chatRail=document.getElementById('chat-rail'),chatHighlight=document.getElementById('chat-highlight');
var chatDrag=null,ignoreChatClickUntil=0;
function positionChatHighlight(){
  if(!chatRail||!chatHighlight)return;
  var selected=chatRail.querySelector('.chat-item.active');
  if(chatDrag&&chatDrag.started&&selected===chatDrag.row){chatHighlight.hidden=true;return;}
  if(!selected){chatHighlight.style.opacity='0';return;}
  var first=chatHighlight.hidden;
  if(first)chatHighlight.classList.add('positioning');
  chatHighlight.hidden=false;
  var top=selected.getBoundingClientRect().top-chatRail.getBoundingClientRect().top+chatRail.scrollTop;
  chatHighlight.style.height=selected.offsetHeight+'px';
  chatHighlight.style.transform='translateY('+top+'px)';
  chatHighlight.style.opacity='1';
  if(first){chatHighlight.getBoundingClientRect();chatHighlight.classList.remove('positioning');}
}
if(window.ResizeObserver&&chatRail)new ResizeObserver(positionChatHighlight).observe(chatRail);
window.addEventListener('resize',positionChatHighlight);

/* Rows move into their new slots while the dragged chat follows the pointer. */
function previewChatOrder(){
  var d=chatDrag;if(!d||!d.started)return;
  d.order.forEach(function(row,i){row.style.transform='translateY('+(d.slots[i]-row.offsetTop)+'px)';});
  var selected=d.order.find(function(row){return row.classList.contains('active');});
  if(selected===d.row){chatHighlight.hidden=true;}
  else if(selected){
    chatHighlight.style.transform='translateY('+(d.slots[d.order.indexOf(selected)]+d.list.offsetTop)+'px)';
  }
}
function updateChatDrag(){
  var d=chatDrag;if(!d||!d.started)return;
  var railRect=chatRail.getBoundingClientRect();
  d.valid=d.x>=railRect.left-24&&d.x<=railRect.right+24&&d.y>=railRect.top-24&&d.y<=railRect.bottom+24;
  d.ghost.style.transform='translate('+Math.round(d.x-d.grabX)+'px,'+Math.round(d.y-d.grabY)+'px)';
  if(!d.valid)return;
  var center=d.y-d.grabY+d.rect.height/2-railRect.top+chatRail.scrollTop-d.list.offsetTop;
  var index=0;
  for(var i=0;i<d.slots.length-1;i++)if(center>(d.slots[i]+d.slots[i+1])/2+d.rect.height/2)index=i+1;
  var old=d.order.indexOf(d.row);
  if(old!==index){d.order.splice(old,1);d.order.splice(index,0,d.row);previewChatOrder();}
}
function scrollChatDrag(){
  var d=chatDrag;if(!d||!d.started)return;
  var rect=chatRail.getBoundingClientRect(),delta=0;
  if(d.valid){if(d.y<rect.top+32)delta=-7;else if(d.y>rect.bottom-32)delta=7;}
  if(delta){chatRail.scrollTop+=delta;updateChatDrag();}
  d.frame=requestAnimationFrame(scrollChatDrag);
}
function finishChatDrag(commit){
  var d=chatDrag;if(!d)return;chatDrag=null;
  if(!d.started)return;
  cancelAnimationFrame(d.frame);ignoreChatClickUntil=Date.now()+350;
  if(commit&&d.valid){
    var saved=getChats(),ordered=[];
    d.order.forEach(function(row){var rec=saved.find(function(c){return c.id===row.dataset.chatId;});if(rec)ordered.push(rec);});
    saved.forEach(function(c){if(!ordered.some(function(rec){return rec.id===c.id;}))ordered.push(c);});
    saveChats(ordered);
    var statusEl=document.getElementById('chat-order-status');
    if(statusEl)statusEl.textContent='Chat moved to position '+(d.order.indexOf(d.row)+1)+' of '+ordered.length+'.';
  }
  document.body.classList.remove('chat-sorting');
  d.order.forEach(function(row){row.style.transform='';row.classList.remove('drag-source');});
  renderChatList();
  var target=Array.from(d.list.querySelectorAll('.chat-item')).find(function(row){return row.dataset.chatId===d.row.dataset.chatId;});
  if(target){
    target.classList.add('drag-source');
    target.focus({preventScroll:true});
    var rect=target.getBoundingClientRect();d.ghost.classList.add('settling');
    d.ghost.style.transform='translate('+rect.left+'px,'+rect.top+'px)';
  }
  setTimeout(function(){d.ghost.remove();if(target)target.classList.remove('drag-source');},reduceMotion?0:260);
}
var chatListEl=document.getElementById('chat-list');
if(chatListEl){
  chatListEl.addEventListener('pointerdown',function(e){
    if(e.button!==0||!e.isPrimary)return;
    var row=e.target.closest('.chat-item');if(!row)return;
    closeChatMenu(false);
    if(chatDrag)finishChatDrag(false);
    var rect=row.getBoundingClientRect();
    chatDrag={row:row,list:chatListEl,pointerId:e.pointerId,startX:e.clientX,startY:e.clientY,x:e.clientX,y:e.clientY,grabX:e.clientX-rect.left,grabY:e.clientY-rect.top,rect:rect,started:false};
  });
  chatListEl.addEventListener('dragstart',function(e){e.preventDefault();});
  chatListEl.addEventListener('keydown',function(e){
    var row=e.target.closest('.chat-item');
    if(!row||!e.altKey||['ArrowUp','ArrowDown'].indexOf(e.key)<0)return;
    e.preventDefault();
    var chats=getChats(),from=chats.findIndex(function(c){return c.id===row.dataset.chatId;});
    var to=from+(e.key==='ArrowUp'?-1:1);
    if(from<0||to<0||to>=chats.length)return;
    chats.splice(to,0,chats.splice(from,1)[0]);saveChats(chats);renderChatList();
    var moved=Array.from(chatListEl.children).find(function(b){return b.dataset.chatId===row.dataset.chatId;});
    if(moved)moved.focus({preventScroll:true});
    document.getElementById('chat-order-status').textContent='Chat moved to position '+(to+1)+' of '+chats.length+'.';
  });
}
document.addEventListener('pointermove',function(e){
  var d=chatDrag;if(!d||e.pointerId!==d.pointerId)return;
  d.x=e.clientX;d.y=e.clientY;
  if(!d.started){
    if(Math.hypot(d.x-d.startX,d.y-d.startY)<6)return;
    d.started=true;d.order=Array.from(d.list.querySelectorAll('.chat-item'));
    d.slots=d.order.map(function(row){return row.offsetTop;});
    d.ghost=d.row.cloneNode(true);d.ghost.removeAttribute('aria-current');d.ghost.setAttribute('aria-hidden','true');d.ghost.tabIndex=-1;
    d.ghost.classList.add('chat-drag-ghost');d.ghost.style.cssText='left:0;top:0;width:'+d.rect.width+'px;height:'+d.rect.height+'px;transform:translate('+Math.round(d.x-d.grabX)+'px,'+Math.round(d.y-d.grabY)+'px)';
    document.body.appendChild(d.ghost);d.row.classList.add('drag-source');document.body.classList.add('chat-sorting');
    previewChatOrder();
    d.frame=requestAnimationFrame(scrollChatDrag);
  }
  e.preventDefault();updateChatDrag();
},{passive:false});
document.addEventListener('pointerup',function(e){if(chatDrag&&e.pointerId===chatDrag.pointerId)finishChatDrag(true);});
document.addEventListener('pointercancel',function(){finishChatDrag(false);});
document.addEventListener('keydown',function(e){if(e.key==='Escape'&&chatDrag){e.preventDefault();finishChatDrag(false);}});
window.addEventListener('blur',function(){finishChatDrag(false);});
function getChats(){try{var c=JSON.parse(localStorage.getItem(CHATS_KEY)||'[]');return Array.isArray(c)?c:[];}catch(e){return[];}}
function saveChats(c){try{localStorage.setItem(CHATS_KEY,JSON.stringify(c));}catch(e){}}
function chatTitle(turns){var f=turns&&turns.length?turns[0].raw:'';return short(f)||'New chat';}
function serializeLiveTurns(){
  return liveTurns.map(function(t){return{raw:t.raw,answer:t.answer||'',meta:t.meta||{},error:t.error||null,pending:!!t.pending,attachments:attachmentRefs(t.attachments)};});
}
function clearComposer(){
  inputEl.value='';
  pendingAttachments=[];renderAttachments();
  autosizeInput();
}
function leaveCurrentChat(){
  liveTurns.forEach(function(t){
    if(t.pending){t.pending=false;t.error='Reply interrupted. Send your message again to continue.';}
  });
  liveCtrls.forEach(function(c){try{c.abort();}catch(e){}});liveCtrls=[];
  saveLiveState();
}
function upsertCurrentChat(){
  if(!activeChatId&&!liveTurns.length&&!inputEl.value.trim()&&!pendingAttachments.length)return;
  var chats=getChats(),now=new Date().toISOString();
  if(!activeChatId)activeChatId=newLiveSession().replace('web-','c-');
  var rec={id:activeChatId,title:chatTitle(liveTurns),savedAt:now,
    turns:serializeLiveTurns(),draft:inputEl.value,draftAttachments:attachmentRefs(pendingAttachments),
    totals:liveTotals,session:liveSession};
  var i=-1;for(var k=0;k<chats.length;k++)if(chats[k].id===activeChatId)i=k;
  if(i>=0&&chats[i].customTitle){rec.customTitle=chats[i].customTitle;rec.title=rec.customTitle;}
  if(i>=0)chats[i]=rec;else chats.unshift(rec);
  saveChats(chats.slice(0,50));
  renderChatList();
}
function renderTurns(turnArray){
  chatEl.innerHTML='';
  turnArray.forEach(function(st){
    var t={live:true,raw:st.raw,seq:++seqCounter,answer:st.answer,meta:st.meta||{},pending:false,
      error:st.pending?'Reply interrupted. Send your message again to continue.':st.error||null,attachments:st.attachments||[]};
    liveTurns.push(t);
    var wrap=document.createElement('div');wrap.className='turn';t.el=wrap;
    var urow=document.createElement('div');urow.className='mr user';
    var ub=document.createElement('div');ub.className='msg';ub.textContent=st.raw;
    appendMessageFiles(ub,t.attachments);
    urow.appendChild(ub);wrap.appendChild(urow);
    if(t.answer||t.error){
      var brow=document.createElement('div');brow.className='mr bot';
      var bb=document.createElement('div');bb.className='msg'+(t.error?' err':'');
      bb.textContent=t.answer+(t.error?(t.answer?'\n\n':'')+t.error:'');
      brow.appendChild(bb);wrap.appendChild(brow);
    }
    var rl3=liveMetaRow(t);if(rl3)wrap.appendChild(rl3);
    chatEl.appendChild(wrap);
  });
  if(liveTurns.length)chatEl.scrollTop=chatEl.scrollHeight;
}
function renderChatList(){
  if(chatDrag){finishChatDrag(false);return;}
  closeChatMenu(false);
  var list=document.getElementById('chat-list');if(!list)return;
  var chats=getChats();
  list.innerHTML='';
  if(!chats.length){var e=document.createElement('div');e.className='chat-list-empty';e.textContent='No past chats yet.';list.appendChild(e);positionChatHighlight();return;}
  chats.forEach(function(c){
    var b=document.createElement('button');b.type='button';
    b.className='chat-item'+(c.id===activeChatId?' active':'');
    b.dataset.chatId=c.id;
    if(c.id===activeChatId)b.setAttribute('aria-current','page');
    var d=new Date(c.savedAt),ds=isNaN(d.getTime())?'':d.toLocaleDateString(undefined,{month:'short',day:'numeric'});
    var ic=document.createElementNS('http://www.w3.org/2000/svg','svg');
    ic.setAttribute('viewBox','0 0 24 24');ic.setAttribute('fill','none');
    ic.setAttribute('stroke','currentColor');ic.setAttribute('stroke-width','2');
    ic.setAttribute('stroke-linecap','round');ic.setAttribute('stroke-linejoin','round');
    ic.setAttribute('aria-hidden','true');
    ic.innerHTML='<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>';
    b.appendChild(ic);
    var t=document.createElement('span');t.className='ct';t.textContent=c.title;b.appendChild(t);
    if(ds){var s=document.createElement('span');s.className='cd';s.textContent=ds;b.appendChild(s);}
    b.setAttribute('aria-label','Open chat: '+c.title);
    b.addEventListener('click',function(){if(Date.now()>=ignoreChatClickUntil)loadChat(c.id);});
    list.appendChild(b);
    var options=document.createElement('button');options.type='button';options.className='chat-options';
    options.dataset.chatOptionsId=c.id;options.setAttribute('aria-label','Options for chat: '+c.title);
    options.setAttribute('aria-haspopup','menu');options.setAttribute('aria-expanded','false');
    options.innerHTML='<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><circle cx="4" cy="10" r="1.4"/><circle cx="10" cy="10" r="1.4"/><circle cx="16" cy="10" r="1.4"/></svg>';
    list.appendChild(options);options.style.top=(b.offsetTop+6)+'px';
    options.addEventListener('click',function(){var r=options.getBoundingClientRect();openChatMenu(c.id,r.left,r.bottom+4);});
  });
  positionChatHighlight();
}
function resetSession(){
  liveCtrls.forEach(function(c){try{c.abort();}catch(e){}});
  liveCtrls=[];liveTurns=[];liveTotals=zeroLive();liveSession=newLiveSession();
  activeChatId=null;chatEl.innerHTML='';renderLiveTotals();clearLiveState();
  clearComposer();
}
function newChat(){
  var unused=getChats().find(function(c){
    return !(c.turns||[]).length&&!c.customTitle&&!(c.draft||'').trim()&&!(c.draftAttachments||[]).length
      &&(c.id!==activeChatId||(!liveTurns.length&&!inputEl.value.trim()&&!pendingAttachments.length));
  });
  if(unused){loadChat(unused.id);if(window.innerWidth<=820)setSide(false);inputEl.focus();return;}
  if(activeChatId&&!liveTurns.length&&!inputEl.value.trim()&&!pendingAttachments.length){
    if(window.innerWidth<=820)setSide(false);inputEl.focus();return;
  }
  leaveCurrentChat();
  resetSession();
  activeChatId=newLiveSession().replace('web-','c-');
  saveLiveState();
  if(window.innerWidth<=820)setSide(false);
  inputEl.focus();
}
function loadChat(id){
  if(id===activeChatId){if(window.innerWidth<=820)setSide(false);return;}
  leaveCurrentChat();
  var chats=getChats(),c=null;
  for(var i=0;i<chats.length;i++)if(chats[i].id===id)c=chats[i];
  if(!c)return;
  resetSession();
  activeChatId=c.id;liveSession=c.session||newLiveSession();liveTotals=c.totals||zeroLive();
  renderTurns(c.turns||[]);
  inputEl.value=typeof c.draft==='string'?c.draft:'';autosizeInput();
  restoreDraftAttachments(c.draftAttachments||[]);
  renderLiveTotals();saveLiveState();renderChatList();
  if(window.innerWidth<=820)setSide(false);
}
function renameChat(id,title){
  if(typeof title!=='string'||!title.trim())return false;
  var chats=getChats(),c=chats.find(function(chat){return chat.id===id;});if(!c)return false;
  c.customTitle=title.trim().slice(0,120);c.title=c.customTitle;saveChats(chats);renderChatList();return true;
}
function removeChatFiles(removed,remaining){
  function refs(chat){var files=(chat.draftAttachments||[]).slice();(chat.turns||[]).forEach(function(t){files=files.concat(t.attachments||[]);});return files;}
  var kept=new Set();remaining.forEach(function(c){refs(c).forEach(function(f){kept.add(f.id);});});
  var discarded=new Set();refs(removed).forEach(function(f){
    if(f.id&&!kept.has(f.id)&&!discarded.has(f.id)){discarded.add(f.id);fileStorage('delete',f.id).catch(function(){});}
  });
}
function deleteChat(id){
  var chats=getChats(),index=chats.findIndex(function(c){return c.id===id;});if(index<0)return false;
  var selected=id===activeChatId;
  if(selected)leaveCurrentChat();
  chats=getChats();var removed=chats.find(function(c){return c.id===id;});
  chats=chats.filter(function(c){return c.id!==id;});saveChats(chats);removeChatFiles(removed,chats);
  if(selected){
    resetSession();
    if(chats.length)loadChat(chats[Math.min(index,chats.length-1)].id);
    else renderChatList();
  }else renderChatList();
  return true;
}
var chatMenu=document.getElementById('chat-menu'),chatMenuId=null,chatDialogId=null;
var renameDialog=document.getElementById('chat-rename-dialog'),deleteDialog=document.getElementById('chat-delete-dialog');
function focusChatRow(id){
  var row=Array.from(chatListEl.querySelectorAll('.chat-item')).find(function(b){return b.dataset.chatId===id;});
  if(row)row.focus({preventScroll:true});else inputEl.focus();
}
function closeChatMenu(restoreFocus){
  if(!chatMenu)return;
  var id=chatMenuId;chatMenu.hidden=true;chatMenuId=null;
  chatListEl.querySelectorAll('.chat-options').forEach(function(b){b.setAttribute('aria-expanded','false');});
  if(restoreFocus&&id)focusChatRow(id);
}
function openChatMenu(id,x,y){
  if(chatDrag&&chatDrag.started)return;
  closeChatMenu(false);chatMenuId=id;chatMenu.hidden=false;
  var option=Array.from(chatListEl.querySelectorAll('.chat-options')).find(function(b){return b.dataset.chatOptionsId===id;});
  if(option)option.setAttribute('aria-expanded','true');
  var r=chatMenu.getBoundingClientRect();
  chatMenu.style.left=Math.max(8,Math.min(x,window.innerWidth-r.width-8))+'px';
  chatMenu.style.top=Math.max(8,Math.min(y,window.innerHeight-r.height-8))+'px';
  chatMenu.querySelector('[role="menuitem"]').focus({preventScroll:true});
}
chatListEl.addEventListener('contextmenu',function(e){
  var row=e.target.closest('.chat-item');if(!row)return;e.preventDefault();openChatMenu(row.dataset.chatId,e.clientX,e.clientY);
});
chatListEl.addEventListener('keydown',function(e){
  var row=e.target.closest('.chat-item');if(!row)return;
  if(e.key==='ContextMenu'||(e.shiftKey&&e.key==='F10')){
    e.preventDefault();var r=row.getBoundingClientRect();openChatMenu(row.dataset.chatId,r.left+18,r.bottom);
  }
});
chatMenu.addEventListener('keydown',function(e){
  if(e.key==='Escape'){e.preventDefault();closeChatMenu(true);return;}
  if(['ArrowDown','ArrowUp','Home','End'].indexOf(e.key)<0)return;e.preventDefault();
  var items=Array.from(chatMenu.querySelectorAll('[role="menuitem"]')),index=items.indexOf(document.activeElement);
  var next=e.key==='Home'?0:e.key==='End'?items.length-1:(index+(e.key==='ArrowDown'?1:-1)+items.length)%items.length;
  items[next].focus();
});
chatMenu.addEventListener('click',function(e){
  var command=e.target.closest('[data-chat-command]');if(!command)return;
  var c=getChats().find(function(chat){return chat.id===chatMenuId;});if(!c){closeChatMenu(false);return;}
  chatDialogId=c.id;closeChatMenu(false);
  if(command.dataset.chatCommand==='rename'){
    document.getElementById('chat-name').value=c.title;renameDialog.returnValue='';renameDialog.showModal();document.getElementById('chat-name').select();
  }else{
    document.getElementById('chat-delete-description').textContent='Delete “'+c.title+'” and its messages from this browser?';
    deleteDialog.returnValue='';deleteDialog.showModal();
  }
});
renameDialog.addEventListener('close',function(){
  var id=chatDialogId;
  if(renameDialog.returnValue==='confirm')renameChat(id,document.getElementById('chat-name').value);
  focusChatRow(id);
});
deleteDialog.addEventListener('close',function(){
  var id=chatDialogId;
  if(deleteDialog.returnValue==='confirm')deleteChat(id);
  focusChatRow(activeChatId);
});
document.addEventListener('pointerdown',function(e){if(!e.target.closest('#chat-menu,.chat-options'))closeChatMenu(false);});
if(chatRail)chatRail.addEventListener('scroll',function(){closeChatMenu(false);});
window.addEventListener('resize',function(){closeChatMenu(false);});
document.getElementById('new-chat-btn').addEventListener('click',newChat);
var draftSaveTimer;
inputEl.addEventListener('input',function(){
  clearTimeout(draftSaveTimer);draftSaveTimer=setTimeout(saveLiveState,250);
});
window.addEventListener('pagehide',saveLiveState);

/* ── Restore live turns ── */
var savedLive=loadLiveState();
if(savedLive){
  liveSession=savedLive.session||newLiveSession();
  liveTotals=savedLive.totals;
  activeChatId=savedLive.activeChatId||null;
  if(!activeChatId&&savedLive.turns.length){
    var storedChats=getChats(),firstTurn=savedLive.turns[0];
    function matchesFirstTurn(c){
      var first=c.turns&&c.turns[0];
      return first&&first.raw===firstTurn.raw&&first.answer===firstTurn.answer;
    }
    var sessionMatches=typeof savedLive.session==='string'&&savedLive.session
      ?storedChats.filter(function(c){return c.session===savedLive.session;}):[];
    // Existing duplicates can share a session; prefer the matching content.
    var restoredChat=sessionMatches.find(matchesFirstTurn)||sessionMatches[0]
      ||storedChats.find(matchesFirstTurn);
    if(restoredChat)activeChatId=restoredChat.id;
  }
  renderTurns(savedLive.turns);
  inputEl.value=typeof savedLive.draft==='string'?savedLive.draft:'';autosizeInput();
  restoreDraftAttachments(savedLive.draftAttachments||[]);
  renderLiveTotals();
  saveLiveState();
}
renderChatList();
});
}

// ── Hero chat mode switch ──
(function(){
  if(typeof document==='undefined')return;
  var hero = document.querySelector('.hero');
  if(!hero) return;
  // Switch to chat mode when first message is sent
  var origSend = window._origAsk;
  function activateChatMode(){
    if(!hero.classList.contains('chatting')){
      hero.classList.add('chatting');
    }
  }
  // Patch: switch to chat mode on any send
  var chatEl = document.getElementById('chat');
  if(chatEl){
    var obs = new MutationObserver(function(muts){
      muts.forEach(function(m){
        if(m.addedNodes.length) activateChatMode();
      });
    });
    obs.observe(chatEl, {childList: true});
  }
  // Also activate on clear to reset
  var cb = document.getElementById('cb');
  if(cb){
    cb.addEventListener('click', function(){
      // Small delay to let clear happen, then check if we should deactivate
      setTimeout(function(){
        if(chatEl && chatEl.children.length <= 1){
          hero.classList.remove('chatting');
        }
      }, 100);
    });
  }
})();
