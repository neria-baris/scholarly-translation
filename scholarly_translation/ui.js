const {token,steps}=window.UI_CONFIG;
const $=id=>document.getElementById(id);
const stepByCommand=command=>steps.find(step=>step.command===command);
const workflow=[['Import','extract-pdf'],['Parse','structure'],['Terms','terminology'],['Translate','translate-unit'],['Review','human-review-render'],['Export','human-review-export']];
let saved={language:'en',provider:'mock',profile:'scholarly',control_store:'outputs/runtime_controls.sqlite3',max_calls:'3',hard_list_usd:'0.01'};
let selected=stepByCommand('translate-unit'),view='translate',lastResult=null,working=false;
let sourceData=null,termData=null;

function node(tag,attributes={},content=''){
  const element=document.createElement(tag);
  for(const [key,value] of Object.entries(attributes))element.setAttribute(key,value);
  element.textContent=content;
  return element;
}
function newOutput(command){
  const directory='outputs/ui/'+command+'-'+new Date().toISOString().replace(/[-:TZ.]/g,'').slice(0,14)+'-'+crypto.randomUUID().slice(0,6);
  return command==='structure'?joined(directory,'structure.json'):directory;
}
function joined(directory,name){return directory.replace(/[\\/]+$/,'')+'/'+name}
async function request(path,data){
  const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-UI-Token':token},body:JSON.stringify(data)});
  const result=await response.json();
  if(!response.ok)throw Error(result.error||'הבקשה נכשלה');
  return result;
}
function status(message){ $('status').textContent=message; }
function collectForm(){
  if(!selected)return;
  for(const field of selected.fields){const input=$('field-'+field.key);if(input&&input.value.trim())saved[field.key]=input.value.trim()}
}
function chooseStep(command,preserveCurrent=true){
  if(preserveCurrent)collectForm();selected=stepByCommand(command)||selected;renderForm();renderProgress();
}
function renderProgress(){
  $('progress').replaceChildren();
  const current=workflow.findIndex(([,command])=>command===selected.command);
  for(const [index,[label,command]] of workflow.entries()){
    const button=node('button',{type:'button',class:index===current?'current':index<current?'complete':''},label);
    button.onclick=()=>{if(command==='extract-pdf')navigate('library');else if(command==='structure')navigate('source');else if(command==='terminology')navigate('glossary');else if(command==='human-review-render')navigate('review');else navigate('translate');chooseStep(command)};
    $('progress').append(button);
  }
}
function renderForm(){
  $('step-title').textContent=selected.title;
  $('step-help').textContent=selected.help;
  $('step-select').replaceChildren();
  for(const step of steps)$('step-select').append(node('option',{value:step.command},step.title));
  $('step-select').value=selected.command;
  $('step-form').replaceChildren();
  for(const field of selected.fields){
    const box=node('div',{class:'field'+(field.kind==='text'?' full':'')});
    box.append(node('label',{for:'field-'+field.key},field.label+(field.required?' *':'')));
    const row=node('div',{class:'fileline'});let input;
    if(field.values.length){
      input=node('select',{id:'field-'+field.key});
      for(const value of field.values)input.append(node('option',{value},value));
      input.value=saved[field.key]||field.values[0];
    }else{
      input=node('input',{id:'field-'+field.key,type:'text',dir:'ltr',autocomplete:'off'});
      input.value=saved[field.key]||'';
    }
    input.onchange=()=>{saved[field.key]=input.value.trim()};
    row.append(input);
    if(field.kind==='file'){
      const picker=node('input',{type:'file','aria-label':'בחר קובץ עבור '+field.label});
      picker.onchange=async()=>{if(!picker.files[0])return;try{status('מעלה קובץ…');input.value=await upload(picker.files[0]);saved[field.key]=input.value;status('הקובץ נשמר מקומית')}catch(error){status('העלאה נכשלה: '+error.message)}};
      row.append(picker);
    }
    box.append(row);$('step-form').append(box);
  }
  $('output-row').hidden=['inspect','inspect-structure','runtime-status'].includes(selected.command);
  $('output-row').querySelector('label').textContent=selected.command==='structure'?'קובץ מבנה חדש':'תיקיית פלט חדשה';
  $('output').value=newOutput(selected.command);
}
async function upload(file){
  const response=await fetch('/upload?name='+encodeURIComponent(file.name),{method:'POST',headers:{'X-UI-Token':token},body:file});
  const result=await response.json();
  if(!response.ok)throw Error(result.error||'ההעלאה נכשלה');
  return result.path;
}
function navigate(destination){
  const previous=view;
  view=destination;
  document.querySelectorAll('[data-view]').forEach(button=>button.classList.toggle('active',button.dataset.view===destination));
  $('workspace-view').hidden=destination==='settings';
  $('settings-view').hidden=destination!=='settings';
  $('library-section').hidden=destination!=='library';
  $('source-editor').hidden=destination!=='source';
  $('glossary-editor').hidden=destination!=='glossary';
  $('reader-section').hidden=destination==='library';
  if(destination==='library'){chooseStep('extract-pdf',previous!=='settings');refreshLibrary()}
  if(destination==='source'){chooseStep('structure',previous!=='settings');refreshSourceOptions()}
  if(destination==='translate')chooseStep('translate-unit',previous!=='settings');
  if(destination==='glossary'){chooseStep('terminology',previous!=='settings');refreshGlossaryOptions()}
  if(destination==='review')chooseStep('human-review-render',previous!=='settings');
  if(destination==='settings')refreshKeyStatus();
}
async function refreshLibrary(){
  try{
    const result=await request('/library',{});$('library-list').replaceChildren();
    if(!result.documents.length){$('library-list').append(node('p',{class:'muted'},'עדיין אין מסמכים שיובאו דרך הממשק.'));return}
    for(const document of result.documents){
      const button=node('button',{class:'library-item',type:'button'});
      button.append(node('strong',{},document.title),node('small',{},document.language+' · '+document.pages+' עמודים'));
      button.onclick=()=>{
        if(saved.document_json!==document.path){
          for(const key of ['structure_json','structure_ocr','glossary','unit_id','draft','review','record','decisions','ocr'])delete saved[key];
        }
        saved.document_json=document.path;saved.document_path=document.path;navigate('source');refreshPreview();
      };
      $('library-list').append(button);
    }
  }catch(error){$('library-list').textContent=error.message}
}
async function refreshPreview(){
  try{
    const result=await request('/preview',{document_json:saved.document_json||'',structure_json:saved.structure_json||'',
      draft:saved.draft||'',review:saved.review||'',unit_id:saved.unit_id||''});
    if(!result.loaded)return;
    $('document-title').textContent=result.title;
    $('document-meta').textContent=(result.language||'מקור')+' → עברית · '+(result.document_id||'');
    $('source-language').textContent=(result.language||'').toUpperCase();
    $('source-text').textContent=result.source_text||'מקור נטען, אך אין טקסט שניתן להציג.';
    $('source-text').dir=result.language==='he'?'rtl':'ltr';
    $('translation-text').textContent=result.translation_text||'עדיין אין טיוטת תרגום למקטע זה.';
    $('translation-stat').textContent=result.translation_status==='mock_placeholder'?'דוגמת mock · לא תרגום':
      result.translation_status==='not_started'?'ממתין לתרגום':result.translation_status;
    $('source-stat').textContent=result.source_status==='resolved'?'קריאה נבחרה · טעונה בדיקה':result.source_status;
    $('unit-select').replaceChildren(node('option',{value:''},'מקטע מקור'));
    for(const [index,unit] of result.units.entries())$('unit-select').append(node('option',{value:unit.unit_id},'מקטע '+(index+1)+(unit.page_number?' · עמוד '+unit.page_number:'')));
    $('unit-select').value=result.unit_id||'';
    if(result.unit_id)saved.unit_id=result.unit_id;
  }catch(error){status('לא ניתן לטעון תצוגה: '+error.message)}
}
async function runCommand(step,values,output){
  if(working)return;
  if(values.provider==='openai'&&!confirm('שלב זה עשוי לבצע קריאה בתשלום ל־OpenAI. להמשיך?'))return false;
  working=true;$('run').disabled=true;$('open').disabled=true;lastResult=null;status('מריץ…');$('log').textContent='';
  try{
    const result=await request('/run',{command:step.command,values,output,paid_confirm:values.provider==='openai'});
    $('log').textContent=(result.stdout||'')+(result.stderr?'\n'+result.stderr:'');
    status(result.code===0?'השלב הושלם':'השלב נכשל (קוד '+result.code+')');
    if(result.code===0){
      if(['demo','extract-pdf'].includes(step.command)){
        for(const key of ['structure_json','structure_ocr','glossary','unit_id','draft','review','record','decisions','ocr'])delete saved[key];
      }
      if(step.command==='structure'){
        for(const key of ['glossary','unit_id','draft','review','record'])delete saved[key];
      }
      if(step.command==='terminology'){
        for(const key of ['draft','review','record'])delete saved[key];
      }
      Object.assign(saved,Object.fromEntries(Object.entries(values).filter(([,value])=>value)));
      const map={demo:{document_json:'document.json',document_path:'document.json'},'extract-pdf':{document_json:'document.json',document_path:'document.json'},
        'ocr-pdf':{ocr:'ocr.json'},structure:{structure_json:''},terminology:{glossary:'glossary.json'},'translate-unit':{draft:'translation_draft.json'},
        'semantic-review':{review:'semantic_review.json'}};
      for(const [key,name] of Object.entries(map[step.command]||{}))saved[key]=name?joined(output,name):output;
      if(step.command==='structure')saved.structure_ocr=values.ocr||'';
      const decision=(result.stdout||'').match(/Wrote decision record: (.+)/);
      if(decision)saved.record=decision[1].trim();
      lastResult=decision?decision[1].trim():step.command==='structure'?output:step.result?joined(output,step.result):
        ['inspect','inspect-structure','runtime-status'].includes(step.command)?null:output;
      $('open').disabled=!lastResult;
      await refreshPreview();
      if(view==='library')await refreshLibrary();
      if(step.command==='structure')await refreshSourceOptions();
      if(step.command==='terminology')await refreshGlossaryOptions();
    }
    return result.code===0;
  }catch(error){status('שגיאה: '+error.message)}
  finally{working=false;$('run').disabled=false}
  return false;
}
function runSelected(){
  collectForm();const values={};for(const field of selected.fields)values[field.key]=($('field-'+field.key)?.value||'').trim();
  runCommand(selected,values,$('output').value.trim());
}
async function importPdf(){
  const file=$('pdf-upload').files[0];if(!file){status('יש לבחור קובץ PDF');return}
  try{
    status('מעלה PDF מקומית…');const path=await upload(file);saved.input=path;
    const step=stepByCommand('extract-pdf');chooseStep(step.command);
    const succeeded=await runCommand(step,{input:path,language:saved.language||'en'},$('output').value.trim());
    if(succeeded)navigate('source');
  }catch(error){status('ייבוא נכשל: '+error.message)}
}
async function openResult(){
  if(!lastResult)return;
  try{await request('/open',{path:lastResult})}catch(error){status(error.message)}
}
async function refreshSourceOptions(){
  sourceData=null;$('source-candidates').replaceChildren();$('source-page').replaceChildren();
  if(!saved.structure_json){$('source-guidance').textContent='לחצו על הכנת מועמדים אחרי חילוץ PDF. הבחירה נבדקת מול טקסט המקור והראיות.';return}
  try{
    sourceData=await request('/source-options',{structure_json:saved.structure_json});
    for(const reading of sourceData.readings){
      const label='עמוד '+reading.page_number+' · '+(reading.status==='resolved'?'נבחרה קריאה':'ממתין להכרעה');
      $('source-page').append(node('option',{value:reading.page_id},label));
    }
    $('source-guidance').textContent=sourceData.readings.length?'בחרו חלופת מקור אחרי בדיקה מול ה־PDF או תמונת העמוד.':'אין עמודים לבחירה.';
    renderSourceCandidates();
  }catch(error){$('source-guidance').textContent='לא ניתן לטעון מועמדים: '+error.message}
}
function renderSourceCandidates(){
  $('source-candidates').replaceChildren();
  const reading=sourceData?.readings.find(item=>item.page_id===$('source-page').value);
  if(!reading)return;
  for(const [index,candidate] of reading.alternatives.entries()){
    const card=node('label',{class:'candidate-card'+(candidate.usable?'':' unusable')});
    const radio=node('input',{type:'radio',name:'source-candidate',value:candidate.candidate_hash});
    if(!candidate.usable)radio.disabled=true;
    if(reading.selected?.candidate_hash===candidate.candidate_hash ||
       (!reading.selected&&candidate.usable&&!reading.alternatives.slice(0,index).some(item=>item.usable)))radio.checked=true;
    card.append(radio,node('strong',{},candidate.origin==='ocr'?'קריאת OCR':'חילוץ דיגיטלי'));
    card.append(node('small',{},candidate.warnings.join(' · ')||'ללא אזהרות נוספות'));
    card.append(node('pre',{},candidate.text||'לא נמצא טקסט קריא'));
    $('source-candidates').append(card);
  }
}
async function prepareSource(){
  if(!saved.document_json){$('source-status').textContent='יש לייבא PDF תחילה';return}
  if(saved.structure_json&&saved.structure_ocr===(saved.ocr||'')){
    $('source-status').textContent='מועמדי המקור כבר מוכנים';await refreshSourceOptions();return;
  }
  const step=stepByCommand('structure');
  const succeeded=await runCommand(step,{document_json:saved.document_json,ocr:saved.ocr||'',
    decisions:saved.decisions||'',previous:saved.structure_json||''},joined(newOutput('source-options'),'structure.json'));
  if(succeeded)await refreshSourceOptions();
}
async function saveSource(){
  const candidate=document.querySelector('input[name="source-candidate"]:checked');
  if(!sourceData||!candidate){$('source-status').textContent='יש לבחור קריאת מקור זמינה';return}
  $('save-source').disabled=true;$('source-status').textContent='בודק ושומר…';
  try{
    const result=await request('/source-decide',{structure_json:saved.structure_json,document_json:saved.document_json,
      ocr:saved.ocr||'',expected_revision:sourceData.revision,page_id:$('source-page').value,
      candidate_hash:candidate.value,actor:$('source-actor').value.trim(),reason:$('source-reason').value.trim()});
    saved.structure_json=result.structure_json;saved.decisions=result.decisions_json;
    for(const key of ['glossary','unit_id','draft','review','record'])delete saved[key];
    $('source-status').textContent='ההכרעה נשמרה כגרסת מבנה חדשה';
    $('log').textContent=result.stdout||'';await refreshSourceOptions();await refreshPreview();renderForm();
  }catch(error){$('source-status').textContent='ההכרעה לא נשמרה: '+error.message}
  finally{$('save-source').disabled=false}
}
async function refreshGlossaryOptions(){
  termData=null;$('term-unit').replaceChildren();$('term-rules').replaceChildren();
  if(!saved.structure_json){$('term-guidance').textContent='יש לבחור קריאת מקור לפני הצעת מונחים.';return}
  try{
    termData=await request('/glossary-options',{structure_json:saved.structure_json,glossary:saved.glossary||''});
    for(const [index,unit] of termData.units.entries())$('term-unit').append(node('option',{value:unit.unit_id},'מקטע '+(index+1)+' · '+unit.language));
    if(saved.unit_id&&termData.units.some(unit=>unit.unit_id===saved.unit_id))$('term-unit').value=saved.unit_id;
    $('term-guidance').textContent=termData.units.length?'העתיקו מונח מדויק מהמקטע. תחולת ברירת המחדל היא המקטע הזה.':'אין מקטע מקור פתור; יש להכריע את המקור תחילה.';
    renderTermSource();renderRules();
  }catch(error){$('term-guidance').textContent='לא ניתן לטעון מילון: '+error.message}
}
function renderTermSource(){
  const unit=termData?.units.find(item=>item.unit_id===$('term-unit').value);
  $('term-source').textContent=unit?.text||'';
  if(unit){saved.unit_id=unit.unit_id;refreshPreview()}
}
function renderRules(){
  $('term-rules').replaceChildren();
  if(!termData?.rules.length){$('term-rules').append(node('p',{class:'muted'},'אין עדיין מונחים במילון.'));return}
  for(const rule of termData.rules){
    const card=node('div',{class:'rule-card'}),description=node('div');
    description.append(node('strong',{},rule.source_term+' → '+rule.target_term));
    description.append(node('small',{},rule.status+' · גרסה '+rule.version+(rule.loaded?' · מונח טעון':'')));
    const target=node('input',{type:'text','aria-label':'תרגום מעודכן עבור '+rule.source_term,dir:'rtl'});
    target.value=rule.target_term;
    const actions=node('div',{class:'rule-actions'});
    const approve=node('button',{type:'button'},'אשר');approve.onclick=()=>reviewTerm(rule,'approved',target.value);
    const reject=node('button',{type:'button'},'דחה');reject.onclick=()=>reviewTerm(rule,'rejected',target.value);
    actions.append(approve,reject);card.append(description,target,actions);$('term-rules').append(card);
  }
}
async function proposeTerm(){
  if(!termData){$('term-status').textContent='יש לטעון מבנה מקור קודם';return}
  const occurrence=Number($('term-occurrence').value);
  $('propose-term').disabled=true;$('term-status').textContent='שומר הצעה…';
  try{
    const result=await request('/glossary-action',{kind:'propose',structure_json:saved.structure_json,
      glossary:saved.glossary||'',unit_id:$('term-unit').value,source_term:$('term-source-term').value,
      target_term:$('term-target').value,occurrence,scope:$('term-scope').value,loaded:$('term-loaded').checked});
    saved.glossary=result.glossary;$('term-status').textContent='המונח נוסף כהצעה ממתינה לאישור';
    $('log').textContent=result.stdout||'';await refreshGlossaryOptions();renderForm();
  }catch(error){$('term-status').textContent='ההצעה לא נשמרה: '+error.message}
  finally{$('propose-term').disabled=false}
}
async function reviewTerm(rule,decision,target){
  $('term-status').textContent='שומר החלטת מילון…';
  try{
    const result=await request('/glossary-action',{kind:'review',structure_json:saved.structure_json,
      glossary:saved.glossary,rule_id:rule.rule_id,expected_version:rule.version,
      expected_fingerprint:rule.fingerprint,actor:$('term-actor').value.trim(),
      reason:$('term-reason').value.trim(),status:decision,target_term:target});
    saved.glossary=result.glossary;$('term-status').textContent=decision==='approved'?'המונח אושר בידי הבודק/ת':'המונח נדחה בידי הבודק/ת';
    $('log').textContent=result.stdout||'';await refreshGlossaryOptions();renderForm();
  }catch(error){$('term-status').textContent='ההחלטה לא נשמרה: '+error.message}
}
async function refreshKeyStatus(){
  try{const result=await request('/settings',{});$('key-status').textContent=result.api_key_available?'מפתח זמין להרצה המקומית':'אין מפתח זמין לסשן'}
  catch(error){$('key-status').textContent=error.message}
}
async function setKey(clear=false){
  const key=clear?'':$('setting-api-key').value.trim();
  try{const result=await request('/settings',{api_key:key});$('setting-api-key').value='';
    $('key-status').textContent=result.api_key_available?'מפתח זמין להרצה המקומית':'המפתח נוקה מהסשן'}
  catch(error){$('key-status').textContent=error.message}
}
function bindSettings(){
  const inputs={provider:'setting-provider',language:'setting-language',max_calls:'setting-max-calls',hard_list_usd:'setting-hard-list-usd',
    control_store:'setting-control-store',tesseract:'setting-tesseract',tessdata_dir:'setting-tessdata'};
  for(const [key,id] of Object.entries(inputs)){
    $(id).value=saved[key]||'';
    $(id).onchange=()=>{saved[key]=$(id).value.trim();if(key==='provider')renderForm()};
  }
  $('save-key').onclick=()=>setKey(false);$('clear-key').onclick=()=>setKey(true);
}
function start(){
  document.querySelectorAll('[data-view]').forEach(button=>button.onclick=()=>navigate(button.dataset.view));
  $('step-select').onchange=()=>chooseStep($('step-select').value);
  $('unit-select').onchange=()=>{saved.unit_id=$('unit-select').value;refreshPreview()};
  $('run').onclick=runSelected;$('open').onclick=openResult;$('import-button').onclick=importPdf;
  $('prepare-source').onclick=prepareSource;$('source-page').onchange=renderSourceCandidates;
  $('save-source').onclick=saveSource;$('term-unit').onchange=renderTermSource;
  $('propose-term').onclick=proposeTerm;
  bindSettings();renderForm();renderProgress();refreshPreview();
}
start();
