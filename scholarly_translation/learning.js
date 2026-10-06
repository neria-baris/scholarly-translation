const {token}=window.UI_CONFIG;
const $=id=>document.getElementById(id);
function esc(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}

const LANGUAGE_NAMES={fr:'צרפתית',de:'גרמנית',es:'ספרדית',yi:'יידיש',it:'איטלקית'};
const ERROR_MESSAGES={
  invalid_budget:'תקציב לא תקין; יש להזין מספר חיובי עד 100$.',
  active_book_conflict:'יש ספר פעיל אחד בלבד; יש לסיים או לנטוש אותו לפני התחלת ספר נוסף.',
  session_not_found:'ההפעלה לא נמצאה.',
  already_running:'ההכנה כבר רצה.',
  invalid_status:'לא ניתן לבצע פעולה זו במצב הנוכחי.',
  stale_learner:'מצב הלמידה השתנה; רעננו את העמוד.',
  unavailable_level:'רמת המאמץ אינה זמינה.',
  missing_api_key:'יש להזין מפתח API לפני הכנת ספר.',
  state_conflict:'הפעולה לא תואמת את המצב הנוכחי; רעננו ונסו שוב.',
  book_not_ready:'הספר עדיין לא מוכן לקריאה.',
  invalid_cursor:'מיקום קריאה לא תקין.',
  unknown_action:'פעולה לא מוכרת.',
  unsupported_format:'יש להעלות קובץ EPUB.',
  incomplete_upload:'ההעלאה לא הושלמה.',
  wrong_language:'הספר אינו בעברית במידה מספקת.',
  no_hebrew_text:'לא נמצא טקסט עברי בספר.',
  empty_epub:'קובץ ה-EPUB ריק.',
  damaged_epub:'קובץ ה-EPUB פגום.',
  drm_protected:'קובץ ה-EPUB מוגן ואינו נתמך.',
  invalid_epub:'קובץ ה-EPUB אינו תקין.',
  oversized_epub:'הקובץ גדול מדי.',
  epub_import_failed:'לא ניתן לקלוט את הספר. בדקו שזה EPUB בעברית ללא הגנה.',
  unfinished_job:'התרגום בספרייה עדיין לא הושלם.',
  missing_target_text:'לתרגום חסר טקסט עברי.',
  invalid_job:'התרגום שנבחר אינו תקין.',
  invalid_learning_request:'פעולת הלמידה לא הושלמה.',
  budget_required:'יש להזין תקציב כדי להמשיך.',
  preparation_stopped:'ההכנה נעצרה.',
};
function errorText(code){return ERROR_MESSAGES[code]||'הפעולה לא הושלמה.'}

async function request(route,data={}){
  const response=await fetch(route,{method:'POST',headers:{'Content-Type':'application/json','X-UI-Token':token},body:JSON.stringify(data)});
  if(!response.ok){let result;try{result=await response.json()}catch(_){throw Error('לא ניתן להתחבר לשרת המקומי. הפעילו אותו שוב.')}
    throw Error(errorText(result.code)||result.error||'הפעולה לא הושלמה')}
  return response.json();
}

let state=null;
let activeReader=null; // {session_id, chapter_index, chapter_count, title}
let pollTimer=null, chapterRequest=0;

function completionKey(sessionId){return 'learning-completion-'+sessionId}
function completionIdFor(sessionId){
  let value=null;
  try{value=localStorage.getItem(completionKey(sessionId))}catch(_){}
  if(!value){
    value=(crypto.randomUUID?crypto.randomUUID():'c-'+Date.now()+'-'+Math.random().toString(16).slice(2)).replace(/[^A-Za-z0-9_.:@-]/g,'');
    try{localStorage.setItem(completionKey(sessionId),value)}catch(_){}
  }
  return value;
}

