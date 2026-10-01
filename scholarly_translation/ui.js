const {token,steps}=window.UI_CONFIG;
const $=id=>document.getElementById(id);
const stepByCommand=command=>steps.find(step=>step.command===command);
const workflow=[['Import','extract-pdf'],['Parse','structure'],['Terms','terminology'],['Translate','translate-unit'],['Review','human-review-render'],['Export','human-review-export']];
let saved={language:'en',provider:'mock',profile:'scholarly',control_store:'outputs/runtime_controls.sqlite3',max_calls:'3',hard_list_usd:'0.01'};
let selected=stepByCommand('translate-unit'),view='translate',lastResult=null,working=false;

function node(tag,attributes={},content=''){
  const element=document.createElement(tag);
  for(const [key,value] of Object.entries(attributes))element.setAttribute(key,value);
  element.textContent=content;
  return element;
}
function newOutput(command){return 'outputs/ui/'+command+'-'+new Date().toISOString().replace(/[-:TZ.]/g,'').slice(0,14)+'-'+crypto.randomUUID().slice(0,6)}
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
    button.onclick=()=>{if(command==='extract-pdf')navigate('library');else if(command==='terminology')navigate('glossary');else if(command==='human-review-render')navigate('review');else navigate('translate');chooseStep(command)};
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
  $('reader-section').hidden=destination==='library';
  if(destination==='library'){chooseStep('extract-pdf',previous!=='settings');refreshLibrary()}
  if(destination==='translate')chooseStep('translate-unit',previous!=='settings');
  if(destination==='glossary')chooseStep('terminology',previous!=='settings');
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
      button.onclick=()=>{saved.document_json=document.path;saved.document_path=document.path;navigate('translate');refreshPreview()};
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
  if(values.provider==='openai'&&!confirm('שלב זה עשוי לבצע קריאה בתשלום ל־OpenAI. להמשיך?'))return;
  working=true;$('run').disabled=true;$('open').disabled=true;lastResult=null;status('מריץ…');$('log').textContent='';
  try{
    const result=await request('/run',{command:step.command,values,output,paid_confirm:values.provider==='openai'});
    $('log').textContent=(result.stdout||'')+(result.stderr?'\n'+result.stderr:'');
    status(result.code===0?'השלב הושלם':'השלב נכשל (קוד '+result.code+')');
    if(result.code===0){
      Object.assign(saved,Object.fromEntries(Object.entries(values).filter(([,value])=>value)));
      const map={demo:{document_json:'document.json',document_path:'document.json'},'extract-pdf':{document_json:'document.json',document_path:'document.json'},
        structure:{structure_json:'structure.json'},terminology:{glossary:'glossary.json'},'translate-unit':{draft:'translation_draft.json'},
        'semantic-review':{review:'semantic_review.json'}};
      for(const [key,name] of Object.entries(map[step.command]||{}))saved[key]=joined(output,name);
      const decision=(result.stdout||'').match(/Wrote decision record: (.+)/);
      if(decision)saved.record=decision[1].trim();
      lastResult=decision?decision[1].trim():step.result?joined(output,step.result):
        ['inspect','inspect-structure','runtime-status'].includes(step.command)?null:output;
      $('open').disabled=!lastResult;
      await refreshPreview();
      if(view==='library')await refreshLibrary();
    }
  }catch(error){status('שגיאה: '+error.message)}
  finally{working=false;$('run').disabled=false}
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
    await runCommand(step,{input:path,language:saved.language||'en'},$('output').value.trim());
    if(saved.document_json)navigate('translate');
  }catch(error){status('ייבוא נכשל: '+error.message)}
}
async function openResult(){
  if(!lastResult)return;
  try{await request('/open',{path:lastResult})}catch(error){status(error.message)}
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
  bindSettings();renderForm();renderProgress();refreshPreview();
}
start();
