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
  return JSON.stringify([uploaded&&uploaded.path,chosen.use_server_config,chosen.role_selections,chosen.quality,chosen.profile,chosen.budget_usd,chosen.language,chosen.ocr_review]);
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
  for(const id of ['start-panel','processing-panel','result-panel','library-panel'])$(id).hidden=id!==panel;
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
    previewState={fingerprint,valid:!preview.scanned||preview.ocr_ready,
      withinBudget:preview.conservative_total_ceiling_usd<=chosen.budget_usd};
    renderPreview(preview);
    updateSettings();
  }catch(error){if(id!==previewCounter)return;$('preview-card').hidden=false;
    $('preview-body').textContent='אומדן לא זמין: '+error.message}
}
function renderPreview(preview){
  $('preview-card').hidden=false;
  if(preview.scanned){
    const review=preview.vision_review?`בדיקת המודל מול תמונות העמודים: צפוי כ־$${Number(preview.expected_total_cost_usd).toFixed(4)}, תקרה $${Number(preview.conservative_total_ceiling_usd).toFixed(4)}.`:'ללא בדיקת מודל (זיהוי מקומי בלבד, ללא עלות).';
    $('preview-body').innerHTML=`<p><strong>קובץ סרוק:</strong> ${esc(preview.scanned_pages)} מתוך ${esc(preview.total_pages)} עמודים בלי טקסט מוטמע. הטקסט יזוהה ב־OCR במחשב שלכם לפני התרגום.</p>
      ${preview.ocr_ready?'':`<p class="message">${esc(preview.ocr_problem)}</p>`}
      <p>${review}</p>
      <p class="advanced-note">עלות התרגום עצמו תחושב אחרי זיהוי הטקסט, מול אותו תקציב. אם היא תחרוג ממנו, התרגום ייעצר ותתבקשו להחליט אם להעלות את התקציב. בחרו את שפת המקור במפורש: בקובץ סרוק אין טקסט לזיהוי השפה.</p>`;
    return;
  }
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
    font_id:$('font-before').value||null,ocr_review:$('ocr-review').value};
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
  if(currentJob.ocr_progress){
    const ocr=currentJob.ocr_progress;
    detail=(ocr.phase==='vision'?'בדיקת המודל מול תמונות העמודים: ':'זיהוי טקסט בעמודים סרוקים: ')+ocr.done+' מתוך '+ocr.total+' עמודים.';
  } else if(currentJob.progress&&currentJob.progress.total_chapters){
    detail='פרק '+currentJob.progress.completed_chapters+' מתוך '+currentJob.progress.total_chapters+' הושלם. '+
      (currentJob.progress.phase||'')+' · '+currentJob.progress.completed_steps+'/'+currentJob.progress.total_steps+' קריאות.';
  } else if(currentJob.total_units){
    detail=currentJob.completed_units+' מתוך '+currentJob.total_units+' מקטעים הושלמו.';
    if(currentJob.chapter_progress)detail='פרק '+currentJob.chapter_progress.current+' מתוך '+currentJob.chapter_progress.total+'. '+detail;
  } else detail='מחלצים את הטקסט ומכינים את התרגום.';
  const blocker=currentJob.blocker;
  $('processing-detail').textContent=(currentJob.error&&!blocker?currentJob.error+' ':'')+detail+' אפשר לחזור לחלון הזה בהמשך.';
  renderDecision(blocker);
  renderUsage('processing-usage');renderResumeKeyFields();
  if(currentJob.budget_status){
    $('processing-budget').hidden=false;
    $('processing-budget').textContent='הוצאה משוערת: $'+currentJob.budget_status.list_estimated_spent_usd.toFixed(4)+
      ' · שמור/ממתין: $'+currentJob.budget_status.held_usd.toFixed(4)+
      ' · נותר מהתקציב: $'+(currentJob.remaining_budget_usd??0).toFixed(4);
  } else $('processing-budget').hidden=true;
  const canPauseResume=currentJob.settings&&currentJob.settings.automation;
  $('pause-button').hidden=!(canPauseResume&&['translating','reviewing','queued','reading'].includes(currentJob.status));
  $('resume-button').hidden=!(canPauseResume&&!blocker&&['paused','interrupted','failed'].includes(currentJob.status));
  renderRecheck(canPauseResume);
  renderResumeKeyFields();
}
function renderRecheck(automation){
  const count=currentJob.recheck_candidates||0,report=currentJob.recheck_report;
  const idle=automation&&['paused','interrupted','failed'].includes(currentJob.status);
  $('recheck-box').hidden=!(idle&&(count>0||report));
  if(report){
    $('recheck-message').textContent='נקראו מחדש '+report.unit_reviews_recovered+' ביקורות מקטעים ו־'+report.chapter_qa_recovered+
      ' בדיקות פרקים. '+(report.reopened_chapters.length?report.reopened_chapters.length+' פרקים נפתחו מחדש, וכ־'+report.units_to_correct+
      ' מקטעים יקבלו תיקון ובדיקה חוזרת כשהעבודה תמשיך.':'לא נמצאו תיקונים חדשים.')+
      (report.still_needs_human?' '+report.still_needs_human+' תשובות עדיין דורשות בדיקה אנושית.':'');
    $('recheck-button').hidden=true;
  } else {
    $('recheck-message').textContent=count+' תשובות בקורת שמורות סומנו בעבר "דורש בדיקה אנושית" בגלל בדיקה מחמירה מדי של הציטוטים. אפשר לקרוא אותן שוב עם הבדיקה המעודכנת.';
    $('recheck-button').hidden=false;
  }
}
async function recheckReviews(){
  $('recheck-error').hidden=true;$('recheck-button').disabled=true;
  try{const result=await request('/document-recheck-reviews',{job_id:currentJob.job_id});
    currentJob={...result,settings:result.settings||currentJob.settings};renderProcessing();
  }catch(error){$('recheck-error').textContent=error.message;$('recheck-error').hidden=false}
  finally{$('recheck-button').disabled=false}
}
function renderDecision(blocker){
  const box=$('decision-box'),options=$('decision-options');
  const waiting=blocker&&['paused','interrupted','failed'].includes(currentJob.status);
  box.hidden=!waiting;if(!waiting){options.replaceChildren();return}
  if(box.dataset.rendered===JSON.stringify(blocker))return;
  box.dataset.rendered=JSON.stringify(blocker);
  $('decision-message').textContent=blocker.message;$('decision-error').hidden=true;
  options.replaceChildren();
  blocker.options.forEach((option,index)=>{
    const row=document.createElement('div');row.className='decision-option';
    if(option.input==='usd'){
      row.innerHTML=`<label for="decision-input-${index}">${esc(option.label)}</label><input id="decision-input-${index}" type="number" min="0" step="0.01" inputmode="decimal" dir="ltr">
        <button type="button" class="secondary-button">אישור והמשך</button>`;
      row.querySelector('button').onclick=()=>decide(option,Number(row.querySelector('input').value),row.querySelector('button'));
    } else {
      row.innerHTML=`<button type="button" class="${index===0?'primary-button':'secondary-button'}">${esc(option.label)}</button>`;
      row.querySelector('button').onclick=()=>decide(option,null,row.querySelector('button'));
    }
    options.append(row);
  });
}
async function decide(option,value,button){
  if(option.input==='usd'&&!(value>0)){$('decision-error').textContent='הזינו סכום בדולרים.';$('decision-error').hidden=false;return}
  $('decision-error').hidden=true;
  for(const control of $('decision-options').querySelectorAll('button,input'))control.disabled=true;
  try{const result=await request('/document-decide',{job_id:currentJob.job_id,option:option.id,value:option.input?value:null});
    currentJob={...result,settings:result.settings||currentJob.settings};delete $('decision-box').dataset.rendered;
    renderProcessing();
    if(!currentJob.blocker)await resumeJob();
  }catch(error){$('decision-error').textContent=error.message;$('decision-error').hidden=false;
    for(const control of $('decision-options').querySelectorAll('button,input'))control.disabled=false}
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
  try{const result=await request('/document-job',{job_id:jobId});if(!$('library-panel').hidden)return;currentJob={...result,settings:result.settings||currentJob?.settings};
    if(['queued','reading','translating','reviewing','rebuilding'].includes(result.status)){show('processing-panel');renderProcessing();pollTimer=setTimeout(()=>poll(jobId),1400)}
    else if(['paused','interrupted','failed'].includes(result.status)&&result.settings?.automation){show('processing-panel');renderProcessing()}
    else{setBusy(false);show('result-panel');renderResult();window.scrollTo({top:0,behavior:'smooth'})}
  }catch(error){if(!$('library-panel').hidden)return;if(error.status===400){forget('document-last-job');currentJob=null;setBusy(false);show('start-panel');message(error.message);return}
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
// ---- library: all completed translations ----
let libraryReturn='start-panel',libraryCounter=0;
function visiblePanel(){return ['start-panel','processing-panel','result-panel','library-panel'].find(id=>!$(id).hidden)||'start-panel'}
function libraryDate(seconds){
  const date=new Date(Number(seconds)*1000);if(!Number.isFinite(date.getTime()))return'';
  try{return date.toLocaleString('he-IL',{dateStyle:'medium',timeStyle:'short'})}catch(_){return date.toLocaleString()}
}
function libraryStem(filename){return String(filename||'document').replace(/\.[^.]+$/,'')}
function libraryFontOptions(selected){
  const fonts=pdfFonts.filter(f=>f.available);
  const chosen=fonts.some(f=>f.id===selected)?selected:'';
  return '<option value="">גופן ברירת המחדל</option>'+fonts.map(f=>`<option value="${esc(f.id)}"${f.id===chosen?' selected':''}>${esc(f.name)}</option>`).join('');
}
function renderLibrary(documents){
  const list=$('library-list');list.replaceChildren();
  $('library-empty').hidden=documents.length>0;
  documents.forEach((doc,index)=>{
    const kind=doc.source_kind==='epub'?'epub':'pdf',detailId='library-detail-'+index;
    const item=document.createElement('li');item.className='library-item';item.dataset.jobId=doc.job_id;
    const fontField=kind==='pdf'?`<div class="field library-font"><label for="library-font-${index}">גופן להורדה</label><select id="library-font-${index}" class="library-font-select">${libraryFontOptions(doc.font_id)}</select></div>`:'';
    item.innerHTML=`<button type="button" class="library-entry" aria-expanded="false" aria-controls="${detailId}">
      <span class="library-kind" data-kind="${kind}">${kind.toUpperCase()}</span>
      <span class="library-entry-text"><strong dir="auto">${esc(doc.filename)}</strong><span class="library-meta">${esc(libraryDate(doc.completed_at))}${doc.unit_count!=null?' · '+esc(doc.unit_count)+' מקטעים':''}</span></span>
      <span class="chevron" aria-hidden="true">⌄</span></button>
      <div id="${detailId}" class="library-detail" hidden>${fontField}
      <div class="library-actions"><button type="button" class="primary-button library-download" data-format="${kind}">הורדת ${kind.toUpperCase()} <span aria-hidden="true">↓</span></button>
      <button type="button" class="secondary-button library-download" data-format="html">הורדת HTML <span aria-hidden="true">↓</span></button>
      <button type="button" class="text-button library-open">פתיחה <span aria-hidden="true">←</span></button>
      <button type="button" class="text-button library-delete">מחיקה</button></div>
      <p class="message library-error" role="alert" hidden></p></div>`;
    const entry=item.querySelector('.library-entry'),detail=item.querySelector('.library-detail');
    entry.onclick=()=>{const open=entry.getAttribute('aria-expanded')!=='true';entry.setAttribute('aria-expanded',String(open));detail.hidden=!open;item.classList.toggle('open',open)};
    item.querySelectorAll('.library-download').forEach(button=>button.onclick=()=>libraryDownload(doc,button,item));
    item.querySelector('.library-open').onclick=()=>libraryOpen(doc);
    item.querySelector('.library-delete').onclick=()=>libraryDelete(doc,item,false);
    list.append(item);
  });
}
const IN_PROGRESS_STATUS={failed:'נעצר',paused:'מושהה',interrupted:'הופסק',queued:'ממתין',reading:'קורא',translating:'מתרגם כעת',reviewing:'בבדיקה',rebuilding:'בונה את הקובץ'};
function renderInProgress(documents){
  const list=$('library-list');list.replaceChildren();
  $('library-empty').hidden=documents.length>0;
  documents.forEach((doc,index)=>{
    const kind=doc.source_kind==='epub'?'epub':'pdf',detailId='library-detail-'+index;
    const item=document.createElement('li');item.className='library-item in-progress';item.dataset.jobId=doc.job_id;
    const parts=[IN_PROGRESS_STATUS[doc.status]||doc.status];
    if(doc.total_chapters)parts.push('פרק '+doc.completed_chapters+' מתוך '+doc.total_chapters);
    parts.push(doc.translated_units+' מתוך '+doc.total_units+' מקטעים');
    if(doc.spent_usd!=null)parts.push('$'+Number(doc.spent_usd).toFixed(4)+(doc.budget_usd?' מתוך $'+Number(doc.budget_usd).toFixed(2):''));
    const notice=doc.blocker?`<p class="library-blocker">${esc(doc.blocker.message)}</p>`:(doc.error?`<p class="library-blocker">${esc(doc.error)}</p>`:'');
    const fontField=kind==='pdf'&&doc.formats.length?`<div class="field library-font"><label for="library-font-${index}">גופן להורדה</label><select id="library-font-${index}" class="library-font-select">${libraryFontOptions(null)}</select></div>`:'';
    const downloads=doc.formats.length?`<button type="button" class="secondary-button library-download" data-format="${kind}" data-partial="1">הורדה חלקית ${kind.toUpperCase()} <span aria-hidden="true">↓</span></button>
      <button type="button" class="secondary-button library-download" data-format="html" data-partial="1">HTML חלקי <span aria-hidden="true">↓</span></button>`:'';
    item.innerHTML=`<button type="button" class="library-entry" aria-expanded="false" aria-controls="${detailId}">
      <span class="library-kind" data-kind="${kind}">${kind.toUpperCase()}</span>
      <span class="library-entry-text"><strong dir="auto">${esc(doc.filename)}</strong><span class="library-meta">${esc(libraryDate(doc.updated_at))} · ${esc(parts.join(' · '))}</span>${doc.blocker?'<span class="library-flag">נדרשת החלטה</span>':''}</span>
      <span class="chevron" aria-hidden="true">⌄</span></button>
      <div id="${detailId}" class="library-detail" hidden>${notice}${fontField}
      <div class="library-actions"><button type="button" class="primary-button library-open">${doc.blocker?'פתיחה והחלטה':'פתיחה והמשך'} <span aria-hidden="true">←</span></button>${downloads}
      <button type="button" class="text-button library-delete">מחיקה</button></div>
      ${doc.formats.length?'<p class="library-partial-note">בהורדה חלקית, מה שעדיין לא תורגם נשאר בשפת המקור.</p>':''}
      <p class="message library-error" role="alert" hidden></p></div>`;
    const entry=item.querySelector('.library-entry'),detail=item.querySelector('.library-detail');
    entry.onclick=()=>{const open=entry.getAttribute('aria-expanded')!=='true';entry.setAttribute('aria-expanded',String(open));detail.hidden=!open;item.classList.toggle('open',open)};
    item.querySelectorAll('.library-download').forEach(button=>button.onclick=()=>libraryDownload(doc,button,item));
    item.querySelector('.library-open').onclick=()=>libraryOpen(doc);
    item.querySelector('.library-delete').onclick=()=>libraryDelete(doc,item,true);
    list.append(item);
  });
}
async function libraryDelete(doc,item,inProgress){
  const spent=inProgress&&doc.spent_usd?' העבודה שכבר שולמה ($'+Number(doc.spent_usd).toFixed(4)+') תאבד.':'';
  if(!confirm('למחוק לצמיתות את "'+doc.filename+'"? יימחקו התרגום, ההעתק של קובץ המקור, מחברת הספר ויומן העלויות שלו.'+spent+' אי אפשר לבטל את המחיקה.'))return;
  const error=item.querySelector('.library-error');error.hidden=true;
  item.querySelectorAll('button,select').forEach(control=>control.disabled=true);
  try{await request('/document-delete',{job_id:doc.job_id,confirm:true});
    try{if(localStorage.getItem('document-last-job')===doc.job_id)forget('document-last-job')}catch(_){}
    if(currentJob?.job_id===doc.job_id)currentJob=null;
    loadLibrary();
  }catch(caught){error.textContent=caught.message;error.hidden=false;item.querySelectorAll('button,select').forEach(control=>control.disabled=false)}
}
let libraryTab='done';
function setLibraryTab(tab){
  libraryTab=tab;
  $('library-tab-done').setAttribute('aria-selected',String(tab==='done'));
  $('library-tab-progress').setAttribute('aria-selected',String(tab==='progress'));
  $('library-intro').textContent=tab==='done'?'כל המסמכים שתרגומם הושלם ונשמר במחשב שלכם. לחצו על מסמך כדי להוריד אותו.':
    'תרגומים שעדיין לא הושלמו: אפשר להמשיך אותם, להחליט מה לעשות כשהם נעצרו, ולהוריד את מה שכבר תורגם.';
  $('library-empty').textContent=tab==='done'?'עדיין אין בספרייה תרגומים שהושלמו. מסמך שתרגומו יושלם יופיע כאן.':'אין כרגע תרגומים בתהליך עבודה.';
  loadLibrary();
}
async function loadLibrary(){
  const id=++libraryCounter,tab=libraryTab;
  $('library-message').hidden=true;$('library-empty').hidden=true;$('library-list').replaceChildren();
  $('library-status').textContent='טוען את הספרייה…';
  try{const result=await request(tab==='done'?'/document-library':'/document-in-progress',{});if(id!==libraryCounter)return;
    $('library-status').textContent='';const documents=Array.isArray(result.documents)?result.documents:[];
    (tab==='done'?renderLibrary:renderInProgress)(documents);
  }catch(error){if(id!==libraryCounter)return;$('library-status').textContent='';$('library-message').textContent=error.message;$('library-message').hidden=false}
}
function openLibrary(){
  const current=visiblePanel();
  if(current==='library-panel'){loadLibrary();return}
  if(current==='result-panel'&&!confirmDiscard())return;
  libraryReturn=current;clearTimeout(pollTimer);
  show('library-panel');window.scrollTo({top:0,behavior:'auto'});$('library-title').focus?.();loadLibrary();
}
function closeLibrary(){
  if(libraryReturn==='processing-panel'&&currentJob?.job_id){show('processing-panel');poll(currentJob.job_id);return}
  if(libraryReturn==='result-panel'&&currentJob){show('result-panel');return}
  show('start-panel');
}
async function libraryDownload(doc,button,item){
  const format=button.dataset.format,error=item.querySelector('.library-error'),select=item.querySelector('.library-font-select');
  error.hidden=true;button.disabled=true;
  try{const payload={job_id:doc.job_id,format},partial=button.dataset.partial==='1';
    if(partial)payload.partial=true;
    if(format!=='epub'&&select&&select.value)payload.font_id=select.value;
    const blob=await request('/document-download',payload,true);
    const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=libraryStem(doc.filename)+(partial?'.he.partial.':'.he.')+format;
    document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
  }catch(caught){error.textContent=caught.message;error.hidden=false}finally{button.disabled=false}
}
function libraryOpen(doc){
  clearTimeout(pollTimer);remember('document-last-job',doc.job_id);
  currentJob={job_id:doc.job_id,filename:doc.filename,status:'queued',stage_label:'',total_units:0,completed_units:0};
  $('review-panel').hidden=true;setBusy(true);show('processing-panel');renderProcessing();poll(doc.job_id);
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
$('save-keys').onclick=saveKeys;$('pause-button').onclick=pauseJob;$('resume-button').onclick=resumeJob;$('recheck-button').onclick=recheckReviews;
$('resume-save-keys').onclick=saveResumeKeys;
$('library-button').onclick=openLibrary;$('library-start-button').onclick=openLibrary;$('library-back').onclick=closeLibrary;
$('library-tab-done').onclick=()=>setLibraryTab('done');$('library-tab-progress').onclick=()=>setLibraryTab('progress');
$('font-before').addEventListener('change',schedulePreview);
$('ocr-review').addEventListener('change',schedulePreview);
$('review-button').onclick=()=>{if($('review-panel').hidden){$('review-panel').hidden=false;renderReview();$('review-panel').scrollIntoView({behavior:'smooth',block:'start'})}else if(confirmDiscard())$('review-panel').hidden=true};
$('close-review').onclick=()=>{if(confirmDiscard())$('review-panel').hidden=true};
$('unit-select').onchange=()=>{if(confirmDiscard()){unitIndex=Number($('unit-select').value);renderReview()}else $('unit-select').value=unitIndex};
$('save-edit').onclick=()=>saveEdit();
$('new-document').onclick=()=>{if(!confirmDiscard())return;clearTimeout(pollTimer);forget('document-last-job');currentJob=null;uploaded=null;$('document-file').value='';$('review-panel').hidden=true;show('start-panel');setUploaded(null);setBusy(false);message('');window.scrollTo({top:0,behavior:'smooth'})};
initialize();