async function importFromQuery(){
  const params=new URLSearchParams(window.location.search);
  const jobId=params.get('job_id');
  if(!jobId)return;
  history.replaceState(null,'',window.location.pathname);
  try{await request('/learning/import-translation',{job_id:jobId})}
  catch(error){$('import-error').textContent=error.message;$('import-error').hidden=false}
}

async function loadState(){
  state=await request('/learning/state',{});
  renderEffort();
  renderLanguages();
  renderBooks();
  renderProgress();
  clearTimeout(pollTimer);
  if(state.sessions.some(s=>s.status==='preparing'))pollTimer=setTimeout(async()=>{
    try{await loadState()}catch(error){$('import-error').textContent=error.message;$('import-error').hidden=false}
  },2000);
}

// ---- effort ----
function renderEffort(){
  const active=!!state.learner.active_book_id;
  $('effort-note').textContent=active?'לא ניתן לשנות רמת מאמץ בזמן שספר פעיל.':'בחרו עד כמה טקסט בשפה הנלמדת יופיע בתוך הקריאה.';
  const host=$('effort-levels');host.replaceChildren();
  const labels={'1':'1 — עד 10%, פירוש לצד המילה','2':'2 — עד 20%, פירוש בלחיצה','3':'3 — עד 30%, ביטויים קצרים'};
  for(const level of state.levels){
    const button=document.createElement('button');
    button.type='button';button.className='level-button';button.setAttribute('role','radio');
    button.setAttribute('aria-checked',String(level.level_id===state.learner.level_id));
    button.textContent=labels[level.level_id]||('רמה '+level.level_id);
    button.disabled=active;
    button.onclick=async()=>{
      try{await request('/learning/effort',{level_id:level.level_id});await loadState()}
      catch(error){$('import-error').textContent=error.message;$('import-error').hidden=false}
    };
    host.append(button);
  }
}

// ---- languages / wordlists ----
function renderLanguages(){
  const host=$('language-list');host.replaceChildren();
  for(const lang of state.languages){
    const item=document.createElement('li');
    item.innerHTML=`<span>${esc(LANGUAGE_NAMES[lang.id]||lang.id)}</span>`+
      (lang.available?'<span class="tag available">פעיל ללמידה</span>':'<span class="tag">רשימת מילים בלבד — למידה עדיין לא זמינה</span>')+
      ` <a href="/learning/wordlist?language=${encodeURIComponent(lang.id)}" target="_blank" rel="noopener">רשימת 500 מילים</a>`;
    host.append(item);
  }
}

// ---- books ----
function sessionForBook(bookId){return state.sessions.filter(s=>s.book_id===bookId&&state.jobs[s.session_id]?.status!=='abandoned')
  .sort((a,b)=>b.base_learner_revision-a.base_learner_revision)[0]}
