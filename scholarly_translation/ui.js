const {token}=window.UI_CONFIG;
const $=id=>document.getElementById(id);
let uploaded=null,currentJob=null,unitIndex=0,busy=false,pollTimer=null,modelConfigAvailable=false;
const defaults={profile:'scholarly',quality:'fast',language:'auto',budget_usd:2,model:'auto'};
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
function settings(){return {profile:$('profile').value,quality:$('quality').value,language:$('language').value,budget_usd:Number($('budget').value),model:$('model').value}}
function updateSettings(){
  preferences=settings();remember('document-preferences',JSON.stringify(preferences));
  $('profile-summary').textContent=$('profile').selectedOptions[0].textContent.split(' (')[0];
  $('quality-summary').textContent=$('quality').selectedOptions[0].textContent.split(' —')[0];
  $('model-summary').textContent=$('model').selectedOptions[0].textContent.split(' —')[0];
  const auto=preferences.model==='auto';
  $('translate-label').textContent=auto?'פתיחת תצוגת ניסיון':busy?'מעלה קובץ…':'תרגום לעברית';
  $('translate-button').disabled=!uploaded||busy;
  $('send-note').textContent=auto?'ללא עלות וללא תרגום אמיתי. יוצג טקסט מקום-שמור בלבד.':'לחיצה על תרגום תבקש אישור לשליחת הטקסט לספק המודל המוגדר.';
  $('budget').disabled=auto;
  $('quality-help').textContent=auto?'Auto תמיד מריץ ברמה מהירה (ללא בדיקה נוספת), ללא קשר לבחירה כאן.':
    preferences.quality==='fast'?'ללא קריאות בדיקה נוספות; המהיר והחסכוני ביותר.':
    preferences.quality==='checked'?'בדיקת מקטעים שסומנו כמסוכנים, ובדיקת פרקים בסוף כל פרק.':
    'בדיקת כל מקטע ובדיקת פרקים; המקיף והיקר ביותר.';
}
function setUploaded(file){
  uploaded=file;$('upload-empty').hidden=!!file;$('upload-selected').hidden=!file;
  if(file){$('filename').textContent=file.name;$('file-size').textContent=(file.size/1024/1024<1?Math.ceil(file.size/1024)+' KB':(file.size/1024/1024).toFixed(1)+' MB')+' · '+file.name.split('.').pop().toUpperCase()}
  updateSettings();
}
async function uploadFile(file){
  if(!file||busy)return;
  if(!/\.pdf$/i.test(file.name)||file.size===0||file.size>25*1024*1024){message('בחרו PDF עד 25 MB. EPUB אינו נתמך כרגע בזרימה זו.');return}
  setBusy(true);message('');
  try{const response=await fetch('/upload?name='+encodeURIComponent(file.name),{method:'POST',headers:{'X-UI-Token':token},body:file});
    const result=await response.json();if(!response.ok)throw Error(result.error||'העלאת הקובץ נכשלה');
    setUploaded({name:file.name,size:file.size,path:result.path});
  }catch(error){message(error.message)}finally{setBusy(false)}
}
function showConnection(){if(!$('connection-dialog').open)$('connection-dialog').showModal()}
function renderConnection(){
  $('connection-label').textContent='מודל: '+($('model').value==='configured'?'מוגדר':'Auto');
  $('connection-dot').classList.toggle('connected',modelConfigAvailable);
  $('connection-detail').textContent=modelConfigAvailable
    ?'קיים קובץ תצורת מודל בשרת. בחירת "מודל מוגדר" תשתמש בו לתרגום אמיתי.'
    :'לא הוגדר קובץ תצורת מודל בשרת כרגע; רק Auto (תצוגת ניסיון) זמין.';
}
async function translate(event){
  if(event)event.preventDefault();if(!uploaded||busy)return;message('');
  const chosen=settings(),auto=chosen.model==='auto';
  if(!auto&&!modelConfigAvailable){message('לא הוגדר מודל בשרת. בחרו Auto, או הגדירו קובץ תצורת מודל בשרת.');showConnection();return}
  if(!auto&&(!Number.isFinite(chosen.budget_usd)||chosen.budget_usd<0.01||chosen.budget_usd>30)){message('בחרו תקציב בין $0.01 ל־$30.');$('translation-options').open=true;$('budget').focus();return}
  if(!auto&&!confirm('לשלוח את הטקסט של '+uploaded.name+' לספק המודל המוגדר?\nפרופיל: '+chosen.profile+'\nרמת בדיקה: '+chosen.quality+'\nמגבלת אומדן מחירון: $'+chosen.budget_usd))return;
  setBusy(true);
  try{const result=await request('/document-translate',{path:uploaded.path,settings:chosen,paid_confirm:!auto});remember('document-last-job',result.job_id);
    currentJob={job_id:result.job_id,filename:uploaded.name,status:'queued',stage_label:'',completed_units:0,total_units:0};show('processing-panel');renderProcessing();await poll(result.job_id);
  }catch(error){show('start-panel');message(error.message);setBusy(false)}
}
function renderProcessing(){
  $('processing-title').textContent=currentJob.stage_label||'קוראים את המסמך…';
  $('processing-file').textContent=currentJob.filename;
  const progress=$('translation-progress');
  if(currentJob.total_units){progress.max=currentJob.total_units;progress.value=currentJob.completed_units;
    let detail=currentJob.completed_units+' מתוך '+currentJob.total_units+' מקטעים הושלמו.';
    if(currentJob.chapter_progress)detail='פרק '+currentJob.chapter_progress.current+' מתוך '+currentJob.chapter_progress.total+'. '+detail;
    $('processing-detail').textContent=detail+' אפשר לחזור לחלון הזה בהמשך.'}
  else{progress.removeAttribute('value');$('processing-detail').textContent='מחלצים את הטקסט ומכינים את התרגום.'}
}
async function poll(jobId){
  clearTimeout(pollTimer);
  try{const result=await request('/document-job',{job_id:jobId});currentJob=result;
    if(['queued','reading','translating','reviewing','rebuilding'].includes(result.status)){show('processing-panel');renderProcessing();pollTimer=setTimeout(()=>poll(jobId),1400)}
    else{setBusy(false);show('result-panel');renderResult();window.scrollTo({top:0,behavior:'smooth'})}
  }catch(error){if(error.status===400){forget('document-last-job');currentJob=null;setBusy(false);show('start-panel');message(error.message);return}
    $('processing-detail').textContent=error.message+' ננסה שוב לבדוק את מצב ההרצה.';pollTimer=setTimeout(()=>poll(jobId),5000)}
}
function renderResult(){
  const auto=currentJob.settings.model==='auto',complete=currentJob.status==='completed',partial=!complete&&currentJob.completed_units>0;
  $('result-title').textContent=auto?'תצוגת הניסיון מוכנה.':complete?'התרגום מוכן.':partial?'התרגום הושלם חלקית.':'התרגום לא הושלם.';
  $('result-symbol').textContent=auto?'↗':complete?'✓':'!';$('result-eyebrow').textContent=auto?'ללא קריאה לספק':'המסמך שלכם';
  $('result-filename').textContent=currentJob.filename;
  $('download-filename').textContent=currentJob.filename.replace(/\.[^.]+$/,'')+'.he.pdf';
  $('result-meta').textContent=(auto?'Auto — תצוגת ניסיון':'מודל מוגדר')+' · '+currentJob.completed_units+'/'+currentJob.total_units+' מקטעים';
  const notices=[];
  if(auto)notices.push('זו תצוגת ניסיון של הממשק בלבד. לא בוצע תרגום אמיתי.');
  if(currentJob.error)notices.push(currentJob.error);
  (currentJob.review_notes||[]).forEach(n=>notices.push(n));
  $('result-notice').textContent=notices.join(' · ');$('result-notice').hidden=!notices.length;
  const limitations=currentJob.export_limitations||[];
  $('result-limitations').textContent=limitations.length?'הערות על בניית ה-PDF: '+limitations.map(l=>l.detail||l.kind).join(' · '):'';
  $('result-limitations').hidden=!limitations.length;
  $('download-pdf').disabled=!complete;
  $('review-button').disabled=!complete;
  $('cost-summary').textContent=currentJob.estimated_cost_usd?'אומדן $'+currentJob.estimated_cost_usd.toFixed(4):auto?'ללא עלות':'';
  $('review-panel').hidden=true;$('unit-select').replaceChildren();
  for(const [index,unit] of (currentJob.units||[]).entries()){
    const option=document.createElement('option');option.value=index;option.textContent=(index+1)+' · '+(unit.status||'');$('unit-select').append(option)}
  unitIndex=0;
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
  const review=unit.review?(' · בדיקה: '+unit.review.verdict+(unit.review.issues&&unit.review.issues.length?' ('+unit.review.issues.length+' נקודות)':'')):'';
  $('review-findings').textContent=(findings.length?'נקודות לבדיקה: '+findings.map(f=>(labels[f.type]||'דורש בדיקה')+(f.source_token?' ('+f.source_token+')':'')).join(' · '):'')+review;
}
async function saveEdit(showMessage=true){
  $('save-edit').disabled=true;
  try{currentJob=await request('/document-review',{job_id:currentJob.job_id,unit_index:unitIndex,target_text:$('review-target').value,expected_revision:currentJob.revision});
    if(showMessage)$('review-message').textContent='השינויים נשמרו. ההורדה כוללת את הגרסה המעודכנת.';return true;
  }catch(error){$('review-message').textContent=error.message;return false}finally{$('save-edit').disabled=false}
}
async function download(){
  if(dirty()&&!await saveEdit())return;
  $('download-pdf').disabled=true;
  try{const blob=await request('/document-download',{job_id:currentJob.job_id,format:'pdf'},true);
    const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=currentJob.filename.replace(/\.[^.]+$/,'')+'.he.pdf';
    document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
  }catch(error){$('result-notice').hidden=false;$('result-notice').textContent=error.message}finally{$('download-pdf').disabled=false}
}
async function sample(){
  if(busy)return;setBusy(true);message('');
  try{const file=await request('/document-sample');$('model').value='auto';setUploaded(file);setBusy(false);await translate();}
  catch(error){message(error.message);setBusy(false)}
}
async function initialize(){
  for(const [key,id] of Object.entries({profile:'profile',quality:'quality',language:'language',budget_usd:'budget',model:'model'})){
    $(id).value=preferences[key];if($(id).value==='')$(id).value=defaults[key];
    $(id).addEventListener('change',updateSettings);
  }
  updateSettings();
  try{const config=await request('/document-config');modelConfigAvailable=config.model_config_available;renderConnection()}catch(error){message(error.message)}
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
$('sample-button').onclick=sample;$('download-pdf').onclick=download;
$('review-button').onclick=()=>{if($('review-panel').hidden){$('review-panel').hidden=false;renderReview();$('review-panel').scrollIntoView({behavior:'smooth',block:'start'})}else if(confirmDiscard())$('review-panel').hidden=true};
$('close-review').onclick=()=>{if(confirmDiscard())$('review-panel').hidden=true};
$('unit-select').onchange=()=>{if(confirmDiscard()){unitIndex=Number($('unit-select').value);renderReview()}else $('unit-select').value=unitIndex};
$('save-edit').onclick=()=>saveEdit();
$('new-document').onclick=()=>{if(!confirmDiscard())return;clearTimeout(pollTimer);forget('document-last-job');currentJob=null;uploaded=null;$('document-file').value='';$('review-panel').hidden=true;show('start-panel');setUploaded(null);setBusy(false);message('');window.scrollTo({top:0,behavior:'smooth'})};
initialize();
