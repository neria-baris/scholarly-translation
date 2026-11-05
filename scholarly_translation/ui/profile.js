/* Profile everywhere: a drawn reader button at the end of every page header and a sign-in window.
   Self-contained (works without ui.js). Calls only the existing routes. */
(function(){
'use strict';
var mount=document.getElementById('profile-mount');
if(!mount)return;
var token=((window.UI_CONFIG||{}).token)||'';
var doc=document.documentElement;
function isEn(){return doc.lang==='en'||doc.getAttribute('data-lang')==='en'}
function t(he,en){return isEn()?en:he}
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e}

var openai=null,google=null,openaiWaitUntil=0,googleWaitUntil=0,timer=null,dlg=null,button=null,badge=null,opener=null;

async function post(route,data){
  var response=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json','X-UI-Token':token},body:JSON.stringify(data||{})});
  var body=null;try{body=await response.json()}catch(_){}
  if(!response.ok){var error=Error((body&&body.error)||t('הפעולה לא הושלמה','The action did not complete'));error.status=response.status;throw error}
  return body||{};
}

/* The drawing: a reader with glasses and a book. Flat fills and a dark outline only. */
var DRAWING='<svg viewBox="0 0 40 40" aria-hidden="true" focusable="false">'
 +'<path d="M6 40c0-8 6-12 14-12s14 4 14 12z" fill="#e3893a" stroke="#2a1a10" stroke-width="1.6" stroke-linejoin="round"/>'
 +'<circle cx="20" cy="16" r="9" fill="#fffbea" stroke="#2a1a10" stroke-width="1.6"/>'
 +'<path d="M11.2 15.2C11 8.6 15.6 6 20 6s9 2.6 8.8 9.2c-2-1.8-4-3-8.8-3s-6.8 1.2-8.8 3z" fill="#e3893a" stroke="#2a1a10" stroke-width="1.5" stroke-linejoin="round"/>'
 +'<circle cx="16.2" cy="17.2" r="2.6" fill="none" stroke="#2a1a10" stroke-width="1.2"/><circle cx="23.8" cy="17.2" r="2.6" fill="none" stroke="#2a1a10" stroke-width="1.2"/><path d="M18.8 17.2h2.4" stroke="#2a1a10" stroke-width="1.2"/>'
 +'<path d="M17.5 22.2q2.5 1.6 5 0" fill="none" stroke="#2a1a10" stroke-width="1.3" stroke-linecap="round"/>'
 +'<path d="M20 33.5c-3-1.6-6.5-1.8-9-1.2v6.2c2.5-.6 6-.4 9 1.2 3-1.6 6.5-1.8 9-1.2v-6.2c-2.5-.6-6-.4-9 1.2z" fill="#fffbea" stroke="#2a1a10" stroke-width="1.4" stroke-linejoin="round"/>'
 +'<path d="M20 33.5v6.2" stroke="#2a1a10" stroke-width="1.2"/>'
 +'</svg>';

function planGranted(){return !!(openai&&openai.account&&openai.account.signed_in&&openai.account.plan_usage)}
function timeText(iso){if(!iso)return '';var d=new Date(iso);return isNaN(d)?'':d.toLocaleTimeString(isEn()?'en-GB':'he-IL',{hour:'2-digit',minute:'2-digit'})}
function stateLine(){
  var plan=openai&&openai.plan;if(!plan||!planGranted())return '';
  var parts=[];
  if(plan.state==='exhausted')parts.push(t('תקציב החשבון נגמר ב־','The account budget ran out at ')+timeText(plan.since)+(plan.retry_at?t('; ניסיון הבא ב־','; next try at ')+timeText(plan.retry_at):''));
  else if(plan.state==='not_eligible')parts.push(t('החשבון אינו זכאי לשימוש בתוכנית; התחברו מחדש.','The account is not eligible for plan usage; reconnect.'));
  else parts.push(t('החשבון מוכן לשימוש.','The account is ready to use.'));
  if(plan.fallback_calls>0)parts.push(t(plan.fallback_calls+' פעמים עברו הקריאות למפתח ה־API','Switched to the API key '+plan.fallback_calls+' times')+(plan.last_fallback_at?t(' (לאחרונה ב־',' (last at ')+timeText(plan.last_fallback_at)+')':''));
  return parts.join(' · ');
}
function renderBadge(){
  if(!badge)return;
  var kind='';
  if(planGranted()){var p=openai.plan;kind=(p&&(p.state==='exhausted'||p.state==='not_eligible'))?'warn':'ready'}
  else if(openai&&openai.account&&openai.account.signed_in)kind='warn';
  badge.hidden=!kind;badge.className='pf-badge'+(kind?' '+kind:'');
  var label=t('פרופיל וחשבונות','Profile and accounts');
  button.setAttribute('aria-label',label);button.title=label;
}

var ui={};
function build(){
  dlg=el('dialog','pf-dialog');dlg.setAttribute('aria-labelledby','pf-title');
  dlg.innerHTML='<div class="pf-head"><h2 id="pf-title"></h2><button type="button" class="pf-close" id="pf-close"></button></div>'
   +'<section class="pf-section" id="pf-openai"><h3 id="pf-openai-title"></h3><p class="pf-line" id="pf-openai-status" role="status"></p><p class="pf-line quiet" id="pf-openai-state"></p>'
   +'<label class="pf-check" id="pf-fallback-row"><input type="checkbox" id="pf-fallback"><span id="pf-fallback-text"></span></label>'
   +'<p class="pf-line pf-warn" id="pf-openai-warn" hidden></p>'
   +'<div class="pf-actions"><button type="button" class="pf-btn" id="pf-oa-connect"></button><button type="button" class="pf-btn" id="pf-oa-reconnect"></button><button type="button" class="pf-btn secondary" id="pf-oa-disconnect"></button></div>'
   +'<p class="pf-line quiet" id="pf-openai-url" hidden></p>'
   +'<p class="pf-line"><a id="pf-usage" href="https://chatgpt.com/#settings" target="_blank" rel="noopener noreferrer"></a></p></section>'
   +'<section class="pf-section" id="pf-google"><h3 id="pf-google-title"></h3><p class="pf-line" id="pf-google-status" role="status"></p><p class="pf-line quiet" id="pf-google-sync"></p>'
   +'<div class="pf-actions"><button type="button" class="pf-btn" id="pf-g-connect"></button><button type="button" class="pf-btn secondary" id="pf-g-sync"></button><button type="button" class="pf-btn secondary" id="pf-g-library"></button><button type="button" class="pf-btn secondary" id="pf-g-disconnect"></button></div></section>'
   +'<p class="pf-foot"><a id="pf-help" href="/help#openai-account" target="_blank" rel="noopener"></a></p>';
  document.body.appendChild(dlg);
  ['close','openai-title','openai-status','openai-state','fallback','fallback-text','openai-warn','oa-connect','oa-reconnect','oa-disconnect','openai-url','usage','google-title','google-status','google-sync','g-connect','g-sync','g-library','g-disconnect','help','title','fallback-row'].forEach(function(id){ui[id]=dlg.querySelector('#pf-'+id)});
  ui.close.onclick=function(){dlg.close()};
  dlg.addEventListener('click',function(ev){if(ev.target===dlg)dlg.close()});
  dlg.addEventListener('close',function(){stopTimer();if(opener&&opener.focus)opener.focus()});
  ui['oa-connect'].onclick=ui['oa-reconnect'].onclick=openaiSignIn;
  ui['oa-disconnect'].onclick=openaiSignOut;
  ui.fallback.onchange=saveFallback;
  ui['g-connect'].onclick=googleSignIn;ui['g-sync'].onclick=googleSync;ui['g-disconnect'].onclick=googleSignOut;
  ui['g-library'].onclick=function(){var b=document.getElementById('library-button');dlg.close();if(b)b.click()};
}

function render(){
  if(!dlg)return;
  var en=isEn();dlg.dir=en?'ltr':'rtl';dlg.lang=en?'en':'he';
  ui.title.textContent=t('פרופיל וחשבונות','Profile and accounts');
  ui.close.textContent=t('סגירה','Close');
  ui['openai-title'].textContent=t('חשבון OpenAI (ChatGPT Plus/Pro)','OpenAI account (ChatGPT Plus/Pro)');
  ui['google-title'].textContent=t('חשבון Google (הספרייה ב־Drive)','Google account (library in Drive)');
  ui.usage.textContent=t('שימוש בחשבון: הגדרות ChatGPT ← Usage','Account usage: ChatGPT settings → Usage');
  ui.help.textContent=t('איך זה עובד? עזרה על חשבון OpenAI','How does it work? Help on the OpenAI account');
  ui.help.setAttribute('href',en?'/help#en-openai-account':'/help#openai-account');
  ui['fallback-text'].textContent=t('כשתקציב החשבון נגמר, המשך אוטומטית עם מפתח ה־API','When the account budget runs out, continue automatically with the API key');
  ui['oa-connect'].textContent=t('התחברות עם OpenAI','Connect OpenAI');
  ui['oa-reconnect'].textContent=t('התחברות מחדש','Reconnect');
  ui['oa-disconnect'].textContent=t('התנתקות','Disconnect');
  renderOpenAI();renderGoogle();renderBadge();
}
function hideOpenAIControls(){ui['oa-connect'].hidden=ui['oa-reconnect'].hidden=ui['oa-disconnect'].hidden=true;ui['fallback-row'].hidden=true;ui['openai-state'].textContent='';ui['openai-warn'].hidden=true}
function renderOpenAI(){
  var s=openai;
  if(!s){ui['openai-status'].textContent=t('טוען…','Loading…');hideOpenAIControls();return}
  var acc=s.account||{};
  if(!acc.available){ui['openai-status'].textContent=t('חיבור חשבון OpenAI אינו זמין בגרסה הזו.','OpenAI account sign-in is not available in this build.');hideOpenAIControls();return}
  var granted=planGranted();
  ui['openai-status'].textContent=!acc.signed_in?t('לא מחוברים. הקריאות ייצאו עם מפתח ה־API.','Not connected. Calls will use the API key.'):
    granted?t('מחוברים: ','Connected: ')+(acc.email||'')+t(' — קריאות למודלים של OpenAI ייצאו קודם על חשבון המנוי.',' — calls to OpenAI models go to the plan first.'):
    t('מחוברים: ','Connected: ')+(acc.email||'')+t(' — אבל השימוש בתוכנית לא אושר. יש לאשר אותו במסך ההסכמה של OpenAI; התחברו מחדש ואשרו.',' — but plan usage was not allowed. It must be allowed on OpenAI\'s consent screen; reconnect and allow it.');
  ui['oa-connect'].hidden=!!acc.signed_in;ui['oa-reconnect'].hidden=!acc.signed_in||granted;ui['oa-disconnect'].hidden=!acc.signed_in;
  ui['fallback-row'].hidden=false;
  if(document.activeElement!==ui.fallback)ui.fallback.checked=s.auto_fallback!==false;
  ui['openai-state'].textContent=stateLine();
  var warn=ui['openai-warn'];
  warn.hidden=!(ui.fallback.checked&&s.key_available===false);
  warn.textContent=warn.hidden?'':t('ההמשך האוטומטי מסומן, אבל לא הוזן מפתח API של OpenAI: כשהתקציב ייגמר העבודה תיעצר.','Automatic continue is on, but no OpenAI API key is entered: the work will stop when the budget runs out.');
  if(acc.signed_in)ui['openai-url'].hidden=true;
}
function syncLine(){
  var sync=(google&&google.sync)||{};
  if(sync.state==='running')return t('מסנכרן…','Syncing…');
  if(sync.state==='signed_out')return t('ההתחברות פגה — התחברו שוב','Sign-in expired — sign in again');
  if(sync.state==='error')return t('הסנכרון נכשל. נסו שוב.','Sync failed. Try again.');
  if(sync.last_sync_at){var d=new Date(sync.last_sync_at);return t('סונכרן לאחרונה: ','Last synced: ')+(isNaN(d)?'':d.toLocaleString(isEn()?'en-GB':'he-IL'))}
  return t('עדיין לא סונכרן','Not synced yet');
}
function renderGoogle(){
  var hide=function(){ui['g-connect'].hidden=ui['g-sync'].hidden=ui['g-library'].hidden=ui['g-disconnect'].hidden=true};
  if(!google){ui['google-status'].textContent=t('טוען…','Loading…');ui['google-sync'].textContent='';hide();return}
  if(!google.available){ui['google-status'].textContent=t('הסנכרון עם Google Drive אינו זמין בגרסה הזו.','Google Drive sync is not available in this build.');ui['google-sync'].textContent='';hide();return}
  var signedIn=!!google.signed_in,again=signedIn&&google.sync&&google.sync.state==='signed_out';
  ui['google-status'].textContent=signedIn?t('מחוברים: ','Connected: ')+(google.email||google.name||''):t('לא מחוברים. הספרייה נשארת על המחשב הזה.','Not connected. The library stays on this computer.');
  ui['google-sync'].textContent=signedIn?syncLine():'';
  ui['g-connect'].hidden=signedIn&&!again;
  ui['g-connect'].textContent=again?t('התחברות מחדש','Sign in again'):t('התחברות עם Google','Sign in with Google');
  ui['g-sync'].hidden=!signedIn;ui['g-sync'].textContent=t('סנכרון עכשיו','Sync now');
  ui['g-sync'].disabled=!!(google.sync&&google.sync.state==='running');
  ui['g-library'].hidden=!signedIn||!document.getElementById('library-button');ui['g-library'].textContent=t('פתיחת הספרייה (כולל Drive)','Open the library (including Drive)');
  ui['g-disconnect'].hidden=!signedIn;ui['g-disconnect'].textContent=t('התנתקות','Disconnect');
}

async function refreshOpenAI(){
  try{openai=await post('/openai-account')}catch(_){return}
  if(openai.account&&openai.account.signed_in)openaiWaitUntil=0;
  renderBadge();if(dlg&&dlg.open)renderOpenAI();
}
async function refreshGoogle(){
  try{google=await post('/account')}catch(_){return}
  if(google.signed_in)googleWaitUntil=0;
  if(dlg&&dlg.open)renderGoogle();
}
function tick(){
  if(!dlg||!dlg.open)return;
  refreshOpenAI();refreshGoogle();
  var waiting=openaiWaitUntil>Date.now()||googleWaitUntil>Date.now();
  timer=setTimeout(tick,waiting?2000:6000);
}
function stopTimer(){clearTimeout(timer);timer=null}

async function openaiSignIn(){
  var bs=[ui['oa-connect'],ui['oa-reconnect']];bs.forEach(function(b){b.disabled=true});
  try{
    var r=await post('/openai-account/sign-in');openaiWaitUntil=Date.now()+600000;
    if(r&&typeof r.url==='string'&&/^https:\/\//.test(r.url)){
      var p=ui['openai-url'];p.textContent='';p.appendChild(document.createTextNode(t('אם הדפדפן לא נפתח, ','If the browser did not open, ')));
      var a=el('a','',t('פתחו את דף ההתחברות','open the sign-in page'));a.href=r.url;a.target='_blank';a.rel='noopener noreferrer';p.appendChild(a);p.hidden=false;
    }
    stopTimer();tick();
  }catch(error){ui['openai-status'].textContent=error.message}
  finally{bs.forEach(function(b){b.disabled=false})}
}
async function openaiSignOut(){
  try{await post('/openai-account/sign-out')}catch(_){}
  await refreshOpenAI();
}
async function saveFallback(){
  try{openai=await post('/openai-account/settings',{auto_fallback:ui.fallback.checked});renderOpenAI();renderBadge()}
  catch(error){ui['openai-status'].textContent=error.message}
}
/* On the main page the legacy Google controls (ui.js, hidden in the header) own the sync state and the
   library refresh, so the window drives them. Elsewhere it calls the same routes directly. */
function legacy(id){return document.getElementById(id)}
async function googleSignIn(){
  var old=legacy('sign-in-button');
  try{if(old)old.click();else await post('/account/sign-in');googleWaitUntil=Date.now()+600000;stopTimer();tick()}
  catch(error){ui['google-status'].textContent=error.message}
}
async function googleSync(){
  var old=legacy('account-sync-now');
  try{if(old)old.click();else{var r=await post('/account/sync');google=Object.assign({},google,{sync:r.sync});renderGoogle()}stopTimer();tick()}
  catch(error){ui['google-sync'].textContent=error.message}
}
async function googleSignOut(){
  var old=legacy('account-sign-out');
  try{if(old)old.click();else await post('/account/sign-out')}catch(_){}
  await refreshGoogle();
}

function openWindow(){
  if(!dlg)build();
  opener=button;render();
  if(!dlg.open)dlg.showModal();
  stopTimer();tick();
}

function init(){
  button=el('button','pf-button');button.type='button';button.id='profile-button';
  button.setAttribute('aria-haspopup','dialog');
  button.innerHTML=DRAWING+'<span class="pf-badge" hidden></span>';
  badge=button.querySelector('.pf-badge');
  mount.appendChild(button);
  button.addEventListener('click',openWindow);
  renderBadge();
  if(token){refreshOpenAI();setInterval(function(){if(!document.hidden)refreshOpenAI()},60000)}
  new MutationObserver(function(){renderBadge();render()}).observe(doc,{attributes:true,attributeFilter:['lang','data-lang']});
}
init();
})();