function bookStatusLabel(status){
  return {imported:'יובא, לא הוכן',preparing:'בהכנה',ready:'מוכן לקריאה',paused:'מושהה',
    failed:'נעצר עם שגיאה',completed:'הושלם',}[status]||status;
}
function usageLine(usage){
  if(!usage)return'';
  return `קריאות: ${usage.attempted_calls} · אומדן לפי מחירון: $${usage.list_estimated_spent_usd.toFixed(4)} · שמור לקריאות: $${usage.held_usd.toFixed(4)}`+
    (usage.stopped?' · נעצר':'');
}
function renderBooks(){
  const host=$('books-list');host.replaceChildren();
  $('books-empty').hidden=state.books.length>0;
  for(const book of state.books){
    const session=sessionForBook(book.book_id);
    const job=session?state.jobs[session.session_id]:null;
    const item=document.createElement('li');item.className='book-item';
    item.innerHTML=`<div class="book-head"><strong dir="auto">${esc(book.title)}</strong>`+
      `<span class="tag">${esc(book.origin==='hebrew_epub'?'EPUB':'מהספרייה')}</span>`+
      (session?`<span class="tag">${esc(bookStatusLabel(session.status))}</span>`:'<span class="tag">לא הוכן</span>')+
      `</div><div class="book-body"></div>`;
    const body=item.querySelector('.book-body');
    if(!session){
      body.append(prepareForm(book));
    }else if(['imported','paused','failed'].includes(session.status)){
      if(job&&job.error_code)body.append(noteParagraph(errorText(job.error_code)));
      body.append(resumeForm(session,job));
      if(['imported','paused','failed'].includes(session.status))body.append(abandonButton(session));
    }else if(session.status==='preparing'){
      body.append(noteParagraph(`הכנה: ${job?job.accepted_chunks:0}/${job?job.total_chunks:0} קטעים.`));
      if(job&&job.usage)body.append(noteParagraph(usageLine(job.usage)));
      const pause=document.createElement('button');pause.type='button';pause.className='secondary-button';
      pause.textContent='השהיית הכנה';pause.onclick=async()=>{try{await request('/learning/pause',{session_id:session.session_id});await loadState()}catch(error){body.append(errorParagraph(error.message))}};
      body.append(pause);
    }else if(session.status==='ready'||session.status==='completed'){
      if(job&&job.usage)body.append(noteParagraph(usageLine(job.usage)));
      const read=document.createElement('button');read.type='button';read.className='primary-button';
      read.textContent=session.status==='completed'?'קריאה חוזרת':(session.read_cursor?'המשך קריאה':'התחלת קריאה');
      read.onclick=()=>openReader(session,book);
      body.append(read);
    }
    host.append(item);
  }
}
function noteParagraph(text){const p=document.createElement('p');p.className='muted';p.textContent=text;return p}
function errorParagraph(text){const p=document.createElement('p');p.className='message';p.setAttribute('role','alert');p.textContent=text;return p}
function prepareForm(book){
  const wrap=document.createElement('form');wrap.className='budget-form';
  const disabled=!!state.learner.active_book_id;
  wrap.innerHTML=`<label>תקציב מרבי (${'$'})<input type="number" min="0.01" max="100" step="0.01" required dir="ltr" ${disabled?'disabled':''}></label>
    <button type="submit" class="primary-button" ${disabled?'disabled':''}>הכן לקריאה</button>`;
  if(disabled)wrap.append(noteParagraph('יש לסיים או לנטוש את הספר הפעיל לפני הכנת ספר נוסף.'));
  wrap.onsubmit=async(event)=>{
    event.preventDefault();
    const input=wrap.querySelector('input');const budget=Number(input.value);
    const button=wrap.querySelector('button');button.disabled=true;
    try{await request('/learning/prepare',{book_id:book.book_id,budget_usd:budget});await loadState()}
    catch(error){wrap.append(errorParagraph(error.message));button.disabled=false}
  };
  return wrap;
}
function resumeForm(session,job){
  const needsBudget=!job||job.budget_usd==null;
  const wrap=document.createElement('form');wrap.className='budget-form';
  wrap.innerHTML=needsBudget?
    `<label>תקציב מרבי ($)<input type="number" min="0.01" max="100" step="0.01" required dir="ltr"></label>
     <button type="submit" class="primary-button">חידוש הכנה</button>`:
    `<button type="submit" class="primary-button">חידוש הכנה</button>`;
  wrap.onsubmit=async(event)=>{
    event.preventDefault();
    const input=wrap.querySelector('input');
    const payload={session_id:session.session_id};
    if(input)payload.budget_usd=Number(input.value);
    try{await request('/learning/resume',payload);await loadState()}
    catch(error){wrap.append(errorParagraph(error.message))}
  };
  return wrap;
}
function abandonButton(session){
  const wrap=document.createElement('div');
  const note=document.createElement('p');note.className='muted';
  note.textContent='נטישה משחררת את מקום הספר הפעיל בלי לשמור התקדמות או השלמה.';
  const button=document.createElement('button');button.type='button';button.className='secondary-button';
  button.textContent='נטישת ספר';
  button.onclick=async()=>{
    if(!confirm('נטישת הספר תשחרר אותו בלי לשמור השלמה. להמשיך?'))return;
    try{await request('/learning/abandon',{session_id:session.session_id});await loadState()}
    catch(error){wrap.append(errorParagraph(error.message))}
  };
  wrap.append(note,button);
  return wrap;
}

