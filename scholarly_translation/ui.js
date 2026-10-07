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
// ---- interface language (he default / en) ----
let LANG='he';
try{if(localStorage.getItem('ui-language')==='en')LANG='en'}catch(_){}
const t=(he,en)=>LANG==='en'?en:he;
let previewView=null,manualEdit=false,resultError='',reviewSaved=false,libraryData=null,recentName=null;
/*I18N-BEGIN*/
const EN={ "brandAria": "Document translation — home", "brand": "Document translation", "help": "Help", "learning": "Language learning", "library": "Library", "heroEyebrow": "PDF / EPUB · to Hebrew", "heroTitle": "Your document, <span>in Hebrew.</span>", "heroText": "Upload a PDF or EPUB, choose how to translate it, and download it translated in the same format.<br class=\"desktop-break\"> You can review and edit it — if you want.", "fileAria": "Choose a PDF or EPUB", "dropAria": "Choose a PDF or EPUB file, or drag it here", "dropTitle": "Choose a file or drag it here", "chooseFile": "Choose a file <span aria-hidden=\"true\">→</span>", "uploadNote": "PDF with embedded text, or EPUB · up to 25 MB", "changeFile": "Change", "optionsLabel": "Options <span class=\"chevron\" aria-hidden=\"true\">⌄</span>", "lblProfile": "Translation profile", "optScholarly": "Academic (precise; notes and terminology preserved)", "optLiterary": "Literary (fluent, faithful to style)", "lblQuality": "Review level", "optFast": "Fast — no extra review", "optChecked": "Checked — risky segments + chapter review", "optThorough": "In-depth — every segment + chapter review", "lblModel": "Model", "optAuto": "Auto — trial preview (simulated), no cost and no real translation", "optConfigured": "My own model (API key)", "lblLanguage": "Source language", "optLangAuto": "Detect automatically", "optEn": "English", "optFr": "French", "optJa": "Japanese", "lblBudget": "Maximum budget per document ($)", "phBudget": "e.g. 5", "noteBudget": "Required with my own model: there is no built-in cap; your limit is enforced as a hard stop.", "lblOcr": "Scanned books (OCR)", "optOcrVision": "Local recognition + model check against the page image", "optOcrOff": "Local recognition only (free)", "noteOcr": "Pages without embedded text are recognized with Tesseract on your computer. The model check compares each page with its image and fixes mistakes and formulas; it needs a model that reads images.", "lblFontBefore": "PDF font (before translation)", "noteFontBefore": "Relevant to PDF files only; an EPUB keeps its original design.", "noteKeys": "My own model: keys are kept only in the local server's memory for this run — not on disk, in the settings file or in the browser. Restarting the server clears them.", "roleTranslator": "Translator", "roleQa": "Quality review (QA) <small>— same as the translator by default</small>", "advRoles": "Advanced chapter reviewer selection (chapter_qa)", "saveKeys": "Save API keys", "previewTitle": "Cost estimate (before anything is sent)", "sampleBtn": "Try a sample PDF, free", "libraryStart": "Library: all finished translations <span aria-hidden=\"true\">→</span>", "formatNote": "We translate the document structure (paragraphs, headings). A PDF is rebuilt and does not reproduce the original layout; an EPUB keeps its original chapter structure and design.", "procEyebrow": "Your document is on its way to Hebrew", "progressAria": "Translation progress", "noteResumeKeys": "The server was restarted and lost the temporary API keys held in memory. Enter them again to continue.", "decisionTitle": "A decision from you is needed to continue", "decisionNote": "The decision is recorded in the cost log. No call is sent to the provider until the work continues.", "recheckTitle": "Saved review answers that were not used", "recheckBtn": "Re-check them (no provider call)", "recheckNote": "The check re-reads the saved answers. Chapters with substantive findings are reopened, and the fixes themselves are sent to the provider only when the work continues.", "crossTitle": "Cross-chapter review of the book", "crossText": "First a name table is built: the model reads the original book, passage by passage, and collects invented names, titles and terms; in a scholarly book also thinkers and authors, cited works and key terms (vowel marks allowed); the table is locked. Then the review compares the source with the translation in windows of 8 chapters with one overlapping chapter (1–8, 8–15, 15–22 …); the overlapping chapter, which has already been reviewed, is the authority. Inconsistent names, terms, references and continuity are corrected automatically and re-checked, and the previous Hebrew text is kept.", "crossNote": "Paid provider calls start only when you click Resume. A re-run re-sends only text that changed.", "crossDone": "The review was prepared. Click Resume to run it.", "pauseBtn": "Pause", "resumeBtn": "Resume", "draftBadge": "Draft", "detailsSummary": "Details about the review and the file", "nbTitle": "Book notebook (optional)", "nbText": "During translation the model records names, terms and translation choices to keep them consistent. You don't need to do anything; you can download it for reference.", "nbDownload": "Download the notebook (Markdown) <span aria-hidden=\"true\">↓</span>", "lblFontAfter": "PDF font (after translation)", "noteFontAfter": "Changing the font rebuilds the PDF only; it sends no call to the model.", "downloadBtn": "Download the translated file <span aria-hidden=\"true\">↓</span>", "reviewBtn": "Review and edit (optional) <span aria-hidden=\"true\">→</span>", "reviewTitle": "Source beside translation", "unitAria": "Choose a segment to review", "closeReviewAria": "Close the review", "srcHead": "Source", "tgtHead": "Translation · editable", "editAria": "Edit the translation", "saveEditBtn": "Save changes", "reviewNote": "Saving updates the downloadable file.", "newDoc": "← Translate another document", "draftNote": "An automatic draft; you can download it right away, or review it first.", "libTitle": "Your translations", "libTabsAria": "Type of documents in the library", "tabDone": "Ready", "tabProgress": "In progress", "back": "← Back", "footerNote": "The file and the result are stored on your computer.", "consentTitle": "Approve sending to providers", "consentText": "The translation and the checks share one budget per document. This is a local estimate limit based on the price list, not a billing limit on the provider account.", "consentOk": "Approve and start translating", "cancel": "Cancel", "connTitle": "Translation model", "closeAria": "Close", "close": "Close", "roleChoose": "Choose a model…", "roleOther": "Other (custom model/provider)…", "roleCompat": "OpenAI-compatible (custom address)", "phModelId": "Model ID", "phBaseUrl": "https://… (OpenAI-compatible only)", "phContext": "Context window (tokens)", "phMaxOut": "Output cap (up to 128,000 tokens)", "phUsable": "Usable window (optional)", "phRateIn": "Input rate ($/1M, optional)", "phRateOut": "Output rate ($/1M, optional)", "phRateCached": "Cache read ($/1M, optional)", "phRateWrite": "Short cache write ($/1M, optional)", "phRateWrite1h": "Hourly cache write ($/1M, optional)", "roleRateNote": "If no rate is entered, a conservative assumption marked \"unofficial\" is used for estimation only." };
const STAGE_EN={"קריאת המסמך": "Reading the document", "מתרגם": "Translating", "בניית המסמך המתורגם": "Building the translated document", "הושלם": "Completed", "מושהה — התוצאות נשמרו": "Paused — results saved", "זיהוי טקסט (OCR) בעמודים סרוקים": "Recognizing text (OCR) on scanned pages", "בדיקת ה־OCR בעזרת המודל": "Checking the OCR with the model", "בבדיקה": "Reviewing", "בבדיקת פרקים": "Reviewing chapters", "ממתין לבדיקה רוחבית": "Waiting for the cross-chapter review", "הופסק": "Stopped", "בניית טבלת השמות של הספר": "Building the book's name table", "תרגום פרק / קבוצת יחידות": "Translating a chapter / group of units", "ביקורת מקטעים ו־QA פרקי": "Segment review and chapter QA"};
const IN_PROGRESS_EN={"failed": "Stopped", "paused": "Paused", "interrupted": "Interrupted", "queued": "Waiting", "reading": "Reading", "translating": "Translating now", "reviewing": "Reviewing", "rebuilding": "Building the file"};
const LIMITATION_EN={"missing_translation": "Segments left in the source language", "inline_markup_flattened": "Inline formatting (emphasis/links) simplified", "units_merged_multiple_blocks": "Segments merged from several paragraphs"};
/*I18N-END*/
function stageLabel(label){
  if(LANG!=='en'||!label)return label;
  if(STAGE_EN[label])return STAGE_EN[label];
  const m=/^בדיקה רוחבית של פרקים (\d+)–(\d+)$/.exec(label);
  return m?'Cross-chapter review of chapters '+m[1]+'–'+m[2]:label;
}
async function request(route,data={},binary=false){
  const response=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json','X-UI-Token':token},body:JSON.stringify(data)});
  if(!response.ok){let result;try{result=await response.json()}catch(_){throw Error(t('לא ניתן להתחבר לשרת המקומי. הפעילו אותו שוב.',"Cannot reach the local server. Start it again."))}
    const error=Error(result.error||t('הפעולה לא הושלמה',"The action did not complete"));error.status=response.status;throw error}
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
function catalogLabel(m){return m.provider+'/'+m.model+' ($'+m.rates_per_million.input+'/'+m.rates_per_million.output+' '+t('ל-1M','per 1M')+')'}
function catalogOptionsHtml(provider){
  return modelCatalog.filter(m=>provider?m.provider===provider:true)
    .map(m=>`<option value="${m.provider}:${m.model}" data-cat="1">${catalogLabel(m)}</option>`).join('');
}
function roleFieldsHtml(role){
  return `<select class="role-select" data-role="${role}"><option value="" data-i18n="roleChoose">בחרו מודל…</option>${catalogOptionsHtml()}<option value="other" data-i18n="roleOther">אחר (מודל/ספק מותאם)…</option></select>
  <div class="other-fields" data-role="${role}">
    <select class="other-provider-type" data-role="${role}"><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option><option value="openai_compatible" data-i18n="roleCompat">תואם-OpenAI (כתובת מותאמת)</option></select>
    <input class="other-model" data-role="${role}" placeholder="מזהה מודל" data-i18n-ph="phModelId" dir="ltr">
    <input class="other-base-url" data-role="${role}" placeholder="https://… (רק לתואם-OpenAI)" data-i18n-ph="phBaseUrl" dir="ltr">
    <input class="other-context" data-role="${role}" type="number" min="1" placeholder="חלון הקשר (טוקנים)" data-i18n-ph="phContext" dir="ltr">
    <input class="other-max-output" data-role="${role}" type="number" min="1" max="128000" placeholder="תקרת פלט (עד 128,000 טוקנים)" data-i18n-ph="phMaxOut" dir="ltr">
    <input class="other-usable" data-role="${role}" type="number" min="1" placeholder="חלון שימוש (רשות)" data-i18n-ph="phUsable" dir="ltr">
    <input class="other-rate-input" data-role="${role}" type="number" min="0" step="0.01" placeholder="תעריף קלט ($/1M, רשות)" data-i18n-ph="phRateIn" dir="ltr">
    <input class="other-rate-output" data-role="${role}" type="number" min="0" step="0.01" placeholder="תעריף פלט ($/1M, רשות)" data-i18n-ph="phRateOut" dir="ltr">
    <input class="other-rate-cached" data-role="${role}" type="number" min="0" step="0.01" placeholder="קריאת מטמון ($/1M, רשות)" data-i18n-ph="phRateCached" dir="ltr">
    <input class="other-rate-write" data-role="${role}" type="number" min="0" step="0.01" placeholder="כתיבת מטמון קצר ($/1M, רשות)" data-i18n-ph="phRateWrite" dir="ltr">
    <input class="other-rate-write1h" data-role="${role}" type="number" min="0" step="0.01" placeholder="כתיבת מטמון שעה ($/1M, רשות)" data-i18n-ph="phRateWrite1h" dir="ltr">
    <p class="advanced-note" data-i18n="roleRateNote">אם לא תוזן תעריף, תשמש הנחה שמרנית ומסומנת "אינה רשמית" לצורך אומדן בלבד.</p>
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
  if(LANG==='en')applyStatic();
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
  container.innerHTML=ids.map(pid=>`<div><label for="key-${esc(pid)}">${t('מפתח API — ','API key — ')}${esc(pid)}${keyProvidersAvailable[pid]?t(' (זמין)',' (available)'):''}</label>
    <small dir="ltr">${esc(resolvedProviders.find(p=>p.id===pid)?.endpoint||t('הספק הרשמי','the official provider'))}</small>
    <input id="key-${esc(pid)}" class="key-input" type="password" data-provider="${esc(pid)}" autocomplete="off"></div>`).join('');
}
async function saveKeys(){
  const inputs=[...document.querySelectorAll('.key-input')];
  const keys={};for(const input of inputs)if(input.value)keys[input.dataset.provider]=input.value;
  $('key-message').textContent=t('שומר…',"Saving…");
  try{const result=await request('/model-keys',{keys});keyProvidersAvailable=result.available;
    $('key-message').textContent=t('המפתחות נשמרו בזיכרון השרת להרצה הנוכחית.',"Keys saved in the local server's memory for the current run.");renderKeyFields();updateSettings();
  }catch(error){$('key-message').textContent=error.message}
  finally{for(const input of inputs)input.value=''}
}
function missingKeyProviders(){return requiredProviderIds().filter(pid=>!keyProvidersAvailable[pid])}
function renderResumeKeyFields(){
  const container=$('resume-key-fields');if(!container)return;
  const required=requiredProviderIdsForJobSettings(currentJob&&currentJob.settings);
  const missing=required.filter(pid=>!keyProvidersAvailable[pid]);
  $('resume-keys').hidden=!missing.length;
  container.innerHTML=missing.map(pid=>`<div><label for="resume-key-${pid}">${t('מפתח API — ','API key — ')}${esc(pid)}</label>
    <input id="resume-key-${pid}" class="resume-key-input" type="password" data-provider="${esc(pid)}" autocomplete="off"></div>`).join('');
}
async function saveResumeKeys(){
  const inputs=[...document.querySelectorAll('.resume-key-input')];
  const keys={};for(const input of inputs)if(input.value)keys[input.dataset.provider]=input.value;
  $('resume-key-message').textContent=t('שומר…',"Saving…");
  try{const result=await request('/model-keys',{keys});keyProvidersAvailable=result.available;
    $('resume-key-message').textContent=t('המפתחות נשמרו. אפשר להמשיך.',"Keys saved. You can continue.");renderResumeKeyFields();
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
    previewView=()=>{$('preview-body').textContent=t('יש להגדיר תקציב מרבי למסמך (מספר חיובי) כדי לקבל אומדן.','A maximum budget per document (a positive number) is required to get an estimate.')};previewView();$('translation-options').open=true;$('budget').focus();return}
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
    const detail=error.message;previewView=()=>{$('preview-body').textContent=t('אומדן לא זמין: ','Estimate unavailable: ')+detail};previewView()}
}
function renderPreview(preview){
  previewView=()=>renderPreview(preview);
  $('preview-card').hidden=false;
  if(preview.scanned){
    const review=preview.vision_review?t(`בדיקת המודל מול תמונות העמודים: צפוי כ־$${Number(preview.expected_total_cost_usd).toFixed(4)}, תקרה $${Number(preview.conservative_total_ceiling_usd).toFixed(4)}.`,`Model check against page images: expected about $${Number(preview.expected_total_cost_usd).toFixed(4)}, ceiling $${Number(preview.conservative_total_ceiling_usd).toFixed(4)}.`):t('ללא בדיקת מודל (זיהוי מקומי בלבד, ללא עלות).',"No model check (local recognition only, free).");
    $('preview-body').innerHTML=`<p>${t(`<strong>קובץ סרוק:</strong> `,`<strong>Scanned file:</strong> `)}${esc(preview.scanned_pages)}${t(` מתוך ${esc(preview.total_pages)} עמודים בלי טקסט מוטמע. הטקסט יזוהה ב־OCR במחשב שלכם לפני התרגום.`,` of ${esc(preview.total_pages)} pages have no embedded text. The text will be recognized with OCR on your computer before translation.`)}</p>
      ${preview.ocr_ready?'':`<p class="message">${esc(preview.ocr_problem)}</p>`}
      <p>${review}</p>
      <p class="advanced-note">${t(`עלות התרגום עצמו תחושב אחרי זיהוי הטקסט, מול אותו תקציב. אם היא תחרוג ממנו, התרגום ייעצר ותתבקשו להחליט אם להעלות את התקציב. בחרו את שפת המקור במפורש: בקובץ סרוק אין טקסט לזיהוי השפה.`,`The cost of the translation itself is computed after the text is recognized, against the same budget. If it exceeds it, translation stops and you will be asked whether to raise the budget. Choose the source language explicitly: a scanned file has no text from which to detect the language.`)}</p>`;
    return;
  }
  const rows=[];
  for(const chapter of preview.chapters){
    for(const [role,usage] of Object.entries(chapter.role_usage)){
      rows.push(`<tr><td>${esc(role==='notebook_keeper'?t('מחברת הספר',"Book notebook"):role)}</td><td dir="ltr">${esc(usage.provider)}/${esc(usage.model)}</td><td dir="ltr">${esc(usage.calls)}</td>
        <td dir="ltr">${esc(usage.input_tokens_upper_bound)} / ${esc(usage.output_tokens_upper_bound)}<br>${esc(usage.count_method)} · ${usage.exact?t('ספירה לפי קידוד',"counted by encoding"):t('אומדן',"estimate")}</td>
        <td dir="ltr">$${Number(usage.expected_cost_usd).toFixed(4)}</td><td dir="ltr">$${Number(usage.conservative_cost_usd).toFixed(4)}</td>
        <td>${usage.pricing_basis==='unknown_conservative'?t('הנחה שמרנית (לא רשמי)',"Conservative assumption (unofficial)"):esc(usage.pricing_basis)}</td></tr>`);
    }
  }
  $('preview-body').innerHTML=`<div class="table-scroll"><table><thead><tr>${t(`<th>תפקיד</th><th>מודל</th><th>קריאות מרביות</th><th>טוקנים קלט / פלט — גבול תכנון</th><th>צפוי</th><th>תקרה לפי ההנחות</th><th>בסיס תמחור</th>`,`<th>Role</th><th>Model</th><th>Max calls</th><th>Input / output tokens — planning bound</th><th>Expected</th><th>Ceiling under the assumptions</th><th>Pricing basis</th>`)}</tr></thead>
    <tbody>${rows.join('')}</tbody></table></div>
    <p>${t(`סה״כ צפוי: `,`Expected total: `)}$${Number(preview.expected_total_cost_usd).toFixed(4)}${t(` · תקרה שמרנית: `,` · Conservative ceiling: `)}$${Number(preview.conservative_total_ceiling_usd).toFixed(4)}
    (${esc(preview.chapter_count)}${t(` פרקים) · קטלוג: `,` chapters) · Catalog: `)}${esc(preview.catalog_version||'')}</p>
    <p class="advanced-note">${t(`האומדן "צפוי" מניח כ-35% ניצול תקרת הפלט, ללא תיקונים וללא הנחת פגיעה במטמון; התקרה לפי ההנחות כוללת תיקון מקומי אחד ובדיקה חוזרת וכתיבת מטמון מלאה. למודל אחר ללא תעריף משתמשים בהנחת $4 קלט / $20 פלט למיליון; זו אינה התחייבות או תקרת חיוב של הספק.`,`The "expected" estimate assumes about 35% use of the output cap, with no corrections and no cache hits; the ceiling under the assumptions includes one local correction, one re-check and a full cache write. For another model with no rate, an assumption of $4 input / $20 output per million is used; this is not a commitment or a provider billing cap.`)}</p>`;
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
  $('translate-label').textContent=auto?t('פתיחת תצוגת ניסיון',"Open trial preview"):busy?t('מעלה קובץ…',"Uploading file…"):t('תרגום לעברית',"Translate to Hebrew");
  const missing=auto?[]:missingKeyProviders();
  const previewReady=auto||(previewState.valid&&previewState.fingerprint===previewFingerprint(chosen)&&previewState.withinBudget);
  $('translate-button').disabled=!uploaded||busy||(!auto&&((!chosen.role_selections&&!isServer())||missing.length>0||!previewReady));
  $('send-note').textContent=auto?t('ללא עלות וללא תרגום אמיתי. יוצג טקסט מקום-שמור בלבד.',"No cost and no real translation. Placeholder text only."):
    missing.length?t('יש לשמור מפתח API עבור: ',"Save an API key for: ")+missing.join(', ')+t(' לפני התרגום.'," before translating."):
    !chosen.role_selections&&!isServer()?t('בחרו מודל מתרגם לפני התרגום.',"Choose a translator model before translating."):
    !previewState.valid||previewState.fingerprint!==previewFingerprint(chosen)?t('ממתינים לאומדן עדכני לפני התרגום.',"Waiting for an up-to-date estimate before translating."):
    !previewState.withinBudget?t('האומדן השמרני חורג מהתקציב שנבחר; הגדילו תקציב או שנו הגדרות.',"The conservative estimate exceeds the chosen budget; raise the budget or change the settings."):
    t('לחיצה על תרגום תבקש אישור לשליחת הטקסט לספקים שנבחרו.',"Clicking Translate will ask you to approve sending the text to the chosen providers.");
  $('budget').disabled=auto;
  $('model-help').textContent=auto?t('Auto הוא תצוגת ניסיון ללא עלות וללא תרגום אמיתי.',"Auto is a trial preview with no cost and no real translation."):
    isServer()?t('משתמש בתצורת המודלים המקומית של השרת.',"Uses the server's local model configuration."):t('בחרו מודל לתרגום ול־QA והזינו מפתחות API לספקים שנבחרו.',"Choose a model for translation and QA and enter API keys for the chosen providers.");
  $('quality-help').textContent=auto?t('Auto תמיד מריץ ברמה מהירה (ללא בדיקה נוספת), ללא קשר לבחירה כאן.',"Auto always runs at the fast level (no extra review), regardless of the choice here."):
    chosen.quality==='fast'?t('ללא קריאות בדיקה נוספות; המהיר והחסכוני ביותר.',"No extra review calls; the fastest and cheapest."):
    chosen.quality==='checked'?t('בדיקת מקטעים שסומנו כמסוכנים, ובדיקת פרקים בסוף כל פרק.',"Review of segments flagged as risky, and a chapter review at the end of each chapter."):
    t('בדיקת כל מקטע ובדיקת פרקים; המקיף והיקר ביותר.',"Review of every segment and a chapter review; the most thorough and most expensive.");
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
  if(!/\.(pdf|epub)$/i.test(file.name)||file.size===0||file.size>25*1024*1024){message(t('בחרו קובץ PDF או EPUB עד 25 MB.',"Choose a PDF or EPUB file up to 25 MB."));return}
  setBusy(true);message('');
  try{const response=await fetch('/upload?name='+encodeURIComponent(file.name),{method:'POST',headers:{'X-UI-Token':token},body:file});
    const result=await response.json();if(!response.ok)throw Error(result.error||t('העלאת הקובץ נכשלה',"File upload failed"));
    setUploaded({name:file.name,size:file.size,path:result.path});
  }catch(error){message(error.message)}finally{setBusy(false)}
}
function showConnection(){if(!$('connection-dialog').open)$('connection-dialog').showModal()}
function renderConnection(){
  $('connection-label').textContent=t('מודל: ',"Model: ")+(isServer()?t('תצורת שרת',"Server configuration"):isReal()?t('משלי',"My own"):'Auto');
  $('connection-dot').classList.toggle('connected',modelConfigAvailable||Object.keys(keyProvidersAvailable).length>0);
  $('connection-detail').textContent=t('Auto הוא מצב תצוגת ניסיון בלבד, ללא עלות וללא תרגום אמיתי. "מודל משלי" משתמש במפתח ה-API שלכם, הנשמר בזיכרון השרת לאורך ההרצה בלבד.',"Auto is a trial preview only, with no cost and no real translation. \"My own model\" uses your API key, which is kept in the server's memory for the run only.");
}
function askProviderConsent(chosen){
  const dialog=$('provider-consent');
  const providers=resolvedProviders.map(p=>p.id+(p.endpoint?' ('+p.endpoint+')':'')).join(', ');
  $('provider-consent-detail').textContent=t('הטקסט של ',"The text of ")+uploaded.name+t(' יישלח לספקים: '," will be sent to the providers: ")+providers+
    t('. פרופיל: ',". Profile: ")+$('profile-summary').textContent+t('. רמת בדיקה: ',". Review level: ")+$('quality-summary').textContent+
    t('. תקציב מרבי לפי האומדן: $',". Maximum budget according to the estimate: $")+chosen.budget_usd+'.';
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
  if(!auto&&!chosen.role_selections&&!isServer()){message(t('בחרו מודל מתרגם לפני התרגום.',"Choose a translator model before translating."));return}
  if(!auto){const missing=missingKeyProviders();if(missing.length){message(t('יש לשמור מפתח API עבור: ',"Save an API key for: ")+missing.join(', ')+'.');return}}
  if(!auto&&!validBudget(chosen.budget_usd)){message(t('יש להגדיר תקציב מרבי למסמך (מספר חיובי) לפני תרגום בתשלום.',"Set a maximum budget per document (a positive number) before a paid translation."));$('translation-options').open=true;$('budget').focus();return}
  if(!auto&&(!previewState.valid||previewState.fingerprint!==previewFingerprint(chosen))){message(t('ממתינים לאומדן עדכני לפני התרגום.',"Waiting for an up-to-date estimate before translating."));return}
  if(!auto&&!previewState.withinBudget){message(t('האומדן השמרני חורג מהתקציב שנבחר; הגדילו תקציב או שנו הגדרות.',"The conservative estimate exceeds the chosen budget; raise the budget or change the settings."));$('translation-options').open=true;$('budget').focus();return}
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
const num=n=>Number(n||0).toLocaleString('en-US'),usd=n=>'$'+Number(n||0).toFixed(4),ltr=v=>'<bdi dir="ltr">'+esc(v)+'</bdi>';
const statRow=(label,value)=>'<dt>'+esc(label)+'</dt><dd>'+value+'</dd>';
function renderUsage(id){
  const container=$(id),rows=currentJob.budget_status?.provider_usage||[],replays=currentJob.local_replays||0,hits=currentJob.budget_status?.cache_hits||0;
  container.hidden=!rows.length&&!replays&&!hits;
  if(container.hidden){container.innerHTML='';return}
  const sum=key=>rows.reduce((acc,r)=>acc+(Number(r[key])||0),0);
  container.innerHTML=(rows.length?t('<table class="usage-table"><thead><tr><th>מודל</th><th>קריאות</th><th>טוקנים בקלט</th><th>טוקנים בפלט</th></tr></thead><tbody>',"<table class=\"usage-table\"><thead><tr><th>Model</th><th>Calls</th><th>Input tokens</th><th>Output tokens</th></tr></thead><tbody>")+
    rows.map(r=>'<tr><td>'+ltr(r.provider+' / '+r.model)+'</td><td>'+ltr(num(r.calls))+'</td><td>'+ltr(num(r.input))+'</td><td>'+ltr(num(r.output))+'</td></tr>').join('')+'</tbody></table>':'')+
    t('<details class="usage-more"><summary>מוני משנה</summary><dl class="stat-grid">',"<details class=\"usage-more\"><summary>Secondary counters</summary><dl class=\"stat-grid\">")+
    statRow(t('קריאת מטמון ספק',"Provider cache reads"),ltr(num(sum('cached'))))+statRow(t('כתיבה למטמון ספק',"Provider cache writes"),ltr(num(sum('cache_write'))))+statRow(t('כתיבה למטמון (שעה)',"Cache writes (hourly)"),ltr(num(sum('cache_write_1h'))))+
    statRow(t('חשיבה (כלולה בפלט)',"Reasoning (included in output)"),ltr(num(sum('reasoning'))))+(sum('unmetered_calls')?statRow(t('קריאות ללא מדידה',"Unmetered calls"),ltr(num(sum('unmetered_calls')))):'')+
    statRow(t('שימוש חוזר מקומי',"Local replays"),ltr(num(replays)))+statRow(t('מטמון תוצאות מקומי',"Local result cache"),ltr(num(hits)))+'</dl></details>';
}
function renderStats(){
  const job=currentJob,box=$('processing-budget'),p=job.progress,b=job.budget_status,rows=[];
  const stage=job.ocr_progress?null:(p?.phase||'');
  if(stage)rows.push(statRow(t('שלב',"Stage"),esc(stageLabel(stage))));
  if(p&&p.total_chapters)rows.push(statRow(t('פרקים',"Chapters"),ltr(num(p.completed_chapters)+' / '+num(p.total_chapters))));
  else if(job.chapter_progress)rows.push(statRow(t('פרקים',"Chapters"),ltr(num(job.chapter_progress.current)+' / '+num(job.chapter_progress.total))));
  if(p&&p.total_steps)rows.push(statRow(t('קריאות',"Calls"),ltr(num(p.completed_steps)+' / '+num(p.total_steps))));
  if(b)rows.push(statRow(t('הוצאה משוערת',"Estimated spend"),ltr(usd(b.list_estimated_spent_usd))),statRow(t('שמור/ממתין',"Held / pending"),ltr(usd(b.held_usd))),statRow(t('נותר מהתקציב',"Remaining budget"),ltr(usd(job.remaining_budget_usd))));
  box.hidden=!rows.length;box.innerHTML=rows.length?'<dl class="stat-grid">'+rows.join('')+'</dl>':'';
}
function renderProcessing(){
  $('processing-title').textContent=stageLabel(currentJob.stage_label)||t('קוראים את המסמך…','Reading the document…');
  $('processing-file').textContent=currentJob.placeholder?t('המסמך האחרון','The last document'):currentJob.filename;
  const progress=$('translation-progress');
  const pct=renderBook();
  progress.value=pct;$('processing-percentage').textContent=pct+'%';
  let detail;
  if(currentJob.ocr_progress){
    const ocr=currentJob.ocr_progress;
    detail=(ocr.phase==='vision'?t('בדיקת המודל מול תמונות העמודים: ',"Model check against page images: "):t('זיהוי טקסט בעמודים סרוקים: ',"Recognizing text on scanned pages: "))+ocr.done+t(' מתוך '," of ")+ocr.total+t(' עמודים.'," pages.");
  } else if(currentJob.progress&&currentJob.progress.total_chapters){
    detail=t('פרק ',"Chapter ")+currentJob.progress.completed_chapters+t(' מתוך '," of ")+currentJob.progress.total_chapters+t(' הושלם.'," completed.");
  } else if(currentJob.total_units){
    detail=currentJob.completed_units+t(' מתוך '," of ")+currentJob.total_units+t(' מקטעים הושלמו.'," segments completed.");
    if(currentJob.chapter_progress)detail=t('פרק ',"Chapter ")+currentJob.chapter_progress.current+t(' מתוך '," of ")+currentJob.chapter_progress.total+'. '+detail;
  } else detail=t('מחלצים את הטקסט ומכינים את התרגום.',"Extracting the text and preparing the translation.");
  const blocker=currentJob.blocker;
  $('processing-detail').textContent=(currentJob.error&&!blocker?currentJob.error+' ':'')+detail+t(' אפשר לחזור לחלון הזה בהמשך.'," You can come back to this window later.");
  renderDecision(blocker);
  renderUsage('processing-usage');renderResumeKeyFields();
  renderStats();
  const canPauseResume=currentJob.settings&&currentJob.settings.automation;
  $('pause-button').hidden=!(canPauseResume&&['translating','reviewing','queued','reading'].includes(currentJob.status));
  $('resume-button').hidden=!(canPauseResume&&!blocker&&['paused','interrupted','failed'].includes(currentJob.status));
  renderRecheck(canPauseResume);renderCrossReview(canPauseResume);
  renderResumeKeyFields();
}
function renderRecheck(automation){
  const count=currentJob.recheck_candidates||0,report=currentJob.recheck_report;
  const idle=automation&&['paused','interrupted','failed'].includes(currentJob.status);
  $('recheck-box').hidden=!(idle&&(count>0||report));
  if(report){
    $('recheck-message').textContent=t('נקראו מחדש ',"Re-read ")+report.unit_reviews_recovered+t(' ביקורות מקטעים ו־'," segment reviews and ")+report.chapter_qa_recovered+
      t(' בדיקות פרקים. '," chapter checks. ")+(report.reopened_chapters.length?report.reopened_chapters.length+t(' פרקים נפתחו מחדש, וכ־'," chapters were reopened, and about ")+report.units_to_correct+
      t(' מקטעים יקבלו תיקון ובדיקה חוזרת כשהעבודה תמשיך.'," segments will get a correction and re-check when the work continues."):t('לא נמצאו תיקונים חדשים.',"No new corrections were found."))+
      (report.still_needs_human?' '+report.still_needs_human+t(' תשובות עדיין דורשות בדיקה אנושית.'," answers still need human review."):'');
    $('recheck-button').hidden=true;
  } else {
    $('recheck-message').textContent=count+t(' תשובות בקורת שמורות סומנו בעבר "דורש בדיקה אנושית" בגלל בדיקה מחמירה מדי של הציטוטים. אפשר לקרוא אותן שוב עם הבדיקה המעודכנת.'," saved review answers were previously marked \"needs human review\" because of an overly strict check of the quotations. They can be re-read with the updated check.");
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
let crossReviewPrepared=null;
function crossReviewLabel(){
  const windows=Object.values((currentJob.cross_qa&&currentJob.cross_qa.windows)||{});
  return windows.length&&windows.every(w=>w&&w.status==='completed')?t('להריץ שוב בדיקה רוחבית',"Run cross-review again"):t('להכין בדיקה רוחבית',"Prepare cross-review");
}
function renderCrossReview(automation){
  const idle=automation&&['paused','interrupted','failed'].includes(currentJob.status);
  const prepared=crossReviewPrepared===currentJob.job_id&&currentJob.cross_review_report;
  $('cross-review-box').hidden=!(idle&&(currentJob.cross_review_available||prepared));
  $('cross-review-button').hidden=!!prepared;$('cross-review-button').textContent=crossReviewLabel();
  $('cross-review-done').hidden=!prepared;
}
async function prepareCrossReviewFromResult(){
  $('result-cross-review-error').hidden=true;$('result-cross-review-button').disabled=true;
  try{const result=await request('/document-cross-review',{job_id:currentJob.job_id});
    crossReviewPrepared=result.job_id;
    currentJob={...result,settings:result.settings||currentJob.settings};show('processing-panel');renderProcessing();
  }catch(error){$('result-cross-review-error').textContent=error.message;$('result-cross-review-error').hidden=false}
  finally{$('result-cross-review-button').disabled=false}
}
async function prepareCrossReview(){
  $('cross-review-error').hidden=true;$('cross-review-button').disabled=true;
  try{const result=await request('/document-cross-review',{job_id:currentJob.job_id});
    crossReviewPrepared=result.job_id;
    currentJob={...result,settings:result.settings||currentJob.settings};renderProcessing();
  }catch(error){$('cross-review-error').textContent=error.message;$('cross-review-error').hidden=false}
  finally{$('cross-review-button').disabled=false}
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
        <button type="button" class="secondary-button decision-confirm">${t('אישור והמשך','Confirm and continue')}</button>`;
      row.querySelector('button').onclick=()=>decide(option,Number(row.querySelector('input').value),row.querySelector('button'));
    } else {
      row.innerHTML=`<button type="button" class="${index===0?'primary-button':'secondary-button'}">${esc(option.label)}</button>`;
      row.querySelector('button').onclick=()=>decide(option,null,row.querySelector('button'));
    }
    options.append(row);
  });
  applyAutoDirs();
}
async function decide(option,value,button){
  if(option.input==='usd'&&!(value>0)){$('decision-error').textContent=t('הזינו סכום בדולרים.',"Enter an amount in dollars.");$('decision-error').hidden=false;return}
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
    $('processing-detail').textContent=error.message+t(' ננסה שוב לבדוק את מצב ההרצה.'," We will try checking the job status again.");pollTimer=setTimeout(()=>poll(jobId),5000)}
}
function sourceExt(){return (currentJob.source_kind||'pdf').toLowerCase()}
function qualityLabel(){
  if(currentJob.settings.model==='auto')returnt('תצוגת ניסיון',"Trial preview");
  return ({checked_draft:t('טיוטה שבדיקתה הושלמה',"Draft, review completed"),draft_with_exceptions:t('טיוטה עם חריגים',"Draft with exceptions"),
    unreviewed_draft:t('טיוטה ללא QA',"Draft without QA"),edited_draft_review_stale:t('טיוטה ערוכה — QA קודם אינו עדכני',"Edited draft — earlier QA is out of date")})[currentJob.quality_status]||t('טיוטה אוטומטית לא מאושרת',"Unapproved automatic draft");
}
const LIMITATION_LABELS={missing_translation:'קטעים שנשארו בשפת המקור',inline_markup_flattened:'עיצוב פנימי (הדגשות/קישורים) פושט',units_merged_multiple_blocks:'מקטעים שאוחדו מכמה פסקאות'};
function groupLimitations(list){
  const counts=new Map();list.forEach(l=>{const k=l.kind||'other';counts.set(k,(counts.get(k)||0)+1)});
  return [...counts.entries()].sort((a,b)=>b[1]-a[1]).map(([kind,count])=>({kind,count,label:LIMITATION_LABELS[kind]||kind}));
}
function renderResultDetails(limitations,notes,findings){
  const lim=$('result-limitations'),nt=$('result-notes'),fd=$('result-findings'),groups=groupLimitations(limitations),shown=3;
  lim.hidden=!groups.length;
  lim.innerHTML=groups.length?t('<b>הערות על בניית הקובץ</b><ul>',"<b>Notes on building the file</b><ul>")+groups.map(g=>'<li>'+esc((LANG==='en'&&LIMITATION_EN[g.kind])||g.label)+': '+ltr(num(g.count))+'</li>').join('')+'</ul>':'';
  nt.hidden=!notes.length;
  nt.innerHTML=notes.length?t('<b>הערות בדיקה</b><ul>',"<b>Review notes</b><ul>")+notes.slice(0,shown).map(n=>'<li dir="auto">'+esc(n)+'</li>').join('')+
    (notes.length>shown?'<li>'+t('ועוד '+ltr(num(notes.length-shown)),'and '+ltr(num(notes.length-shown))+' more')+'</li>':'')+'</ul>':'';
  fd.hidden=!findings;
  fd.innerHTML=findings?t('בבדיקות נרשמו ',"The checks recorded ")+ltr(num(findings))+t(' ממצאים או הערות; היסטוריית הבדיקה והתיקון מוצגת במקטעים.'," findings or notes; the review and correction history is shown per segment."):'';
  $('result-details').hidden=!(groups.length||notes.length||findings||!$('result-usage').hidden);
}
function renderResultSummary(){
  renderBook(true);renderUsage('result-usage');
  const auto=currentJob.settings.model==='auto',complete=currentJob.status==='completed',partial=!complete&&currentJob.completed_units>0;
  $('result-title').textContent=auto?t('תצוגת הניסיון מוכנה.',"The trial preview is ready."):complete?t('התרגום מוכן.',"The translation is ready."):partial?t('התרגום הושלם חלקית.',"The translation is partially complete."):t('התרגום לא הושלם.',"The translation did not complete.");
  $('result-symbol').textContent=auto?'↗':complete?'✓':'!';$('result-eyebrow').textContent=auto?t('ללא קריאה לספק',"No provider call"):t('המסמך שלכם',"Your document");
  $('result-filename').textContent=currentJob.filename;
  $('download-filename').textContent=currentJob.filename.replace(/\.[^.]+$/,'')+'.he.'+sourceExt();
  $('result-meta').textContent=qualityLabel()+' · '+currentJob.completed_units+'/'+currentJob.total_units+t(' מקטעים'," segments");
  const limitations=currentJob.export_limitations||[],notes=currentJob.review_notes||[];
  const findings=(currentJob.units||[]).reduce((sum,u)=>sum+(u.findings||[]).length+(u.unresolved?1:0),0)+(currentJob.exceptions||[]).length+
    (currentJob.chapter_qa_results||[]).reduce((sum,q)=>sum+(q.issues||[]).length,0);
  const stale=currentJob.quality_status==='edited_draft_review_stale'||(currentJob.units||[]).some(u=>u.review_stale);
  const notices=[];
  if(auto)notices.push(t('זו תצוגת ניסיון של הממשק בלבד. לא בוצע תרגום אמיתי.',"This is an interface trial preview only. No real translation was performed."));
  if(currentJob.error)notices.push(currentJob.error);
  if(resultError)notices.push(resultError);
  if(!auto&&complete&&(limitations.length||notes.length||findings))notices.push(t('הקובץ מוכן. נרשמו הערות בדיקה ובנייה — פרטים למטה.',"The file is ready. Review and build notes were recorded — details below."));
  $('result-notice').textContent=notices.join(' · ');$('result-notice').hidden=!notices.length;
  renderResultDetails(limitations,notes,findings);
  const exceptionText=manualEdit?t('הגרסה נערכה ידנית. בדיקות המודל שקדמו לעריכה אינן אישור לטקסט החדש; לא נשלחה קריאת מודל נוספת.','The version was edited manually. Model reviews that preceded the edit do not approve the new text; no further model call was sent.'):stale?t('הטקסט נערך לאחר בדיקת המודל; תוצאות ה־QA הקודמות אינן אישור לגרסה הערוכה.','The text was edited after the model review; the earlier QA results do not approve the edited version.'):'';
  $('result-exceptions').textContent=exceptionText;$('result-exceptions').hidden=!exceptionText;
  $('download-pdf').disabled=!complete;
  renderNotebook();
  $('review-button').disabled=!complete;
  $('cost-summary').textContent=currentJob.estimated_cost_usd?t('אומדן $','Estimate $')+currentJob.estimated_cost_usd.toFixed(4):auto?t('ללא עלות','No cost'):'';
}
function renderResult(){
  manualEdit=false;resultError='';renderResultSummary();
  const complete=currentJob.status==='completed';
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
  $('result-cross-review').hidden=!(currentJob.cross_review_available&&currentJob.settings&&currentJob.settings.automation);
  $('result-cross-review-button').textContent=crossReviewLabel();
  for(const [index,text] of summaries){const item=document.createElement('li');item.textContent=t('פרק ',"Chapter ")+(Number(index)+1)+': '+text;list.append(item)}
}
async function downloadNotebook(){
  $('download-notebook').disabled=true;
  try{const blob=await request('/document-notebook',{job_id:currentJob.job_id},true);
    const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=currentJob.filename.replace(/\.[^.]+$/,'')+'.notebook.md';
    document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
  }catch(error){resultError=error.message;renderResultSummary()}finally{$('download-notebook').disabled=false}
}
function dirty(){return !$('review-panel').hidden&&currentJob?.units[unitIndex]&&$('review-target').value!==currentJob.units[unitIndex].target_text}
function confirmDiscard(){return !dirty()||confirm(t('יש שינויים שלא נשמרו. לעבור בלי לשמור?',"You have unsaved changes. Continue without saving?"))}
function renderReview(){
  const unit=currentJob.units[unitIndex];if(!unit)return;
  $('unit-select').value=unitIndex;
  $('review-source').textContent=unit.source_text;$('review-source').dir='auto';
  $('review-target').value=unit.target_text;$('review-message').textContent='';reviewSaved=false;
  renderReviewLabels(unit);
}
function renderReviewLabels(unit){
  $('review-location').textContent=t('מקטע ','Segment ')+(unitIndex+1)+t(' מתוך ',' of ')+currentJob.units.length;
  $('review-findings').textContent=reviewFindingsText(unit);
}
function reviewFindingsText(unit){
  const labels={missing_number:t('מספר חסר',"Missing number"),missing_footnote_marker:t('סימון הערה חסר',"Missing footnote marker"),missing_citation_reference:t('הפניה לבדיקה',"Reference to check"),missing_formula_token:t('נוסחה לבדיקה',"Formula to check"),proper_name_candidate:t('שם לבדיקה',"Name to check"),missing_hebrew_script:t('הטקסט אינו תרגום עברי',"The text is not a Hebrew translation")};
  const findings=unit.findings||[];
  const latest=unit.recheck||unit.review;
  const review=latest?(' · '+(unit.recheck?t('בדיקה חוזרת: ',"Re-check: "):t('בדיקה: ',"Review: "))+(latest.verdict||latest.status)+
    (latest.issues&&latest.issues.length?' ('+latest.issues.length+t(' נקודות)'," points)"):'')+(unit.review_stale?t(' · נערך לאחר הבדיקה — נדרשת בדיקה מחדש'," · edited after the review — a new review is needed"):'')):'';
  const display=value=>typeof value==='string'?value:JSON.stringify(value);
  const issueText=issue=>{
    if(typeof issue!=='object'||!issue)return display(issue);
    return ['severity','type','category','status','verdict','chapter','unit_id','source_span','target_span','translation_span','span','problem','explanation','description','suggested_correction','correction','reason','error']
      .filter(key=>issue[key]!==undefined&&issue[key]!==null)
      .map(key=>key+': '+display(issue[key])).join('\n')||display(issue);
  };
  const details=[];
  for(const issue of latest?.issues||[])details.push(t('ממצא בבדיקת המקטע:\n',"Finding in the segment review:\n")+issueText(issue));
  for(const chapter of currentJob.chapter_qa_results||[]){
    if(chapter.unit_ids?.includes(unit.unit_id)){
      for(const issue of chapter.issues||[])details.push(t('ממצא בבדיקת הפרק:\n',"Finding in the chapter review:\n")+issueText(issue));
      if(chapter.verdict&&chapter.verdict!=='PASS')details.push(t('בדיקת פרק: ',"Chapter review: ")+chapter.verdict+' · '+(chapter.status||''));
    }
  }
  for(const exception of currentJob.exceptions||[]){
    if(!exception.unit_id||exception.unit_id===unit.unit_id)
      details.push(t('חריג ',"Exception ")+(exception.unit_id?t('במקטע',"in the segment"):t('במסמך',"in the document"))+':\n'+issueText(exception.issue||exception));
  }
  if(unit.unresolved)details.push(t('ממצא שלא נפתר: ',"Unresolved finding: ")+display(unit.unresolved));
  return (findings.length?t('נקודות לבדיקה: ',"Points to check: ")+findings.map(f=>(labels[f.type]||t('דורש בדיקה',"Needs review"))+(f.source_token?' ('+f.source_token+')':'')).join(' · '):'')+review+
    (details.length?'\n\n'+details.join('\n\n'):'');
}
async function saveEdit(showMessage=true){
  $('save-edit').disabled=true;
  try{currentJob=await request('/document-review',{job_id:currentJob.job_id,unit_index:unitIndex,target_text:$('review-target').value,expected_revision:currentJob.revision});
    renderReview();
    manualEdit=true;renderResultSummary();
    if(showMessage){reviewSaved=true;$('review-message').textContent=t('השינויים נשמרו. ההורדה כוללת את הגרסה המעודכנת.','Changes saved. The download includes the updated version.')}return true;
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
  }catch(error){resultError=error.message;renderResultSummary()}finally{$('download-pdf').disabled=false}
}
// ---- library: all completed translations ----
let libraryReturn='start-panel',libraryCounter=0;
function visiblePanel(){return ['start-panel','processing-panel','result-panel','library-panel'].find(id=>!$(id).hidden)||'start-panel'}
function libraryDate(seconds){
  const date=new Date(Number(seconds)*1000);if(!Number.isFinite(date.getTime()))return'';
  try{return date.toLocaleString(t('he-IL','en-US'),{dateStyle:'medium',timeStyle:'short'})}catch(_){return date.toLocaleString()}
}
function libraryStem(filename){return String(filename||'document').replace(/\.[^.]+$/,'')}
function libraryFontOptions(selected){
  const fonts=pdfFonts.filter(f=>f.available);
  const chosen=fonts.some(f=>f.id===selected)?selected:'';
  return t('<option value="">גופן ברירת המחדל</option>',"<option value=\"\">Default font</option>")+fonts.map(f=>`<option value="${esc(f.id)}"${f.id===chosen?' selected':''}>${esc(f.name)}</option>`).join('');
}
function renderLibrary(documents){
  const list=$('library-list');list.replaceChildren();
  $('library-empty').hidden=documents.length>0;
  documents.forEach((doc,index)=>{
    const kind=doc.source_kind==='epub'?'epub':'pdf',detailId='library-detail-'+index;
    const item=document.createElement('li');item.className='library-item';item.dataset.jobId=doc.job_id;
    const fontField=kind==='pdf'?`<div class="field library-font"><label for="library-font-${index}">${t(`גופן להורדה`,`Download font`)}</label><select id="library-font-${index}" class="library-font-select">${libraryFontOptions(doc.font_id)}</select></div>`:'';
    item.innerHTML=`<button type="button" class="library-entry" aria-expanded="false" aria-controls="${detailId}">
      <span class="library-kind" data-kind="${kind}">${kind.toUpperCase()}</span>
      <span class="library-entry-text"><strong dir="auto">${esc(doc.filename)}</strong><span class="library-meta">${esc(libraryDate(doc.completed_at))}${doc.unit_count!=null?' · '+esc(doc.unit_count)+t(' מקטעים'," segments"):''}</span></span>
      <span class="chevron" aria-hidden="true">⌄</span></button>
      <div id="${detailId}" class="library-detail" hidden>${fontField}
      <div class="library-actions"><button type="button" class="primary-button library-download" data-format="${kind}">${t(`הורדת ${kind.toUpperCase()}`,`Download ${kind.toUpperCase()}`)} <span aria-hidden="true">↓</span></button>
      <button type="button" class="secondary-button library-download" data-format="html">${t('הורדת HTML','Download HTML')} <span aria-hidden="true">↓</span></button>
      <button type="button" class="text-button library-open">${t('פתיחה','Open')} <span aria-hidden="true">${t('←','→')}</span></button>
      <button type="button" class="text-button library-delete">${t('מחיקה','Delete')}</button>
      <button type="button" class="text-button library-learning">${t('העבר ללמידת שפה','Send to language learning')} <span aria-hidden="true">${t('←','→')}</span></button></div>
      <p class="message library-error" role="alert" hidden></p></div>`;
    const entry=item.querySelector('.library-entry'),detail=item.querySelector('.library-detail');
    entry.onclick=()=>{const open=entry.getAttribute('aria-expanded')!=='true';entry.setAttribute('aria-expanded',String(open));detail.hidden=!open;item.classList.toggle('open',open)};
    item.querySelectorAll('.library-download').forEach(button=>button.onclick=()=>libraryDownload(doc,button,item));
    item.querySelector('.library-open').onclick=()=>libraryOpen(doc);
    item.querySelector('.library-delete').onclick=()=>libraryDelete(doc,item,false);
    item.querySelector('.library-learning').onclick=()=>openLearningWindow(doc,item.querySelector('.library-error'));
    list.append(item);
  });
  applyAutoDirs();
}
const IN_PROGRESS_STATUS={failed:'נעצר',paused:'מושהה',interrupted:'הופסק',queued:'ממתין',reading:'קורא',translating:'מתרגם כעת',reviewing:'בבדיקה',rebuilding:'בונה את הקובץ'};
function renderInProgress(documents){
  const list=$('library-list');list.replaceChildren();
  $('library-empty').hidden=documents.length>0;
  documents.forEach((doc,index)=>{
    const kind=doc.source_kind==='epub'?'epub':'pdf',detailId='library-detail-'+index;
    const item=document.createElement('li');item.className='library-item in-progress';item.dataset.jobId=doc.job_id;
    const parts=[(LANG==='en'?IN_PROGRESS_EN:IN_PROGRESS_STATUS)[doc.status]||doc.status];
    if(doc.total_chapters)parts.push(t('פרק ',"Chapter ")+doc.completed_chapters+t(' מתוך '," of ")+doc.total_chapters);
    parts.push(doc.translated_units+t(' מתוך '," of ")+doc.total_units+t(' מקטעים'," segments"));
    if(doc.spent_usd!=null)parts.push('$'+Number(doc.spent_usd).toFixed(4)+(doc.budget_usd?t(' מתוך $'," of $")+Number(doc.budget_usd).toFixed(2):''));
    const notice=doc.blocker?`<p class="library-blocker">${esc(doc.blocker.message)}</p>`:(doc.error?`<p class="library-blocker">${esc(doc.error)}</p>`:'');
    const fontField=kind==='pdf'&&doc.formats.length?`<div class="field library-font"><label for="library-font-${index}">${t(`גופן להורדה`,`Download font`)}</label><select id="library-font-${index}" class="library-font-select">${libraryFontOptions(null)}</select></div>`:'';
    const downloads=doc.formats.length?`<button type="button" class="secondary-button library-download" data-format="${kind}" data-partial="1">${t(`הורדה חלקית ${kind.toUpperCase()}`,`Partial download ${kind.toUpperCase()}`)} <span aria-hidden="true">↓</span></button>
      <button type="button" class="secondary-button library-download" data-format="html" data-partial="1">${t('HTML חלקי','Partial HTML')} <span aria-hidden="true">↓</span></button>`:'';
    item.innerHTML=`<button type="button" class="library-entry" aria-expanded="false" aria-controls="${detailId}">
      <span class="library-kind" data-kind="${kind}">${kind.toUpperCase()}</span>
      <span class="library-entry-text"><strong dir="auto">${esc(doc.filename)}</strong><span class="library-meta">${esc(libraryDate(doc.updated_at))} · ${esc(parts.join(' · '))}</span>${doc.blocker?t('<span class="library-flag">נדרשת החלטה</span>',"<span class=\"library-flag\">Decision required</span>"):''}</span>
      <span class="chevron" aria-hidden="true">⌄</span></button>
      <div id="${detailId}" class="library-detail" hidden>${notice}${fontField}
      <div class="library-actions"><button type="button" class="primary-button library-open">${doc.blocker?t('פתיחה והחלטה','Open and decide'):t('פתיחה והמשך','Open and continue')} <span aria-hidden="true">${t('←','→')}</span></button>${downloads}
      <button type="button" class="text-button library-delete">${t('מחיקה','Delete')}</button></div>
      ${doc.formats.length?t('<p class="library-partial-note">בהורדה חלקית, מה שעדיין לא תורגם נשאר בשפת המקור.</p>',"<p class=\"library-partial-note\">In a partial download, whatever has not been translated yet stays in the source language.</p>"):''}
      <p class="message library-error" role="alert" hidden></p></div>`;
    const entry=item.querySelector('.library-entry'),detail=item.querySelector('.library-detail');
    entry.onclick=()=>{const open=entry.getAttribute('aria-expanded')!=='true';entry.setAttribute('aria-expanded',String(open));detail.hidden=!open;item.classList.toggle('open',open)};
    item.querySelectorAll('.library-download').forEach(button=>button.onclick=()=>libraryDownload(doc,button,item));
    item.querySelector('.library-open').onclick=()=>libraryOpen(doc);
    item.querySelector('.library-delete').onclick=()=>libraryDelete(doc,item,true);
    list.append(item);
  });
  applyAutoDirs();
}
async function libraryDelete(doc,item,inProgress){
  const spent=inProgress&&doc.spent_usd?t(' העבודה שכבר שולמה ($'," The work already paid for ($")+Number(doc.spent_usd).toFixed(4)+t(') תאבד.',") will be lost."):'';
  if(!confirm(t('למחוק לצמיתות את "',"Permanently delete \"")+doc.filename+t('"? יימחקו התרגום, ההעתק של קובץ המקור, מחברת הספר ויומן העלויות שלו.',"\"? The translation, the copy of the source file, the book notebook and its cost log will be deleted.")+spent+t(' אי אפשר לבטל את המחיקה.'," This cannot be undone.")))return;
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
  libraryTexts();
  loadLibrary();
}
function libraryTexts(){
  const tab=libraryTab;
  $('library-intro').textContent=tab==='done'?t('כל המסמכים שתרגומם הושלם ונשמר במחשב שלכם. לחצו על מסמך כדי להוריד אותו.',"All documents whose translation is complete and saved on your computer. Click a document to download it."):
    t('תרגומים שעדיין לא הושלמו: אפשר להמשיך אותם, להחליט מה לעשות כשהם נעצרו, ולהוריד את מה שכבר תורגם.',"Translations not yet complete: you can continue them, decide what to do when they stopped, and download what has been translated so far.");
  $('library-empty').textContent=tab==='done'?t('עדיין אין בספרייה תרגומים שהושלמו. מסמך שתרגומו יושלם יופיע כאן.',"There are no completed translations in the library yet. A document whose translation completes will appear here."):t('אין כרגע תרגומים בתהליך עבודה.',"There are no translations in progress right now.");
}
async function loadLibrary(){
  const id=++libraryCounter,tab=libraryTab;
  $('library-message').hidden=true;$('library-empty').hidden=true;$('library-list').replaceChildren();
  $('library-status').textContent=t('טוען את הספרייה…',"Loading the library…");
  try{const result=await request(tab==='done'?'/document-library':'/document-in-progress',{});if(id!==libraryCounter)return;
    $('library-status').textContent='';const documents=Array.isArray(result.documents)?result.documents:[];libraryData={tab,documents};
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
function openLearningWindow(doc,errorNode){
  errorNode.hidden=true;
  const target='/learning?job_id='+encodeURIComponent(doc.job_id);
  const win=window.open(target,'scholarly-learning');
  if(!win){errorNode.innerHTML='';const link=document.createElement('a');link.href=target;link.target='scholarly-learning';link.rel='noopener';
    link.className='text-button';link.textContent=t('פתיחת למידת שפה בחלון חדש',"Open language learning in a new window");errorNode.append(link);errorNode.hidden=false;return}
  win.focus?.();
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
function renderRecent(){if(recentName)$('recent-button').textContent=t('חזרה ל־','Back to ')+recentName}
function populateFontSelects(){
  const options=pdfFonts.map(f=>`<option value="${f.id}" ${f.available?'':'disabled'}>${f.name}${f.available?'':t(' (לא זמין)'," (unavailable)")}</option>`).join('');
  $('font-before').innerHTML=options;$('font-after').innerHTML=t('<option value="">ללא שינוי</option>',"<option value=\"\">No change</option>")+options;
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
    if(modelConfigAvailable){const option=document.createElement('option');option.value='server';option.textContent=t('תצורת המודלים שהוגדרה בשרת',"Model configuration set on the server");$('model').append(option)}
    populateFontSelects();initRoleUI();renderKeyFields();renderConnection();updateSettings();
  }catch(error){message(error.message)}
  let last;try{last=localStorage.getItem('document-last-job')}catch(_){}
  if(last){setBusy(true);show('processing-panel');currentJob={filename:'המסמך האחרון',placeholder:true,status:'queued',stage_label:'',total_units:0,completed_units:0};renderProcessing();await poll(last)}
  else{try{const result=await request('/document-recent');if(result.job){$('recent-button').hidden=false;recentName=result.job.filename;renderRecent();
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
$('save-keys').onclick=saveKeys;$('pause-button').onclick=pauseJob;$('resume-button').onclick=resumeJob;$('recheck-button').onclick=recheckReviews;$('cross-review-button').onclick=prepareCrossReview;$('result-cross-review-button').onclick=prepareCrossReviewFromResult;
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
// ---- language switch ----
const origText=new WeakMap();
function applyStatic(){
  const attrs=[['data-i18n',null],['data-i18n-aria','aria-label'],['data-i18n-ph','placeholder']];
  for(const [data,attr] of attrs){
    document.querySelectorAll('['+data+']').forEach(el=>{
      let saved=origText.get(el);if(!saved){saved={};origText.set(el,saved)}
      const slot=attr||'html';
      if(!(slot in saved)){if(LANG!=='en')return;saved[slot]=attr?el.getAttribute(attr):el.innerHTML}
      const value=LANG==='en'?EN[el.getAttribute(data)]:saved[slot];
      if(value===undefined)return;
      if(attr)el.setAttribute(attr,value);else el.innerHTML=value;
    });
  }
}
const FREE_SEL='#processing-detail,#form-message,#result-notice,#decision-message,#decision-error,#recheck-error,#cross-review-error,#result-cross-review-error,#library-message,#review-findings,#key-message,#resume-key-message,.library-blocker,.library-error,#decision-options label,#decision-options button:not(.decision-confirm)';
function applyAutoDirs(){
  document.querySelectorAll(FREE_SEL).forEach(el=>{if(LANG==='en')el.setAttribute('dir','auto');else el.removeAttribute('dir')});
}
function applyBase(){
  const root=document.documentElement;
  root.lang=LANG;root.dir=LANG==='en'?'ltr':'rtl';
  document.title=t('תרגום מסמכים לעברית','Document translation to Hebrew');
  const button=$('language-button');button.textContent=t('English','עברית');button.lang=t('en','he');
  const arrow=document.querySelector('#translate-button>span[aria-hidden="true"]');if(arrow)arrow.textContent=t('←','→');
  applyStatic();applyAutoDirs();renderConnection();
}
function keptKeyInputs(){const kept={};document.querySelectorAll('.key-input,.resume-key-input').forEach(i=>{if(i.value)kept[i.className+':'+i.dataset.provider]=i.value});return kept}
function restoreKeyInputs(kept){document.querySelectorAll('.key-input,.resume-key-input').forEach(i=>{const v=kept[i.className+':'+i.dataset.provider];if(v)i.value=v})}
function setLanguage(next){
  if(next===LANG)return;
  LANG=next;remember('ui-language',next);
  const kept=keptKeyInputs(),beforeFont=$('font-before').value,afterFont=$('font-after').value;
  applyBase();
  document.querySelectorAll('.role-select option[data-cat]').forEach(option=>{
    const model=modelCatalog.find(m=>m.provider+':'+m.model===option.value);if(model)option.textContent=catalogLabel(model)});
  const serverOption=$('model').querySelector('option[value="server"]');
  if(serverOption)serverOption.textContent=t('תצורת המודלים שהוגדרה בשרת','Model configuration set on the server');
  if(pdfFonts.length){populateFontSelects();$('font-before').value=beforeFont;$('font-after').value=afterFont}
  updateSettings();renderConnection();renderRecent();libraryTexts();
  document.querySelectorAll('.decision-confirm').forEach(b=>b.textContent=t('אישור והמשך','Confirm and continue'));
  if(previewView&&!$('preview-card').hidden)previewView();
  const panel=visiblePanel();
  if(panel==='processing-panel'&&currentJob)renderProcessing();
  else if(panel==='result-panel'&&currentJob&&currentJob.settings){
    renderResultSummary();
    if(!$('review-panel').hidden&&currentJob.units&&currentJob.units[unitIndex]){
      renderReviewLabels(currentJob.units[unitIndex]);
      if(reviewSaved)$('review-message').textContent=t('השינויים נשמרו. ההורדה כוללת את הגרסה המעודכנת.','Changes saved. The download includes the updated version.');
    }
  } else if(panel==='library-panel'&&libraryData){
    const open=[...document.querySelectorAll('.library-item.open')].map(i=>i.dataset.jobId);
    const fonts={};document.querySelectorAll('.library-item').forEach(i=>{const s=i.querySelector('.library-font-select');if(s)fonts[i.dataset.jobId]=s.value});
    (libraryData.tab==='done'?renderLibrary:renderInProgress)(libraryData.documents);
    document.querySelectorAll('.library-item').forEach(i=>{
      const s=i.querySelector('.library-font-select');if(s&&fonts[i.dataset.jobId]!==undefined)s.value=fonts[i.dataset.jobId];
      if(open.includes(i.dataset.jobId))i.querySelector('.library-entry').click()});
  }
  renderKeyFields();restoreKeyInputs(kept);
  applyAutoDirs();
}
$('language-button').onclick=()=>setLanguage(LANG==='en'?'he':'en');
applyBase();
initialize();
