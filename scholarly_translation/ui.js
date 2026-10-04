const {token}=window.UI_CONFIG;
const $=id=>document.getElementById(id);
let uploaded=null,currentJob=null,chunkIndex=0,busy=false,pollTimer=null,keyAvailable=false;
const defaults={model:'gpt-6-luna',quality:'balanced',language:'auto',budget_usd:2};
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
function show(panel){for(const id of ['start-panel','processing-panel','result-panel'])$(id).hidden=id!==panel}
function setBusy(value){busy=value;updateSettings();$('sample-button').disabled=value}
function settings(){return {model:$('model').value,quality:$('quality').value,language:$('language').value,budget_usd:Number($('budget').value)}}
function updateSettings(){
  preferences=settings();remember('document-preferences',JSON.stringify(preferences));
  $('model-summary').textContent=$('model').selectedOptions[0].textContent;
  $('quality-summary').textContent=$('quality').selectedOptions[0].textContent;
  const demo=preferences.model==='demo';
  $('translate-label').textContent=demo?'פתיחת תצוגת ניסיון':busy?'מעלה קובץ…':'תרגום לעברית';
  $('translate-button').disabled=!uploaded||busy;
  $('send-note').textContent=demo?'ללא API וללא עלות. יוצג המקור בלבד; זה אינו תרגום.':'לחיצה על תרגום תבקש אישור לשליחת הטקסט ל־OpenAI.';
  $('quality').disabled=demo;$('budget').disabled=demo;
  $('quality-help').textContent=preferences.quality==='fast'?'פחות זמן חשיבה ועיבוד קצר יותר.':
    preferences.quality==='careful'?'יותר זמן חשיבה; עשוי להימשך זמן רב יותר ולעלות יותר.':'יותר זמן חשיבה למודל; אינו מבטיח דיוק מחקרי.';
}
function setUploaded(file){
  uploaded=file;$('upload-empty').hidden=!!file;$('upload-selected').hidden=!file;
  if(file){$('filename').textContent=file.name;$('file-size').textContent=(file.size/1024/1024<1?Math.ceil(file.size/1024)+' KB':(file.size/1024/1024).toFixed(1)+' MB')+' · '+file.name.split('.').pop().toUpperCase()}
  updateSettings();
}
async function uploadFile(file){
  if(!file||busy)return;
  if(!/\.(pdf|epub)$/i.test(file.name)||file.size===0||file.size>25*1024*1024){message('בחרו PDF או EPUB עד 25 MB.');return}
  setBusy(true);message('');
  try{const response=await fetch('/upload?name='+encodeURIComponent(file.name),{method:'POST',headers:{'X-UI-Token':token},body:file});
    const result=await response.json();if(!response.ok)throw Error(result.error||'העלאת הקובץ נכשלה');
    setUploaded({name:file.name,size:file.size,path:result.path});
  }catch(error){message(error.message)}finally{setBusy(false)}
}
function showConnection(){if(!$('connection-dialog').open)$('connection-dialog').showModal();$('api-key').focus()}
function renderConnection(){
  $('connection-label').textContent=keyAvailable?'OpenAI מחובר':'חיבור OpenAI';
  $('connection-dot').classList.toggle('connected',keyAvailable);
}
async function saveKey(clear=false){
  const key=clear?'':$('api-key').value.trim();if(!clear&&!key){$('key-message').textContent='יש להזין מפתח API.';return}
  $('save-key').disabled=true;
  try{const result=await request('/settings',{api_key:key});keyAvailable=result.api_key_available;$('api-key').value='';renderConnection();
    $('key-message').textContent=keyAvailable?(clear?'המפתח הזמני נוקה; מפתח הסביבה עדיין זמין.':'החיבור נשמר להרצה הזו.'):'אין מפתח זמין להרצה.';
    if(!clear)$('connection-dialog').close();
  }catch(error){$('key-message').textContent=error.message}finally{$('save-key').disabled=false}
}
async function translate(event){
  if(event)event.preventDefault();if(!uploaded||busy)return;message('');
  const chosen=settings(),demo=chosen.model==='demo';
  if(!demo&&!keyAvailable){message('חברו OpenAI כדי להתחיל בתרגום, או בחרו תצוגת ניסיון ללא API.');showConnection();return}
  if(!Number.isFinite(chosen.budget_usd)||chosen.budget_usd<0.01||chosen.budget_usd>30){message('בחרו תקציב בין $0.01 ל־$30.');$('translation-options').open=true;$('budget').focus();return}
  if(!demo&&!confirm('לשלוח את הטקסט של '+uploaded.name+' ל־OpenAI לתרגום?\nמודל: '+chosen.model+'\nמגבלת אומדן מחירון: $'+chosen.budget_usd+'\nרמת העיבוד: '+$('quality').selectedOptions[0].textContent))return;
  setBusy(true);
  try{const result=await request('/document-translate',{path:uploaded.path,settings:chosen,paid_confirm:!demo});remember('document-last-job',result.job_id);
    currentJob={job_id:result.job_id,filename:uploaded.name,status:'queued',completed_chunks:0,total_chunks:0};show('processing-panel');renderProcessing();await poll(result.job_id);
  }catch(error){show('start-panel');message(error.message);setBusy(false)}
}
function renderProcessing(){
  $('processing-title').textContent=currentJob.status==='translating'?'מתרגמים את המסמך…':'קוראים את המסמך…';
  $('processing-file').textContent=currentJob.filename;
  const progress=$('translation-progress');
  if(currentJob.total_chunks){progress.max=currentJob.total_chunks;progress.value=currentJob.completed_chunks;
    $('processing-detail').textContent=currentJob.completed_chunks+' מתוך '+currentJob.total_chunks+' מקטעים הושלמו. אפשר לחזור לחלון הזה בהמשך.'}
  else{progress.removeAttribute('value');$('processing-detail').textContent='מחלצים את הטקסט ומכינים את התרגום.'}
}
async function poll(jobId){
  clearTimeout(pollTimer);
  try{const result=await request('/document-job',{job_id:jobId});currentJob=result;
    if(['queued','reading','translating'].includes(result.status)){show('processing-panel');renderProcessing();pollTimer=setTimeout(()=>poll(jobId),1400)}
    else{setBusy(false);show('result-panel');renderResult();window.scrollTo({top:0,behavior:'smooth'})}
  }catch(error){if(error.status===400){forget('document-last-job');currentJob=null;setBusy(false);show('start-panel');message(error.message);return}
    $('processing-detail').textContent=error.message+' ננסה שוב לבדוק את מצב ההרצה.';pollTimer=setTimeout(()=>poll(jobId),5000)}
}
function renderResult(){
  const demo=currentJob.status==='demo',complete=['completed','demo'].includes(currentJob.status),partial=!complete&&currentJob.completed_chunks>0;
  $('result-title').textContent=demo?'תצוגת הניסיון מוכנה.':complete?'התרגום מוכן.':partial?'התרגום הושלם חלקית.':'התרגום לא הושלם.';
  $('result-symbol').textContent=demo?'↗':complete?'✓':'!';$('result-eyebrow').textContent=demo?'ללא קריאת API':'המסמך שלכם';
  $('result-filename').textContent=currentJob.filename;
  $('download-filename').textContent=currentJob.filename.replace(/\.[^.]+$/,'')+'.he.html';
  $('result-meta').textContent=(currentJob.settings.model==='demo'?'תצוגת ניסיון':currentJob.settings.model)+' · '+currentJob.completed_chunks+'/'+currentJob.total_chunks+' מקטעים';
  const notice=demo?'זו תצוגת ניסיון של הממשק בלבד. הוצג טקסט המקור; לא בוצע תרגום.':currentJob.error||'';
  $('result-notice').textContent=notice;$('result-notice').hidden=!notice;
  $('download-html').disabled=$('download-text').disabled=!currentJob.completed_chunks;
  $('review-button').disabled=!complete;$('download-html').firstChild.textContent=demo?'הורדת תצוגת הניסיון ':partial?'הורדת התרגום החלקי ':'הורדת התרגום ';
  $('cost-summary').textContent=currentJob.estimated_cost_usd?'אומדן $'+currentJob.estimated_cost_usd.toFixed(4):demo?'ללא עלות API':'';
  $('review-panel').hidden=true;$('chunk-select').replaceChildren();
  for(const [index,chunk] of (currentJob.chunks||[]).entries()){
    const option=document.createElement('option');option.value=index;option.textContent=(index+1)+' · '+chunk.location;$('chunk-select').append(option)}
  chunkIndex=0;
}
function dirty(){return !$('review-panel').hidden&&currentJob?.chunks[chunkIndex]&&$('review-target').value!==currentJob.chunks[chunkIndex].target_text}
function confirmDiscard(){return !dirty()||confirm('יש שינויים שלא נשמרו. לעבור בלי לשמור?')}
function renderReview(){
  const chunk=currentJob.chunks[chunkIndex];if(!chunk)return;
  $('chunk-select').value=chunkIndex;$('review-location').textContent=chunk.location+' · מקטע '+(chunkIndex+1)+' מתוך '+currentJob.chunks.length;
  $('review-source').textContent=chunk.source_text;$('review-source').dir=currentJob.language==='he'?'rtl':'ltr';
  $('review-target').value=chunk.target_text;$('review-message').textContent='';
  const labels={missing_number:'מספר חסר',missing_footnote_marker:'סימון הערה חסר',missing_citation_reference:'הפניה לבדיקה',missing_formula_token:'נוסחה לבדיקה',proper_name_candidate:'שם לבדיקה',missing_hebrew_script:'הטקסט אינו תרגום עברי'};
  const findings=currentJob.settings.model==='demo'?[]:chunk.findings||[];
  $('review-findings').textContent=findings.length?'נקודות לבדיקה: '+findings.map(f=>(labels[f.type]||'דורש בדיקה')+(f.source_token?' ('+f.source_token+')':'')).join(' · '):'';
}
async function saveEdit(showMessage=true){
  $('save-edit').disabled=true;
  try{currentJob=await request('/document-review',{job_id:currentJob.job_id,chunk_index:chunkIndex,target_text:$('review-target').value,expected_revision:currentJob.revision});
    if(showMessage)$('review-message').textContent='השינויים נשמרו. ההורדה כוללת את הגרסה המעודכנת.';return true;
  }catch(error){$('review-message').textContent=error.message;return false}finally{$('save-edit').disabled=false}
}
async function download(format){
  if(dirty()&&!await saveEdit())return;
  const button=$(format==='html'?'download-html':'download-text');button.disabled=true;
  try{const blob=await request('/document-download',{job_id:currentJob.job_id,format},true);
    const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=currentJob.filename.replace(/\.[^.]+$/,'')+'.he.'+format;
    document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
  }catch(error){$('result-notice').hidden=false;$('result-notice').textContent=error.message}finally{button.disabled=false}
}
async function sample(){
  if(busy)return;setBusy(true);message('');
  try{const file=await request('/document-sample');$('model').value='demo';setUploaded(file);setBusy(false);await translate();}
  catch(error){message(error.message);setBusy(false)}
}
async function initialize(){
  for(const [key,id] of Object.entries({model:'model',quality:'quality',language:'language',budget_usd:'budget'})){
    $(id).value=preferences[key];if($(id).value==='')$(id).value=defaults[key];
    $(id).addEventListener('change',updateSettings);
  }
  updateSettings();
  try{const config=await request('/document-config');keyAvailable=config.api_key_available;renderConnection()}catch(error){message(error.message)}
  let last;try{last=localStorage.getItem('document-last-job')}catch(_){}
  if(last){setBusy(true);show('processing-panel');currentJob={filename:'המסמך האחרון',status:'queued',total_chunks:0,completed_chunks:0};renderProcessing();await poll(last)}
  else{try{const result=await request('/document-recent');if(result.job){$('recent-button').hidden=false;$('recent-button').textContent='חזרה ל־'+result.job.filename;
    $('recent-button').onclick=()=>{remember('document-last-job',result.job.job_id);setBusy(true);show('processing-panel');poll(result.job.job_id)}}}catch(_){}}
}
$('drop-zone').onclick=()=>{if(!busy)$('document-file').click()};
$('drop-zone').onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();if(!busy)$('document-file').click()}};
$('document-file').onchange=()=>uploadFile($('document-file').files[0]);
for(const kind of ['dragenter','dragover'])$('drop-zone').addEventListener(kind,event=>{event.preventDefault();$('drop-zone').classList.add('dragging')});
for(const kind of ['dragleave','drop'])$('drop-zone').addEventListener(kind,event=>{event.preventDefault();$('drop-zone').classList.remove('dragging');if(kind==='drop')uploadFile(event.dataTransfer.files[0])});
$('translation-form').onsubmit=translate;$('connection-button').onclick=showConnection;
$('close-connection').onclick=()=>{$('api-key').value='';$('connection-dialog').close()};
$('connection-dialog').addEventListener('cancel',()=>{$('api-key').value=''});
$('save-key').onclick=()=>saveKey();$('clear-key').onclick=()=>saveKey(true);
$('sample-button').onclick=sample;$('download-html').onclick=()=>download('html');$('download-text').onclick=()=>download('txt');
$('review-button').onclick=()=>{if($('review-panel').hidden){$('review-panel').hidden=false;renderReview();$('review-panel').scrollIntoView({behavior:'smooth',block:'start'})}else if(confirmDiscard())$('review-panel').hidden=true};
$('close-review').onclick=()=>{if(confirmDiscard())$('review-panel').hidden=true};
$('chunk-select').onchange=()=>{if(confirmDiscard()){chunkIndex=Number($('chunk-select').value);renderReview()}else $('chunk-select').value=chunkIndex};
$('save-edit').onclick=()=>saveEdit();
$('new-document').onclick=()=>{if(!confirmDiscard())return;clearTimeout(pollTimer);forget('document-last-job');currentJob=null;uploaded=null;$('document-file').value='';$('review-panel').hidden=true;if($('model').value==='demo')$('model').value=defaults.model;show('start-panel');setUploaded(null);setBusy(false);message('');window.scrollTo({top:0,behavior:'smooth'})};
initialize();
