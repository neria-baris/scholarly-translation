const {token}=window.UI_CONFIG;
const $=id=>document.getElementById(id);
function esc(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
let uploaded=null,currentJob=null,unitIndex=0,busy=false,pollTimer=null,modelConfigAvailable=false;
let modelCatalog=[],pdfFonts=[],keyProvidersAvailable={};
let resolvedProviders=[],configuredProviders=[];
let roleSelections={translator:null,semantic_reviewer:null,chapter_qa:null};
let qaTouched=false,chapterQaTouched=false;
let previewCounter=0,previewTimer=null;
let previewState={fingerprint:null,valid:false,withinBudget:false};
function previewFingerprint(chosen){
  return JSON.stringify([uploaded&&uploaded.path,chosen.use_server_config,chosen.role_selections,chosen.quality,chosen.profile,chosen.budget_usd,chosen.language]);
}
function isReal(){return $('model').value!=='auto'}
function isServer(){return $('model').value==='server'}
const defaults={profile:'scholarly',quality:'fast',language:'auto',budget_usd:null,model:'auto'};
let preferences={...defaults};
try{const stored=JSON.parse(localStorage.getItem('document-preferences')||'null');if(stored)preferences={...defaults,...stored}}catch(_){}
function remember(key,value){try{localStorage.setItem(key,value)}catch(_){}}
function forget(key){try{localStorage.removeItem(key)}catch(_){}}
async function request(route,data={},binary=false){
  const response=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json','X-UI-Token':token},body:JSON.stringify(data)});
  if(!response.ok){let result;try{result=await response.json()}catch(_){throw Error('לא ניתן להתחבר לשרת המקומי. הפעילו אותו שוב.')}
    const error=Error(result.error||'הפעולה לא הושלמה');error.status=response.status;throw error}
  return binary?response.blob():response.json();
}
function message(text){$('form-message').textContent=text;$('form-message').hidden=!text}
function show(panel){
  const changed=$(panel).hidden;
  for(const id of ['start-panel','processing-panel','result-panel'])$(id).hidden=id!==panel;
  if(changed&&panel==='processing-panel')window.scrollTo({top:0,behavior:'auto'});
}
function setBusy(value){busy=value;updateSettings();$('sample-button').disabled=value}

// ---- model/QA role selection UI ----
function catalogOptionsHtml(provider){
  return modelCatalog.filter(m=>provider?m.provider===provider:true)
    .map(m=>`<option value="${m.provider}:${m.model}">${m.provider}/${m.model} ($${m.rates_per_million.input}/${m.rates_per_million.output} ל-1M)</option>`).join('');
}
function roleFieldsHtml(role){
  return `<select class="role-select" data-role="${role}"><option value="">בחרו מודל…</option>${catalogOptionsHtml()}<option value="other">אחר (מודל/ספק מותאם)…</option></select>
  <div class="other-fields" data-role="${role}">
    <select class="other-provider-type" data-role="${role}"><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option><option value="openai_compatible">תואם-OpenAI (כתובת מותאמת)</option></select>
    <input class="other-model" data-role="${role}" placeholder="מזהה מודל" dir="ltr">
    <input class="other-base-url" data-role="${role}" placeholder="https://… (רק לתואם-OpenAI)" dir="ltr">
    <input class="other-context" data-role="${role}" type="number" min="1" placeholder="חלון הקשר (טוקנים)" dir="ltr">
    <input class="other-max-output" data-role="${role}" type="number" min="1" max="128000" placeholder="תקרת פלט (עד 128,000 טוקנים)" dir="ltr">
    <input class="other-usable" data-role="${role}" type="number" min="1" placeholder="חלון שימוש (רשות)" dir="ltr">
    <input class="other-rate-input" data-role="${role}" type="number" min="0" step="0.01" placeholder="תעריף קלט ($/1M, רשות)" dir="ltr">
    <input class="other-rate-output" data-role="${role}" type="number" min="0" step="0.01" placeholder="תעריף פלט ($/1M, רשות)" dir="ltr">
    <input class="other-rate-cached" data-role="${role}" type="number" min="0" step="0.01" placeholder="קריאת מטמון ($/1M, רשות)" dir="ltr">
    <input class="other-rate-write" data-role="${role}" type="number" min="0" step="0.01" placeholder="כתיבת מטמון קצר ($/1M, רשות)" dir="ltr">
    <input class="other-rate-write1h" data-role="${role}" type="number" min="0" step="0.01" placeholder="כתיבת מטמון שעה ($/1M, רשות)" dir="ltr">
    <p class="advanced-note">אם לא תוזן תעריף, תשמש הנחה שמרנית ומסומנת "אינה רשמית" לצורך אומדן בלבד.</p>
  </div>`;
}
function initRoleUI(){
  for(const role of ['translator','semantic_reviewer','chapter_qa']){
    const block=document.querySelector(`.role-block[data-role="${role}"] .role-fields`);
    if(block)block.innerHTML=roleFieldsHtml(role);
  }
  document.querySelectorAll('.role-select').forEach(select=>{
    select.addEventListener('change',()=>onRoleSelectChange(select.dataset.role,select.value));
  });
  document.querySelectorAll('.other-fields input,.other-provider-type')
    .forEach(input=>input.addEventListener('input',()=>onOtherFieldChange(input.dataset.role)));
}
function onRoleSelectChange(role,value){
  if(role==='semantic_reviewer')qaTouched=true;
  if(role==='chapter_qa')chapterQaTouched=true;
  const otherFields=document.querySelector(`.other-fields[data-role="${role}"]`);
  otherFields.classList.toggle('active',value==='other');
  if(value==='other'){onOtherFieldChange(role)}
  else if(value){
    const [provider,model]=value.split(':');
    roleSelections[role]={source:'catalog',provider,model};
  } else {roleSelections[role]=null}
  cascadeQaMirror(role);
  renderKeyFields();schedulePreview();
}
function onOtherFieldChange(role){
  if(role==='semantic_reviewer')qaTouched=true;
  if(role==='chapter_qa')chapterQaTouched=true;
  const q=sel=>document.querySelector(`.${sel}[data-role="${role}"]`);
  const providerType=q('other-provider-type').value,model=q('other-model').value.trim();
  const toInt=raw=>{if(raw==='')return NaN;const n=Number(raw);return Number.isInteger(n)?n:NaN};
  const contextWindow=toInt(q('other-context').value),maxOutput=toInt(q('other-max-output').value);
  const baseUrl=q('other-base-url').value.trim();
  const rateInput=q('other-rate-input').value,rateOutput=q('other-rate-output').value;
  const selection={source:'other',provider_type:providerType,model,context_window:contextWindow,max_output_tokens:maxOutput};
  if(baseUrl)selection.base_url=baseUrl;
  if(q('other-usable').value!=='')selection.usable_context_tokens=Number(q('other-usable').value);
  if(rateInput!==''||rateOutput!==''){
    selection.rates={input:rateInput===''?null:Number(rateInput),output:rateOutput===''?null:Number(rateOutput)};
    for(const [field,key] of [['other-rate-cached','cached'],['other-rate-write','cache_write'],['other-rate-write1h','cache_write_1h']]){
      if(q(field).value!=='')selection.rates[key]=Number(q(field).value);
    }
  }
  roleSelections[role]=(model&&Number.isInteger(contextWindow)&&Number.isInteger(maxOutput))?selection:null;
  cascadeQaMirror(role);
  renderKeyFields();schedulePreview();
}
function mirrorTranslatorToQa(){
  if(!qaTouched){roleSelections.semantic_reviewer=roleSelections.translator;syncRoleUI('semantic_reviewer')}
  if(!chapterQaTouched){roleSelections.chapter_qa=roleSelections.semantic_reviewer;syncRoleUI('chapter_qa')}
}
function cascadeQaMirror(role){
  if(role==='translator')mirrorTranslatorToQa();
  else if(role==='semantic_reviewer'&&!chapterQaTouched){roleSelections.chapter_qa=roleSelections.semantic_reviewer;syncRoleUI('chapter_qa')}
}
function syncRoleUI(role){
  const selection=roleSelections[role],select=document.querySelector(`.role-select[data-role="${role}"]`);
  if(!select)return;
  if(selection&&selection.source==='catalog'){select.value=selection.provider+':'+selection.model;
    document.querySelector(`.other-fields[data-role="${role}"]`).classList.remove('active')}
  else if(selection&&selection.source==='other'){select.value='other';
    document.querySelector(`.other-fields[data-role="${role}"]`).classList.add('active');
    const q=sel=>document.querySelector(`.${sel}[data-role="${role}"]`);
    q('other-provider-type').value=selection.provider_type;
    q('other-model').value=selection.model;
    q('other-base-url').value=selection.base_url||'';
    q('other-context').value=selection.context_window;
    q('other-max-output').value=selection.max_output_tokens;
    q('other-usable').value=selection.usable_context_tokens||'';
    q('other-rate-input').value=selection.rates?selection.rates.input:'';
    q('other-rate-output').value=selection.rates?selection.rates.output:'';
    q('other-rate-cached').value=selection.rates?.cached??'';
    q('other-rate-write').value=selection.rates?.cache_write??'';
    q('other-rate-write1h').value=selection.rates?.cache_write_1h??'';}
  else select.value='';
}
function requiredProviderIdsFromSelections(selections,quality){
  const roles=quality==='fast'?['translator']:['translator','semantic_reviewer','chapter_qa'];
  const ids=new Set();
  for(const role of roles){const sel=selections&&selections[role];if(!sel)continue;
    const pid=sel.source==='catalog'?sel.provider:(sel.provider_type==='openai_compatible'?'compatible':sel.provider_type);
    ids.add(pid)}
  return [...ids];
}
function requiredProviderIds(){return resolvedProviders.map(p=>p.id)}
function requiredProviderIdsForJobSettings(settingsObj){
  if(!settingsObj||settingsObj.model!=='configured')return[];
  if(settingsObj.role_selections)return requiredProviderIdsFromSelections(settingsObj.role_selections,settingsObj.quality);
  if(settingsObj.model_config){
    const config=settingsObj.model_config,roles=settingsObj.quality==='fast'?['translator']:['translator','semantic_reviewer','chapter_qa'];
    return [...new Set(roles.map(r=>config.models[r]?.provider).filter(pid=>pid&&config.providers[pid]?.type!=='mock'))];
  }
  return[];
}
function renderKeyFields(){
  const container=document.querySelector('.key-fields');if(!container)return;
  const ids=requiredProviderIds();
  container.innerHTML=ids.map(pid=>`<div><label for="key-${esc(pid)}">מפתח API — ${esc(pid)}${keyProvidersAvailable[pid]?' (זמין)':''}</label>
    <small dir="ltr">${esc(resolvedProviders.find(p=>p.id===pid)?.endpoint||'הספק הרשמי')}</small>
    <input id="key-${esc(pid)}" class="key-input" type="password" data-provider="${esc(pid)}" autocomplete="off"></div>`).join('');
}
async function saveKeys(){
  const inputs=[...document.querySelectorAll('.key-input')];
  const keys={};for(const input of inputs)if(input.value)keys[input.dataset.provider]=input.value;
  $('key-message').textContent='שומר…';
  try{const result=await request('/model-keys',{keys});keyProvidersAvailable=result.available;
    $('key-message').textContent='המפתחות נשמרו בזיכרון השרת להרצה הנוכחית.';renderKeyFields();updateSettings();
  }catch(error){$('key-message').textContent=error.message}
  finally{for(const input of inputs)input.value=''}
}
function missingKeyProviders(){return requiredProviderIds().filter(pid=>!keyProvidersAvailable[pid])}
function renderResumeKeyFields(){
  const container=$('resume-key-fields');if(!container)return;
  const required=requiredProviderIdsForJobSettings(currentJob&&currentJob.settings);
  const missing=required.filter(pid=>!keyProvidersAvailable[pid]);
  $('resume-keys').hidden=!missing.length;
  container.innerHTML=missing.map(pid=>`<div><label for="resume-key-${pid}">מפתח API — ${esc(pid)}</label>
    <input id="resume-key-${pid}" class="resume-key-input" type="password" data-provider="${esc(pid)}" autocomplete="off"></div>`).join('');
}
async function saveResumeKeys(){
  const inputs=[...document.querySelectorAll('.resume-key-input')];
  const keys={};for(const input of inputs)if(input.value)keys[input.dataset.provider]=input.value;
  $('resume-key-message').textContent='שומר…';
  try{const result=await request('/model-keys',{keys});keyProvidersAvailable=result.available;
    $('resume-key-message').textContent='המפתחות נשמרו. אפשר להמשיך.';renderResumeKeyFields();
  }catch(error){$('resume-key-message').textContent=error.message}
  finally{for(const input of inputs)input.value=''}
}

// ---- preview ----
function schedulePreview(){
  clearTimeout(previewTimer);
  previewCounter++; // invalidate any in-flight preview immediately on any relevant change
  previewState={fingerprint:null,valid:false,withinBudget:false};
  resolvedProviders=[];
  updateSettings();
  if(!isReal()){$('preview-card').hidden=true;renderKeyFields();return}
  previewTimer=setTimeout(runPreview,450);
}
function validBudget(value){return typeof value==='number'&&Number.isFinite(value)&&value>0}
async function runPreview(){
  const id=++previewCounter;
  const chosen=settings();
  if(!validBudget(chosen.budget_usd)){previewState={fingerprint:'',valid:false,withinBudget:false};$('preview-card').hidden=false;
    $('preview-body').textContent='יש להגדיר תקציב מרבי למסמך (מספר חיובי) כדי לקבל אומדן.';$('translation-options').open=true;$('budget').focus();return}
  const fingerprint=previewFingerprint(chosen);
  if(!isServer()&&(!chosen.role_selections||!chosen.role_selections.translator)){$('preview-card').hidden=true;return}
  try{
    const models=await request('/document-models',{settings:chosen});
    if(id!==previewCounter||fingerprint!==previewFingerprint(settings()))return;
    resolvedProviders=models.required_providers;
    for(const provider of resolvedProviders)keyProvidersAvailable[provider.id]=provider.key_available;
    renderKeyFields();updateSettings();
    if(!uploaded){$('preview-card').hidden=true;return}
    const preview=await request('/document-preview',{path:uploaded.path,settings:chosen});
    if(id!==previewCounter)return; // stale response, ignore: input changed since this request started
    const currentFingerprint=previewFingerprint(settings());
    if(fingerprint!==currentFingerprint)return; // input changed mid-flight
    previewState={fingerprint,valid:true,
      withinBudget:preview.conservative_total_ceiling_usd<=chosen.budget_usd};
    renderPreview(preview);
    updateSettings();
  }catch(error){if(id!==previewCounter)return;$('preview-card').hidden=false;
    $('preview-body').textContent='אומדן לא זמין: '+error.message}
}
function renderPreview(preview){
  $('preview-card').hidden=false;
  const rows=[];
  for(const chapter of preview.chapters){
    for(const [role,usage] of Object.entries(chapter.role_usage)){
      rows.push(`<tr><td>${esc(role==='notebook_keeper'?'מחברת הספר':role)}</td><td dir="ltr">${esc(usage.provider)}/${esc(usage.model)}</td><td dir="ltr">${esc(usage.calls)}</td>
        <td dir="ltr">${esc(usage.input_tokens_upper_bound)} / ${esc(usage.output_tokens_upper_bound)}<br>${esc(usage.count_method)} · ${usage.exact?'ספירה לפי קידוד':'אומדן'}</td>
        <td dir="ltr">$${Number(usage.expected_cost_usd).toFixed(4)}</td><td dir="ltr">$${Number(usage.conservative_cost_usd).toFixed(4)}</td>
        <td>${usage.pricing_basis==='unknown_conservative'?'הנחה שמרנית (לא רשמי)':esc(usage.pricing_basis)}</td></tr>`);
    }
  }
  $('preview-body').innerHTML=`<div class="table-scroll"><table><thead><tr><th>תפקיד</th><th>מודל</th><th>קריאות מרביות</th><th>טוקנים קלט / פלט — גבול תכנון</th><th>צפוי</th><th>תקרה לפי ההנחות</th><th>בסיס תמחור</th></tr></thead>
    <tbody>${rows.join('')}</tbody></table></div>
    <p>סה״כ צפוי: $${Number(preview.expected_total_cost_usd).toFixed(4)} · תקרה שמרנית: $${Number(preview.conservative_total_ceiling_usd).toFixed(4)}
    (${esc(preview.chapter_count)} פרקים) · קטלוג: ${esc(preview.catalog_version||'')}</p>
    <p class="advanced-note">האומדן "צפוי" מניח כ-35% ניצול תקרת הפלט, ללא תיקונים וללא הנחת פגיעה במטמון; התקרה לפי ההנחות כוללת תיקון מקומי אחד ובדיקה חוזרת וכתיבת מטמון מלאה. למודל אחר ללא תעריף משתמשים בהנחת $4 קלט / $20 פלט למיליון; זו אינה התחייבות או תקרת חיוב של הספק.</p>`;
}

function settings(){
  const model=isReal()?'configured':'auto';
  const result={profile:$('profile').value,quality:$('quality').value,language:$('language').value,
    budget_usd:$('budget').value.trim()===''?null:Number($('budget').value),model,automation:model==='configured',
    font_id:$('font-before').value||null};
  if(isServer())result.use_server_config=true;
  else if(model==='configured'&&roleSelections.translator)result.role_selections={...roleSelections};
  return result;
}
function updateSettings(){
  const chosen=settings();preferences=chosen;remember('document-preferences',JSON.stringify(preferences));
  $('profile-summary').textContent=$('profile').selectedOptions[0].textContent.split(' (')[0];
  $('quality-summary').textContent=$('quality').selectedOptions[0].textContent.split(' —')[0];
  $('model-summary').textContent=$('model').selectedOptions[0].textContent.split(' —')[0];
  const auto=chosen.model==='auto';
  $('model-settings').hidden=auto;
  document.querySelectorAll('#model-settings .role-block').forEach(block=>block.hidden=isServer());
  $('translate-label').textContent=auto?'פתיחת תצוגת ניסיון':busy?'מעלה קובץ…':'תרגום לעברית';
  const missing=auto?[]:missingKeyProviders();
  const previewReady=auto||(previewState.valid&&previewState.fingerprint===previewFingerprint(chosen)&&previewState.withinBudget);
  $('translate-button').disabled=!uploaded||busy||(!auto&&((!chosen.role_selections&&!isServer())||missing.length>0||!previewReady));
  $('send-note').textContent=auto?'ללא עלות וללא תרגום אמיתי. יוצג טקסט מקום-שמור בלבד.':
    missing.length?'יש לשמור מפתח API עבור: '+missing.join(', ')+' לפני התרגום.':
    !chosen.role_selections&&!isServer()?'בחרו מודל מתרגם לפני התרגום.':
    !previewState.valid||previewState.fingerprint!==previewFingerprint(chosen)?'ממתינים לאומדן עדכני לפני התרגום.':
    !previewState.withinBudget?'האומדן השמרני חורג מהתקציב שנבחר; הגדילו תקציב או שנו הגדרות.':
    'לחיצה על תרגום תבקש אישור לשליחת הטקסט לספקים שנבחרו.';
  $('budget').disabled=auto;
  $('model-help').textContent=auto?'Auto הוא תצוגת ניסיון ללא עלות וללא תרגום אמיתי.':
    isServer()?'משתמש בתצורת המודלים המקומית של השרת.':'בחרו מודל לתרגום ול־QA והזינו מפתחות API לספקים שנבחרו.';
  $('quality-help').textContent=auto?'Auto תמיד מריץ ברמה מהירה (ללא בדיקה נוספת), ללא קשר לבחירה כאן.':
    chosen.quality==='fast'?'ללא קריאות בדיקה נוספות; המהיר והחסכוני ביותר.':
    chosen.quality==='checked'?'בדיקת מקטעים שסומנו כמסוכנים, ובדיקת פרקים בסוף כל פרק.':
    'בדיקת כל מקטע ובדיקת פרקים; המקיף והיקר ביותר.';
}
function setUploaded(file){
  uploaded=file;$('upload-empty').hidden=!!file;$('upload-selected').hidden=!file;
  if(file){$('filename').textContent=file.name;$('file-size').textContent=(file.size/1024/1024<1?Math.ceil(file.size/1024)+' KB':(file.size/1024/1024).toFixed(1)+' MB')+' · '+file.name.split('.').pop().toUpperCase()}
  updatePdfFontVisibility();updateSettings();schedulePreview();
}
function updatePdfFontVisibility(){
  const isPdf=uploaded&&/\.pdf$/i.test(uploaded.name);
  $('font-before').closest('.field').hidden=!isPdf;
}
async function uploadFile(file){
  if(!file||busy)return;
  if(!/\.(pdf|epub)$/i.test(file.name)||file.size===0||file.size>25*1024*1024){message('בחרו קובץ PDF או EPUB עד 25 MB.');return}
  setBusy(true);message('');
  try{const response=await fetch('/upload?name='+encodeURIComponent(file.name),{method:'POST',headers:{'X-UI-Token':token},body:file});
    const result=await response.json();if(!response.ok)throw Error(result.error||'העלאת הקובץ נכשלה');
    setUploaded({name:file.name,size:file.size,path:result.path});
  }catch(error){message(error.message)}finally{setBusy(false)}
}
function showConnection(){if(!$('connection-dialog').open)$('connection-dialog').showModal()}
function renderConnection(){
  $('connection-label').textContent='מודל: '+(isServer()?'תצורת שרת':isReal()?'משלי':'Auto');
  $('connection-dot').classList.toggle('connected',modelConfigAvailable||Object.keys(keyProvidersAvailable).length>0);
  $('connection-detail').textContent='Auto הוא מצב תצוגת ניסיון בלבד, ללא עלות וללא תרגום אמיתי. "מודל משלי" משתמש במפתח ה-API שלכם, הנשמר בזיכרון השרת לאורך ההרצה בלבד.';
}
function askProviderConsent(chosen){
  const dialog=$('provider-consent');
  const providers=resolvedProviders.map(p=>p.id+(p.endpoint?' ('+p.endpoint+')':'')).join(', ');
  $('provider-consent-detail').textContent='הטקסט של '+uploaded.name+' יישלח לספקים: '+providers+
    '. פרופיל: '+$('profile-summary').textContent+'. רמת בדיקה: '+$('quality-summary').textContent+
    '. תקציב מרבי לפי האומדן: $'+chosen.budget_usd+'.';
  return new Promise(resolve=>{
    let accepted=false;
    $('confirm-provider-send').onclick=()=>{accepted=true;dialog.close()};
    $('cancel-provider-send').onclick=()=>dialog.close();
    dialog.addEventListener('close',()=>resolve(accepted),{once:true});
    dialog.showModal();$('cancel-provider-send').focus();
  });
}
async function translate(event){
  if(event)event.preventDefault();if(!uploaded||busy)return;message('');
  const chosen=settings(),auto=chosen.model==='auto';
  if(!auto&&!chosen.role_selections&&!isServer()){message('בחרו מודל מתרגם לפני התרגום.');return}
  if(!auto){const missing=missingKeyProviders();if(missing.length){message('יש לשמור מפתח API עבור: '+missing.join(', ')+'.');return}}
  if(!auto&&!validBudget(chosen.budget_usd)){message('יש להגדיר תקציב מרבי למסמך (מספר חיובי) לפני תרגום בתשלום.');$('translation-options').open=true;$('budget').focus();return}
  if(!auto&&(!previewState.valid||previewState.fingerprint!==previewFingerprint(chosen))){message('ממתינים לאומדן עדכני לפני התרגום.');return}
  if(!auto&&!previewState.withinBudget){message('האומדן השמרני חורג מהתקציב שנבחר; הגדילו תקציב או שנו הגדרות.');$('translation-options').open=true;$('budget').focus();return}
  if(!auto&&!await askProviderConsent(chosen))return;
  setBusy(true);
  try{const result=await request('/document-translate',{path:uploaded.path,settings:chosen,paid_confirm:!auto});remember('document-last-job',result.job_id);
    currentJob={job_id:result.job_id,filename:uploaded.name,status:'queued',stage_label:'',completed_units:0,total_units:0,settings:chosen};show('processing-panel');renderProcessing();await poll(result.job_id);
  }catch(error){show('start-panel');message(error.message);setBusy(false)}
}
function bookPhaseFor(job){
  if(['paused','interrupted'].includes(job.status))return'paused';
  if(job.status==='failed')return'error';
  if(job.status==='completed')return'finished';
  if(['queued','reading'].includes(job.status))return'start';
  return'open';
}
function renderBook(inResult=false){
  const host=$(inResult?'result-book-host':'processing-book-host'),book=$('pixel-book');
  if(book.parentElement!==host)host.append(book,$('processing-percentage'));
  const next=bookPhaseFor(currentJob),previous=book.dataset.phase;
  if(next==='open'&&previous==='start')book.classList.add('opening');
  if(next!=='open')book.classList.remove('opening');
  book.dataset.phase=next;
  const pct=currentJob.status==='completed'?100:Math.min(95,Math.max(0,currentJob.progress?.percentage??
    (currentJob.total_units?Math.round(95*currentJob.completed_units/currentJob.total_units):0)));
  $('processing-percentage').textContent=pct+'%';return pct;
}
function renderUsage(id){
  const container=$(id),rows=currentJob.budget_status?.provider_usage||[];
  container.hidden=!rows.length&&!currentJob.local_replays;
  container.innerHTML='<p>שימוש חוזר מקומי: '+esc(currentJob.local_replays||0)+' פעולות · מטמון תוצאות מקומי: '+esc(currentJob.budget_status?.cache_hits||0)+'</p>'+
    rows.map(row=>'<p><b>'+esc(row.provider)+' / '+esc(row.model)+'</b> · '+esc(row.calls)+' קריאות לספק · קלט '+esc(row.input)+' / פלט '+esc(row.output)+
      ' טוקנים · חשיבה '+esc(row.reasoning)+' (כלולה בפלט) · קריאת מטמון ספק '+esc(row.cached)+' · כתיבה '+esc(row.cache_write)+' / שעה '+esc(row.cache_write_1h)+
      (row.unmetered_calls?' · '+esc(row.unmetered_calls)+' קריאות ללא מדידה':'')+'</p>').join('');
}
function renderProcessing(){
  $('processing-title').textContent=currentJob.stage_label||'קוראים את המסמך…';
  $('processing-file').textContent=currentJob.filename;
  const progress=$('translation-progress');
  const pct=renderBook();
  progress.value=pct;$('processing-percentage').textContent=pct+'%';
  let detail;
  if(currentJob.progress&&currentJob.progress.total_chapters){
    detail='פרק '+currentJob.progress.completed_chapters+' מתוך '+currentJob.progress.total_chapters+' הושלם. '+
      (currentJob.progress.phase||'')+' · '+currentJob.progress.completed_steps+'/'+currentJob.progress.total_steps+' קריאות.';
  } else if(currentJob.total_units){
    detail=currentJob.completed_units+' מתוך '+currentJob.total_units+' מקטעים הושלמו.';
    if(currentJob.chapter_progress)detail='פרק '+currentJob.chapter_progress.current+' מתוך '+currentJob.chapter_progress.total+'. '+detail;
  } else detail='מחלצים את הטקסט ומכינים את התרגום.';
  $('processing-detail').textContent=(currentJob.error?currentJob.error+' ':'')+detail+' אפשר לחזור לחלון הזה בהמשך.';
  renderUsage('processing-usage');renderResumeKeyFields();
  if(currentJob.budget_status){
    $('processing-budget').hidden=false;
    $('processing-budget').textContent='הוצאה משוערת: $'+currentJob.budget_status.list_estimated_spent_usd.toFixed(4)+
      ' · שמור/ממתין: $'+currentJob.budget_status.held_usd.toFixed(4)+
      ' · נותר מהתקציב: $'+(currentJob.remaining_budget_usd??0).toFixed(4);
  } else $('processing-budget').hidden=true;
  const canPauseResume=currentJob.settings&&currentJob.settings.automation;
  $('pause-button').hidden=!(canPauseResume&&['translating','reviewing','queued','reading'].includes(currentJob.status));
  $('resume-button').hidden=!(canPauseResume&&['paused','interrupted','failed'].includes(currentJob.status));
  renderResumeKeyFields();
}
async function pauseJob(){
  try{currentJob=await request('/document-pause',{job_id:currentJob.job_id});renderProcessing()}
  catch(error){$('processing-detail').textContent=error.message}
}
async function resumeJob(){
  try{const result=await request('/document-resume',{job_id:currentJob.job_id});
    currentJob.status='translating';renderProcessing();await poll(result.job_id||currentJob.job_id);
  }catch(error){$('processing-detail').textContent=error.message;renderResumeKeyFields()}
}
async function poll(jobId){
  clearTimeout(pollTimer);
  try{const result=await request('/document-job',{job_id:jobId});currentJob={...result,settings:result.settings||currentJob?.settings};
    if(['queued','reading','translating','reviewing','rebuilding'].includes(result.status)){show('processing-panel');renderProcessing();pollTimer=setTimeout(()=>poll(jobId),1400)}
    else if(['paused','interrupted','failed'].includes(result.status)&&result.settings?.automation){show('processing-panel');renderProcessing()}
    else{setBusy(false);show('result-panel');renderResult();window.scrollTo({top:0,behavior:'smooth'})}
  }catch(error){if(error.status===400){forget('document-last-job');currentJob=null;setBusy(false);show('start-panel');message(error.message);return}
    $('processing-detail').textContent=error.message+' ננסה שוב לבדוק את מצב ההרצה.';pollTimer=setTimeout(()=>poll(jobId),5000)}
}
function sourceExt(){return (currentJob.source_kind||'pdf').toLowerCase()}
function qualityLabel(){
  if(currentJob.settings.model==='auto')return'תצוגת ניסיון';
  return ({checked_draft:'טיוטה שבדיקתה הושלמה',draft_with_exceptions:'טיוטה עם חריגים',
    unreviewed_draft:'טיוטה ללא QA',edited_draft_review_stale:'טיוטה ערוכה — QA קודם אינו עדכני'})[currentJob.quality_status]||'טיוטה אוטומטית לא מאושרת';
}
function renderResult(){
  renderBook(true);renderUsage('result-usage');
  const auto=currentJob.settings.model==='auto',complete=currentJob.status==='completed',partial=!complete&&currentJob.completed_units>0;
  $('result-title').textContent=auto?'תצוגת הניסיון מוכנה.':complete?'התרגום מוכן.':partial?'התרגום הושלם חלקית.':'התרגום לא הושלם.';
  $('result-symbol').textContent=auto?'↗':complete?'✓':'!';$('result-eyebrow').textContent=auto?'ללא קריאה לספק':'המסמך שלכם';
  $('result-filename').textContent=currentJob.filename;
  $('download-filename').textContent=currentJob.filename.replace(/\.[^.]+$/,'')+'.he.'+sourceExt();
  $('result-meta').textContent=qualityLabel()+' · '+currentJob.completed_units+'/'+currentJob.total_units+' מקטעים';
  const notices=[];
  if(auto)notices.push('זו תצוגת ניסיון של הממשק בלבד. לא בוצע תרגום אמיתי.');
  if(currentJob.error)notices.push(currentJob.error);
  (currentJob.review_notes||[]).forEach(n=>notices.push(n));
  $('result-notice').textContent=notices.join(' · ');$('result-notice').hidden=!notices.length;
  const limitations=currentJob.export_limitations||[];
  $('result-limitations').textContent=limitations.length?'הערות על בניית הקובץ המתורגם: '+limitations.map(l=>l.detail||l.kind).join(' · '):'';
  $('result-limitations').hidden=!limitations.length;
  const findings=(currentJob.units||[]).reduce((sum,u)=>sum+(u.findings||[]).length+(u.unresolved?1:0),0)+(currentJob.exceptions||[]).length+
    (currentJob.chapter_qa_results||[]).reduce((sum,q)=>sum+(q.issues||[]).length,0);
  const stale=currentJob.quality_status==='edited_draft_review_stale'||(currentJob.units||[]).some(u=>u.review_stale);
  $('result-exceptions').textContent=(findings?'בבדיקות נרשמו '+findings+' ממצאים או הערות; היסטוריית הבדיקה והתיקון מוצגת במקטעים. ':'')+
    (stale?'הטקסט נערך לאחר בדיקת המודל; תוצאות ה־QA הקודמות אינן אישור לגרסה הערוכה.':'');
  $('result-exceptions').hidden=!findings&&!stale;
  $('download-pdf').disabled=!complete;
  renderNotebook();
  $('review-button').disabled=!complete;
  $('cost-summary').textContent=currentJob.estimated_cost_usd?'אומדן $'+currentJob.estimated_cost_usd.toFixed(4):auto?'ללא עלות':'';
  const isPdf=sourceExt()==='pdf';
  $('font-after-field').hidden=!isPdf||!complete;
  if(isPdf&&pdfFonts.length){
    const current=currentJob.settings.font_id||'';
    $('font-after').value=current;
  }
  $('review-panel').hidden=true;$('unit-select').replaceChildren();
  for(const [index,unit] of (currentJob.units||[]).entries()){
    const option=document.createElement('option');option.value=index;option.textContent=(index+1)+' · '+(unit.status||'');$('unit-select').append(option)}
  unitIndex=0;
}
function renderNotebook(){
  const nb=currentJob.book_notebook,box=$('result-notebook'),list=$('notebook-summaries');
  list.replaceChildren();
  const summaries=nb&&nb.chapter_summaries?Object.entries(nb.chapter_summaries).sort((a,b)=>Number(a[0])-Number(b[0])):[];
  box.hidden=!nb||currentJob.status!=='completed';
  for(const [index,text] of summaries){const item=document.createElement('li');item.textContent='פרק '+(Number(index)+1)+': '+text;list.append(item)}
}
async function downloadNotebook(){
  $('download-notebook').disabled=true;
  try{const blob=await request('/document-notebook',{job_id:currentJob.job_id},true);
    const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=currentJob.filename.replace(/\.[^.]+$/,'')+'.notebook.md';
    document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
  }catch(error){$('result-notice').hidden=false;$('result-notice').textContent=error.message}finally{$('download-notebook').disabled=false}
}
function dirty(){return !$('review-panel').hidden&&currentJob?.units[unitIndex]&&$('review-target').value!==currentJob.units[unitIndex].target_text}
function confirmDiscard(){return !dirty()||confirm('יש שינויים שלא נשמרו. לעבור בלי לשמור?')}
function renderReview(){
  const unit=currentJob.units[unitIndex];if(!unit)return;
  $('unit-select').value=unitIndex;$('review-location').textContent='מקטע '+(unitIndex+1)+' מתוך '+currentJob.units.length;
  $('review-source').textContent=unit.source_text;$('review-source').dir='auto';
  $('review-target').value=unit.target_text;$('review-message').textContent='';
  const labels={missing_number:'מספר חסר',missing_footnote_marker:'סימון הערה חסר',missing_citation_reference:'הפניה לבדיקה',missing_formula_token:'נוסחה לבדיקה',proper_name_candidate:'שם לבדיקה',missing_hebrew_script:'הטקסט אינו תרגום עברי'};
  const findings=unit.findings||[];
  const latest=unit.recheck||unit.review;
  const review=latest?(' · '+(unit.recheck?'בדיקה חוזרת: ':'בדיקה: ')+(latest.verdict||latest.status)+
    (latest.issues&&latest.issues.length?' ('+latest.issues.length+' נקודות)':'')+(unit.review_stale?' · נערך לאחר הבדיקה — נדרשת בדיקה מחדש':'')):'';
  const display=value=>typeof value==='string'?value:JSON.stringify(value);
  const issueText=issue=>{
    if(typeof issue!=='object'||!issue)return display(issue);
    return ['severity','type','category','status','verdict','chapter','unit_id','source_span','target_span','translation_span','span','problem','explanation','description','suggested_correction','correction','reason','error']
      .filter(key=>issue[key]!==undefined&&issue[key]!==null)
      .map(key=>key+': '+display(issue[key])).join('\n')||display(issue);
  };
  const details=[];
  for(const issue of latest?.issues||[])details.push('ממצא בבדיקת המקטע:\n'+issueText(issue));
  for(const chapter of currentJob.chapter_qa_results||[]){
    if(chapter.unit_ids?.includes(unit.unit_id)){
      for(const issue of chapter.issues||[])details.push('ממצא בבדיקת הפרק:\n'+issueText(issue));
      if(chapter.verdict&&chapter.verdict!=='PASS')details.push('בדיקת פרק: '+chapter.verdict+' · '+(chapter.status||''));
    }
  }
  for(const exception of currentJob.exceptions||[]){
    if(!exception.unit_id||exception.unit_id===unit.unit_id)
      details.push('חריג '+(exception.unit_id?'במקטע':'במסמך')+':\n'+issueText(exception.issue||exception));
  }
  if(unit.unresolved)details.push('ממצא שלא נפתר: '+display(unit.unresolved));
  $('review-findings').textContent=(findings.length?'נקודות לבדיקה: '+findings.map(f=>(labels[f.type]||'דורש בדיקה')+(f.source_token?' ('+f.source_token+')':'')).join(' · '):'')+review+
    (details.length?'\n\n'+details.join('\n\n'):'');
}
async function saveEdit(showMessage=true){
  $('save-edit').disabled=true;
  try{currentJob=await request('/document-review',{job_id:currentJob.job_id,unit_index:unitIndex,target_text:$('review-target').value,expected_revision:currentJob.revision});
    renderReview();
    $('result-meta').textContent=qualityLabel()+' · '+currentJob.completed_units+'/'+currentJob.total_units+' מקטעים';
    $('result-exceptions').hidden=false;
    $('result-exceptions').textContent='הגרסה נערכה ידנית. בדיקות המודל שקדמו לעריכה אינן אישור לטקסט החדש; לא נשלחה קריאת מודל נוספת.';
    if(showMessage)$('review-message').textContent='השינויים נשמרו. ההורדה כוללת את הגרסה המעודכנת.';return true;
  }catch(error){$('review-message').textContent=error.message;return false}finally{$('save-edit').disabled=false}
}
async function download(){
  if(dirty()&&!await saveEdit())return;
  $('download-pdf').disabled=true;
  try{const payload={job_id:currentJob.job_id,format:sourceExt()};
    if(sourceExt()==='pdf'&&$('font-after').value)payload.font_id=$('font-after').value;
    const blob=await request('/document-download',payload,true);
    const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=currentJob.filename.replace(/\.[^.]+$/,'')+'.he.'+sourceExt();
    document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
  }catch(error){$('result-notice').hidden=false;$('result-notice').textContent=error.message}finally{$('download-pdf').disabled=false}
}
async function sample(){
  if(busy)return;setBusy(true);message('');
  try{const file=await request('/document-sample');$('model').value='auto';setUploaded(file);setBusy(false);await translate();}
  catch(error){message(error.message);setBusy(false)}
}
function populateFontSelects(){
  const options=pdfFonts.map(f=>`<option value="${f.id}" ${f.available?'':'disabled'}>${f.name}${f.available?'':' (לא זמין)'}</option>`).join('');
  $('font-before').innerHTML=options;$('font-after').innerHTML='<option value="">ללא שינוי</option>'+options;
}
async function initialize(){
  for(const [key,id] of Object.entries({profile:'profile',quality:'quality',language:'language',budget_usd:'budget',model:'model'})){
    $(id).value=preferences[key]??'';if($(id).value===''&&defaults[key]!=null)$(id).value=defaults[key];
    $(id).addEventListener('change',()=>{if(id==='model'&&isReal())$('quality').value='checked';updateSettings();schedulePreview();renderConnection()});
  }
  initRoleUI();
  updateSettings();
  try{const config=await request('/document-config');modelConfigAvailable=config.model_config_available;
    modelCatalog=config.model_catalog||[];pdfFonts=config.pdf_fonts||[];keyProvidersAvailable=config.key_providers_available||{};
    configuredProviders=config.configured_requirements||[];
    if(modelConfigAvailable){const option=document.createElement('option');option.value='server';option.textContent='תצורת המודלים שהוגדרה בשרת';$('model').append(option)}
    populateFontSelects();initRoleUI();renderKeyFields();renderConnection();updateSettings();
  }catch(error){message(error.message)}
  let last;try{last=localStorage.getItem('document-last-job')}catch(_){}
  if(last){setBusy(true);show('processing-panel');currentJob={filename:'המסמך האחרון',status:'queued',stage_label:'',total_units:0,completed_units:0};renderProcessing();await poll(last)}
  else{try{const result=await request('/document-recent');if(result.job){$('recent-button').hidden=false;$('recent-button').textContent='חזרה ל־'+result.job.filename;
    $('recent-button').onclick=()=>{remember('document-last-job',result.job.job_id);setBusy(true);show('processing-panel');poll(result.job.job_id)}}}catch(_){}}
}
$('drop-zone').onclick=()=>{if(!busy)$('document-file').click()};
$('drop-zone').onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();if(!busy)$('document-file').click()}};
$('document-file').onchange=()=>uploadFile($('document-file').files[0]);
for(const kind of ['dragenter','dragover'])$('drop-zone').addEventListener(kind,event=>{event.preventDefault();$('drop-zone').classList.add('dragging')});
for(const kind of ['dragleave','drop'])$('drop-zone').addEventListener(kind,event=>{event.preventDefault();$('drop-zone').classList.remove('dragging');if(kind==='drop')uploadFile(event.dataTransfer.files[0])});
$('translation-form').onsubmit=translate;$('connection-button').onclick=showConnection;
$('close-connection').onclick=()=>$('connection-dialog').close();
$('close-connection-ok').onclick=()=>$('connection-dialog').close();
$('sample-button').onclick=sample;$('download-pdf').onclick=download;$('download-notebook').onclick=downloadNotebook;
$('save-keys').onclick=saveKeys;$('pause-button').onclick=pauseJob;$('resume-button').onclick=resumeJob;
$('resume-save-keys').onclick=saveResumeKeys;
$('font-before').addEventListener('change',schedulePreview);
$('review-button').onclick=()=>{if($('review-panel').hidden){$('review-panel').hidden=false;renderReview();$('review-panel').scrollIntoView({behavior:'smooth',block:'start'})}else if(confirmDiscard())$('review-panel').hidden=true};
$('close-review').onclick=()=>{if(confirmDiscard())$('review-panel').hidden=true};
$('unit-select').onchange=()=>{if(confirmDiscard()){unitIndex=Number($('unit-select').value);renderReview()}else $('unit-select').value=unitIndex};
$('save-edit').onclick=()=>saveEdit();
$('new-document').onclick=()=>{if(!confirmDiscard())return;clearTimeout(pollTimer);forget('document-last-job');currentJob=null;uploaded=null;$('document-file').value='';$('review-panel').hidden=true;show('start-panel');setUploaded(null);setBusy(false);message('');window.scrollTo({top:0,behavior:'smooth'})};
initialize();