function renderProgress(){
  const count=state.learner.items.reduce((sum,row)=>sum+row.introduced_count,0);
  $('progress-summary').textContent=`ספרים שקראת: ${state.learner.completed_books.length} · מילים ומבנים שפגשת: ${state.learner.items.length} · הופעות בקריאה: ${count}.`;
}

// ---- upload ----
$('epub-choose').onclick=()=>$('epub-file').click();
$('epub-file').onchange=async()=>{
  const file=$('epub-file').files[0];$('epub-file').value='';
  if(!file)return;
  $('upload-message').hidden=true;
  try{
    const response=await fetch('/learning/upload-epub?name='+encodeURIComponent(file.name),
      {method:'POST',headers:{'X-UI-Token':token},body:file});
    const result=await response.json();
    if(!response.ok)throw Error(errorText(result.code)||result.error);
    await loadState();
  }catch(error){$('upload-message').textContent=error.message;$('upload-message').hidden=false}
};

// ---- API key ----
$('save-key').onclick=async()=>{
  const value=$('learning-key').value;
  $('learning-key').value='';
  try{await request('/model-keys',{keys:{openai:value}});$('key-message').textContent='המפתח נשמר בזיכרון עד לכיבוי השרת.'}
  catch(error){$('key-message').textContent=error.message}
};

// ---- reader ----
function openReader(session,book){
  activeReader={session_id:session.session_id,chapter_index:session.read_cursor?session.read_cursor.chapter_index:0,book};
  document.body.classList.add('reading');
  $('reader-section').hidden=false;window.scrollTo({top:0,behavior:'auto'});
  loadChapter(activeReader.chapter_index);
}
$('reader-close').onclick=()=>{$('reader-section').hidden=true;activeReader=null;chapterRequest++;document.body.classList.remove('reading');$('books-title').scrollIntoView({behavior:'auto'})};
$('reader-prev').onclick=()=>{if(activeReader&&activeReader.chapter_index>0)loadChapter(activeReader.chapter_index-1)};
$('reader-next').onclick=()=>{if(activeReader&&activeReader.chapter_index<activeReader.chapter_count-1)loadChapter(activeReader.chapter_index+1)};

async function loadChapter(index){
  const reader=activeReader, serial=++chapterRequest;
  $('reader-prev').disabled=true;$('reader-next').disabled=true;
  try{
    const result=await request('/learning/read',{session_id:reader.session_id,chapter_index:index});
    if(activeReader!==reader||serial!==chapterRequest)return;
    activeReader.chapter_index=result.chapter_index;activeReader.chapter_count=result.chapter_count;
    activeReader.prepared_hash=result.session.prepared_hash;
    $('reader-title').textContent=result.title;
    $('reader-chapter-title').textContent=result.chapter_title;
    $('reader-position').textContent=`פרק ${result.chapter_index+1} מתוך ${result.chapter_count}`;
    $('reader-prev').disabled=result.chapter_index===0;
    $('reader-next').disabled=result.chapter_index>=result.chapter_count-1;
    $('reader-html').innerHTML=result.html;
    $('gloss-popup').hidden=true;
    activeReader.completed=result.session.status==='completed';
    $('complete-button').disabled=activeReader.completed;
    $('complete-button').textContent=activeReader.completed?'הספר כבר סומן כקראתי':'קראתי את הספר';
    renderRecap(result.recap,result.items);
    await request('/learning/cursor',{session_id:activeReader.session_id,chapter_index:result.chapter_index});
    $('completion-message').textContent='';
  }catch(error){$('import-error').textContent=error.message;$('import-error').hidden=false}
}

function renderRecap(recap,items={}){
  const vocabHost=$('recap-vocabulary'),grammarHost=$('recap-grammar'),warningsHost=$('recap-warnings');
  vocabHost.replaceChildren();grammarHost.replaceChildren();warningsHost.replaceChildren();
  const vocabulary=recap.vocabulary||[],grammar=recap.grammar||[],warnings=recap.warnings||[];
  $('recap-empty').hidden=vocabulary.length>0||grammar.length>0;
  if($('recap-empty').hidden===false)$('recap-empty').textContent='לא נוספו פריטי לימוד חדשים בפרק זה.';
  for(const entry of vocabulary){
    const li=document.createElement('li'),foreign=document.createElement('bdi');
    foreign.dir='ltr';foreign.lang='fr';foreign.textContent=items[entry.item_id]?.lemma||entry.item_id;
    li.append(foreign,document.createTextNode(' — '+(entry.gloss_he||'')));vocabHost.append(li);
  }
  for(const entry of grammar){
    const li=document.createElement('li');li.textContent=entry.explanation_he||'';grammarHost.append(li);
    for(const example of entry.examples||[]){
      if(!example.foreign)continue;
      const row=document.createElement('li'),foreign=document.createElement('bdi');
      foreign.dir='ltr';foreign.lang='fr';foreign.textContent=example.foreign;
      row.append(foreign,document.createTextNode(' — '+example.hebrew));grammarHost.append(row);
    }
  }
  if(!grammar.length){const li=document.createElement('li');li.textContent='בפרק זה לא הודגם מבנה דקדוקי חדש.';grammarHost.append(li)}
  for(const warning of warnings){
    const li=document.createElement('li');li.textContent=warning.code==='coverage_shortfall'?
      'חלק מהמילים המתוכננות לא התאימו לקטע, ולכן לא שולבו.':'חלק מההחלפות הושמטו בגלל משמעות לא ברורה.';
    if(![...warningsHost.children].some(x=>x.textContent===li.textContent))warningsHost.append(li);
  }
}

function toggleGloss(element){
  const next=element.nextElementSibling;
  if(next&&next.classList.contains('learning-gloss-toggle')){
    next.remove();element.setAttribute('aria-expanded','false');return;
  }
  const span=document.createElement('span');span.className='learning-gloss-toggle';span.setAttribute('dir','rtl');span.setAttribute('lang','he');
  span.textContent='('+(element.getAttribute('data-gloss-he')||'')+')';
  element.after(span);element.setAttribute('aria-expanded','true');
}
$('reader-html').addEventListener('click',(event)=>{
  const target=event.target.closest('.learning-foreign-click');
  if(target)toggleGloss(target);
});
$('reader-html').addEventListener('keydown',(event)=>{
  const target=event.target.closest('.learning-foreign-click');
  if(target&&(event.key==='Enter'||event.key===' ')){event.preventDefault();toggleGloss(target)}
});

$('complete-button').onclick=async()=>{
  if(!activeReader||activeReader.completed)return;
  const reader=activeReader;
  const button=$('complete-button');button.disabled=true;
  const completionId=completionIdFor(activeReader.session_id);
  try{
    const receipt=await request('/learning/complete',{session_id:activeReader.session_id,
      prepared_hash:activeReader.prepared_hash,completion_id:completionId});
    reader.completed=true;
    $('completion-message').textContent='המילים ורמת המאמץ נשמרו לספר הבא.';
    button.textContent='הספר סומן כקראתי';
    await loadState();
  }catch(error){
    try{await loadState();reader.completed=state.sessions.find(s=>s.session_id===reader.session_id)?.status==='completed'}catch(_){}
    $('completion-message').textContent=reader.completed?'המילים ורמת המאמץ נשמרו לספר הבא.':error.message;
  }
  finally{button.disabled=!!activeReader?.completed}
};

(async function initialize(){
  try{await importFromQuery();await loadState()}
  catch(error){$('import-error').textContent=error.message;$('import-error').hidden=false}
})();
