const {token}=window.UI_CONFIG;
const $=id=>document.getElementById(id);
function esc(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}

const LANGUAGE_NAMES={fr:'צרפתית',de:'גרמנית',es:'ספרדית',yi:'יידיש',it:'איטלקית'};
const ERROR_MESSAGES={
  invalid_budget:'יש להזין תקציב חיובי. אפשר להגדיל את התקציב ולהמשיך.',
  budget_cannot_decrease:'בחידוש אפשר לשמור את התקציב או להגדיל אותו; ההוצאה הקודמת נשארת בחישוב.',
  budget_exhausted:'התקציב אינו מספיק לקריאה הבאה. הקטעים שהתקבלו נשמרו; הגדילו את התקציב וחַדשו את ההכנה.',
  invalid_context:'היקף הקשר חייב להיות מספר שלם בין 0 לשני מיליון תווים. בחרו היקף אחר.',
  invalid_output_limit:'יש לבחור אורך תשובה חיובי בטוקנים.',
  output_capacity:'אורך התשובה שבחרתם גדול מיכולת המודל. הקטינו אותו וחַדשו את ההכנה.',
  context_capacity:'הקטע וההקשר חורגים מחלון המודל. הקטינו הקשר או אורך תשובה; הטקסט אינו נחתך אוטומטית.',
  response_incomplete:'תשובת המודל נקטעה או נכשלה ונשמרה כפי שהתקבלה. הגדילו אורך תשובה או תקציב ובחרו ניסיון חדש מפורש.',
  retry_confirmation_required:'התשובה הקודמת נכשלה או שתוצאת הקריאה אינה ידועה. נשמר התיעוד; אפשר לבחור ניסיון חדש, שעלול לגרור חיוב נוסף.',
  invalid_generation:'התשובה לא עמדה בחוזה ולכן לא שולבה. התשובה הגולמית נשמרה; אפשר לשנות הגדרות ולבחור ניסיון חדש.',
  archive_save_failed:'הספר זמין לקריאה, אך שמירת המילון או הסברי הדקדוק בתיקייה האישית נכשלה. פנו מקום או בדקו הרשאות ופתחו שוב את הפרק.',
  accounting_unavailable:'תיעוד העלויות אינו זמין או פגום. נתוני הקריאה נשמרו; יש לשחזר את התיעוד לפני יצירה נוספת כדי לשמור על התקציב.',
  invalid_export_format:'בחרו EPUB או HTML לייצוא.',
  invalid_export_options:'אפשרויות הייצוא אינן תקינות.',
  invalid_preserved_epub:'עותק ה־EPUB השמור פגום או לא תואם לספר. הייצוא נעצר; אפשר לייבא מחדש או לבטל שמירת עיצוב ולייצא טקסט.',
  preservation_unavailable:'לא ניתן לשלב בבטחה את המילים בעיצוב המקור. אפשר לבטל את שמירת העיצוב ולייצא את כל הטקסט והסיכומים בעימוד חדש.',
  invalid_export_text:'הטקסט מכיל תו שאינו מתאים לקובץ ספר. הייצוא נעצר בלי לחתוך את הטקסט.',
  invalid_export_coverage:'לא ניתן לאמת שהייצוא מכיל את כל הספר. נתוני הספר נשמרו והייצוא נעצר.',
  corrupt_store:'נתוני הספר אינם תואמים לגרסה שנשמרה. הייצוא נעצר כדי שלא להוריד ספר פגום.',
  export_failed:'לא ניתן להשלים את ההורדה. נתוני הספר נשמרו; נסו שוב.',
  active_book_conflict:'יש ספר פעיל אחד בלבד; יש לסיים או לנטוש אותו לפני התחלת ספר נוסף.',
  session_not_found:'ההפעלה לא נמצאה.',
  already_running:'ההכנה כבר רצה.',
  invalid_status:'לא ניתן לבצע פעולה זו במצב הנוכחי.',
  stale_learner:'מצב הלמידה השתנה; רעננו את העמוד.',
  unavailable_level:'רמת המאמץ אינה זמינה.',
  unsupported_language:'השפה שנבחרה אינה נתמכת.',
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
let glossTarget=null;

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
  const selector=$('learning-language');selector.replaceChildren();
  for(const lang of state.languages){
    const option=document.createElement('option');option.value=lang.id;
    option.textContent=LANGUAGE_NAMES[lang.id]||lang.id;option.disabled=!lang.available;
    selector.append(option);
  }
  selector.value=state.selected_language||state.learner.language;selector.disabled=active;
  $('effort-note').textContent=active?'לא ניתן לשנות רמת מאמץ בזמן שספר פעיל.':'בחרו את קצב שילוב החומר החדש. החזרה על מילים מוכרות מצטברת מעבר לכך.';
  const host=$('effort-levels');host.replaceChildren();
  const labels={'1':'1 — עד 10% חומר חדש','2':'2 — עד 20% חומר חדש','3':'3 — עד 30% חומר חדש וביטויים קצרים'};
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

$('learning-language').onchange=async()=>{
  const selector=$('learning-language');selector.disabled=true;
  try{
    await request('/learning/language',{language:selector.value});
    closeGloss();activeReader=null;chapterRequest++;$('reader-section').hidden=true;
    document.body.classList.remove('reading','progress-open');$('progress-return').hidden=true;
    $('reader-progress').setAttribute('aria-expanded','false');await loadState();
  }catch(error){selector.value=state.selected_language||state.learner.language;
    selector.disabled=!!state.learner.active_book_id;
    $('import-error').textContent=error.message;$('import-error').hidden=false}
};

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
  if(usage.accounting_unavailable)return errorText('accounting_unavailable');
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
    if(job){
      body.append(noteParagraph(`נשמרו ${job.accepted_chunks} מתוך ${job.total_chunks} קטעים; הקטעים שהתקבלו אינם נמחקים כשנעצרים.`));
      if(job.context_info)body.append(noteParagraph(`הקשר נוסף: ${job.context_info.provided_chars} תווים מתוך ${job.context_info.available_chars} הזמינים, לפי בקשת ${job.context_info.requested_chars} תווים. אפשר לשנות בחידוש.`));
      if(job.usage?.held_usd>0)body.append(noteParagraph(`חיוב שאינו ודאי עדיין שמור בחישוב התקציב: $${job.usage.held_usd.toFixed(4)}. ניסיון חדש עשוי לעלות בנוסף.`));
    }
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
      body.append(exportForm(session));
    }
    host.append(item);
  }
}
function noteParagraph(text){const p=document.createElement('p');p.className='muted';p.textContent=text;return p}
function errorParagraph(text){const p=document.createElement('p');p.className='message';p.setAttribute('role','alert');p.textContent=text;return p}
function exportForm(session){
  const form=document.createElement('form');form.className='export-form';
  form.innerHTML=`<label>פורמט ייצוא<select name="format"><option value="epub">EPUB לקורא ספרים</option><option value="html">HTML לקריאה בדפדפן ללא חיבור</option></select></label>
    <label><input name="meanings" type="checkbox" checked> קישורי פירוש בקובץ</label>
    <label><input name="preserve" type="checkbox" checked> שמירת עיצוב ותמונות המקור ב־EPUB</label>
    <button type="submit" class="secondary-button">הורדת ספר הלמידה</button>`;
  const message=document.createElement('p');message.className='muted';message.setAttribute('role','status');
  const book=state.books.find(entry=>entry.book_id===session.book_id);
  message.textContent=book?.epub_layout==='retained'?
    'EPUB משמר את התמונות, הגופנים והעיצוב ככל שניתן. HTML או ביטול שמירת העיצוב מפיקים טקסט בעימוד חדש. כולל סיכומי פרקים; תמיכה בפירושים תלויה בקורא. אחרי הקריאה חזרו לסמן קראתי.':
    'לקובץ זה אין עותק EPUB מקורי שמור: הייצוא יהיה טקסט בעימוד חדש, ללא תמונות המקור. אפשר לייבא מחדש כדי לשמר אותן. אחרי הקריאה חזרו לסמן קראתי.';
  form.append(message);
  form.onsubmit=async(event)=>{
    event.preventDefault();const button=form.querySelector('button');button.disabled=true;
    try{
      const response=await fetch('/learning/export',{method:'POST',headers:{'Content-Type':'application/json','X-UI-Token':token},
        body:JSON.stringify({session_id:session.session_id,format:form.querySelector('[name=format]').value,
                             include_meanings:form.querySelector('[name=meanings]').checked,
                             preserve_layout:form.querySelector('[name=preserve]').checked})});
      if(!response.ok){const result=await response.json();throw Error(errorText(result.code))}
      const blob=await response.blob();
      const expected=response.headers.get('Content-Length');
      if(!blob.size||(expected&&blob.size!==Number(expected)))throw Error(errorText('export_failed'));
      const match=(response.headers.get('Content-Disposition')||'').match(/filename\*=UTF-8''([^;]+)/i);
      const url=URL.createObjectURL(blob),link=document.createElement('a');
      link.href=url;link.download=match?decodeURIComponent(match[1]):'learning.'+form.querySelector('[name=format]').value;
      document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
      const warning=response.headers.get('X-Learning-Export-Warnings');
      message.textContent=(warning?.includes('reflowed_text')?'הורד טקסט בעימוד חדש, ללא תמונות ועיצוב המקור. ':'הקובץ עם עיצוב המקור הוכן להורדה. ')+
        'אחרי סיום הקריאה מחוץ לאתר חזרו לסמן קראתי; ההורדה אינה שומרת השלמה.';
    }catch(error){message.textContent=Object.values(ERROR_MESSAGES).includes(error.message)?error.message:errorText('export_failed')}
    finally{button.disabled=false}
  };
  return form;
}
function prepareForm(book){
  const wrap=document.createElement('form');wrap.className='budget-form';
  const disabled=!!state.learner.active_book_id;
  wrap.innerHTML=`${preparationOptions(null,disabled)}
    <button type="submit" class="primary-button" ${disabled?'disabled':''}>הכן לקריאה</button>`;
  if(disabled)wrap.append(noteParagraph('יש לסיים או לנטוש את הספר הפעיל לפני הכנת ספר נוסף.'));
  wrap.onsubmit=async(event)=>{
    event.preventDefault();
    const button=wrap.querySelector('button');button.disabled=true;
    try{await request('/learning/prepare',{book_id:book.book_id,...optionsFrom(wrap)});await loadState()}
    catch(error){wrap.append(errorParagraph(error.message));button.disabled=false}
  };
  return wrap;
}
function resumeForm(session,job){
  const wrap=document.createElement('form');wrap.className='budget-form';
  wrap.innerHTML=`${preparationOptions(job,false)}
    <label><input name="retry" type="checkbox"> ניסיון חדש לקטע שלא התקבל — עלול לגרור חיוב נוסף</label>
    <button type="submit" class="primary-button">חידוש הכנה</button>`;
  wrap.onsubmit=async(event)=>{
    event.preventDefault();
    const payload={session_id:session.session_id,...optionsFrom(wrap),retry:wrap.querySelector('[name=retry]').checked};
    try{await request('/learning/resume',payload);await loadState()}
    catch(error){wrap.append(errorParagraph(error.message))}
  };
  return wrap;
}
function preparationOptions(job,disabled){
  const attrs=disabled?'disabled':'';
  return `<label>תקציב כולל מרבי ($)<input name="budget" type="number" min="0.000001" step="any" value="${esc(job?.budget_usd??'')}" required dir="ltr" ${attrs}></label>
    <label>היקף הקשר נוסף (תווים)<input name="context" type="number" min="0" max="2000000" step="1" value="${job?.context_chars??4000}" required dir="ltr" ${attrs}></label>
    <label>אורך תשובה מותר (טוקנים)<input name="output" type="number" min="1" step="1" value="${job?.output_tokens??6000}" required dir="ltr" ${attrs}></label>`;
}
function optionsFrom(form){return {budget_usd:Number(form.querySelector('[name=budget]').value),
  context_chars:Number(form.querySelector('[name=context]').value),output_tokens:Number(form.querySelector('[name=output]').value)}}
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
  $('personal-archive').textContent=state.personal_archive?`המילון והסברי הדקדוק נשמרים בתיקייה: ${state.personal_archive.path}`:'';
  $('archive-warning').hidden=!state.personal_archive?.warning;
  if(state.personal_archive?.warning)$('archive-warning').textContent=errorText(state.personal_archive.warning);
  const progress=state.progress||(state.summary&&state.summary.progress)||null;
  if(!progress){
    // staged compatibility: older servers may not yet send the progress field.
    const count=state.learner.items.reduce((sum,row)=>sum+row.introduced_count,0);
    $('progress-summary').textContent=`ספרים שקראת: ${state.learner.completed_books.length} · מילים ומבנים שפגשת: ${state.learner.items.length} · הופעות בקריאה: ${count}.`;
    $('progress-detail').hidden=true;
    return;
  }
  $('progress-detail').hidden=false;
  $('progress-summary').textContent=`ספרים שקראת: ${state.learner.completed_books.length} · מילים שנשמרו: ${progress.completed_word_count} · מבנים שנשמרו: ${progress.completed_structure_count} · מילים בקטלוג הנוכחי: ${progress.catalog_word_count}.`;
  const goal=progress.initial_word_goal,completed=progress.completed_word_count;
  $('progress-milestone').textContent=completed>=goal?
    `עברתם את אבן הדרך הראשונה של ${goal} מילים — הלמידה ממשיכה בלי תקרה קבועה.`:
    `אבן הדרך הראשונה: ${completed} מתוך ${goal} מילים. זו התחלה, לא תקרה סופית.`;
  const current=progress.active_book;
  $('progress-current-book').hidden=!current;
  if(current){
    $('progress-current-title').textContent=current.title;
    $('progress-current-counts').textContent=
      `הוכנו ${current.prepared_chunks} מתוך ${current.total_chunks} קטעים`+
      (current.chapter_index!=null?` · פרק ${current.chapter_index+1} מתוך ${current.chapter_count}`:' · טרם התחילה קריאה');
  }
  renderVocabLists(progress);
}

function renderVocabLists(progress){
  const query=($('vocab-search').value||'').trim().normalize('NFC').toLocaleLowerCase(state.learner.language);
  const savedMap=new Map();
  for(const item of progress.completed_items||[])savedMap.set(item.item_id,item);
  const currentMap=new Map();
  if(progress.active_book)for(const item of progress.active_book.read_items||[])currentMap.set(item.item_id,item);
  const ids=new Set([...savedMap.keys(),...currentMap.keys()]);
  const words=[],grammar=[];
  for(const id of ids){
    const saved=savedMap.get(id),current=currentMap.get(id);
    const base=saved||current;
    if(query&&!base.foreign.normalize('NFC').toLocaleLowerCase(state.learner.language).includes(query)&&!base.hebrew.includes(query))continue;
    (base.kind==='grammar'?grammar:words).push({base,saved,current});
  }
  const byForeign=(a,b)=>a.base.foreign.localeCompare(b.base.foreign);
  renderVocabColumn($('vocab-words-list'),words.sort(byForeign),query);
  renderVocabColumn($('vocab-grammar-list'),grammar.sort(byForeign),query);
}
function renderVocabColumn(host,rows,query){
  host.replaceChildren();
  if(!rows.length){
    const empty=document.createElement('li');empty.className='muted';
    empty.textContent=query?'לא נמצאו פריטים מתאימים.':'עדיין אין פריטים כאן.';
    host.append(empty);return;
  }
  for(const row of rows){
    const li=document.createElement('li');li.className='vocab-item';
    const foreign=document.createElement('bdi');foreign.dir=state.learner.language==='yi'?'rtl':'ltr';
    foreign.lang=state.learner.language;foreign.textContent=row.base.foreign;
    const hebrew=document.createElement('span');hebrew.textContent=' — '+row.base.hebrew;
    const tags=document.createElement('span');tags.className='vocab-tags';
    if(row.saved){
      const tag=document.createElement('span');tag.className='tag available';
      tag.textContent=row.saved.last_book_title?`נשמר מ-${row.saved.last_book_title} (${row.saved.encounters})`:`נשמר (${row.saved.encounters})`;
      tags.append(tag);
    }
    if(row.current){
      const tag=document.createElement('span');tag.className='tag';
      tag.textContent=`בספר הנוכחי — טרם נשמר (${row.current.encounters})`;
      tags.append(tag);
    }
    li.append(foreign,hebrew,tags);
    host.append(li);
  }
}
$('vocab-search').oninput=()=>{
  const progress=state&&(state.progress||(state.summary&&state.summary.progress));
  if(progress)renderVocabLists(progress);
};

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
  document.body.classList.remove('progress-open');$('progress-return').hidden=true;
  $('reader-section').hidden=false;window.scrollTo({top:0,behavior:'auto'});
  loadChapter(activeReader.chapter_index);
}
$('reader-close').onclick=()=>{closeGloss();$('reader-section').hidden=true;activeReader=null;chapterRequest++;document.body.classList.remove('reading','progress-open');$('progress-return').hidden=true;$('reader-progress').setAttribute('aria-expanded','false');$('books-title').scrollIntoView({behavior:'auto'})};
$('reader-progress').onclick=async()=>{
  const reader=activeReader;
  try{await loadState();if(activeReader!==reader||!reader)return;
    closeGloss();document.body.classList.add('progress-open');$('progress-return').hidden=false;
    $('reader-progress').setAttribute('aria-expanded','true');$('progress-title').scrollIntoView({behavior:'auto'});
  }catch(error){$('import-error').textContent=error.message;$('import-error').hidden=false}
};
$('progress-return').onclick=()=>{document.body.classList.remove('progress-open');$('progress-return').hidden=true;$('reader-progress').setAttribute('aria-expanded','false');$('reader-title').scrollIntoView({behavior:'auto'})};
$('reader-prev').onclick=()=>{if(activeReader&&activeReader.chapter_index>0)loadChapter(activeReader.chapter_index-1)};
$('reader-next').onclick=()=>{if(activeReader&&activeReader.chapter_index<activeReader.chapter_count-1)loadChapter(activeReader.chapter_index+1)};

async function loadChapter(index){
  const reader=activeReader, serial=++chapterRequest;
  closeGloss();
  $('reader-prev').disabled=true;$('reader-next').disabled=true;
  try{
    const result=await request('/learning/read',{session_id:reader.session_id,chapter_index:index,
      gloss_on_click:$('reader-gloss').checked});
    if(activeReader!==reader||serial!==chapterRequest)return;
    activeReader.chapter_index=result.chapter_index;activeReader.chapter_count=result.chapter_count;
    activeReader.prepared_hash=result.session.prepared_hash;
    activeReader.language=result.language||result.session.language;
    $('reader-export').replaceChildren(exportForm(result.session));
    $('reader-title').textContent=result.title;
    $('reader-chapter-title').textContent=result.chapter_title;
    $('reader-position').textContent=`פרק ${result.chapter_index+1} מתוך ${result.chapter_count}`;
    $('reader-prev').disabled=result.chapter_index===0;
    $('reader-next').disabled=result.chapter_index>=result.chapter_count-1;
    $('reader-html').innerHTML=result.html;
    if(result.archive_warning){$('import-error').textContent=errorText(result.archive_warning);$('import-error').hidden=false}
    activeReader.completed=result.session.status==='completed';
    $('complete-button').disabled=activeReader.completed;
    $('complete-button').textContent=activeReader.completed?'הספר כבר סומן כקראתי':'קראתי את הספר';
    renderRecap(result.recap,result.items);
    await request('/learning/cursor',{session_id:activeReader.session_id,chapter_index:result.chapter_index});
    if(activeReader!==reader||serial!==chapterRequest)return;
    await loadState();
    $('completion-message').textContent='';
  }catch(error){$('import-error').textContent=error.message;$('import-error').hidden=false}
}

// Meanings are revealed only on request, in a separate panel; no model call.
function closeGloss(restoreFocus=false){
  const target=glossTarget;
  if(target)target.setAttribute('aria-expanded','false');
  glossTarget=null;$('gloss-popup').hidden=true;
  if(restoreFocus&&target?.isConnected)target.focus();
}
function showGloss(target){
  if(glossTarget===target){closeGloss();return}
  closeGloss();glossTarget=target;target.setAttribute('aria-expanded','true');
  $('gloss-word').textContent=target.textContent;
  $('gloss-word').dir=target.dir;$('gloss-word').lang=target.lang;
  $('gloss-meaning').textContent=target.getAttribute('data-gloss-he')||'אין פירוש זמין.';
  $('gloss-popup').hidden=false;
}
$('gloss-close').onclick=()=>closeGloss(true);
$('reader-gloss').onchange=()=>{if(activeReader)loadChapter(activeReader.chapter_index)};
$('reader-html').addEventListener('click',event=>{
  const target=event.target.closest('.learning-foreign-click');
  if(target)showGloss(target);
});
$('reader-html').addEventListener('keydown',event=>{
  const target=event.target.closest('.learning-foreign-click');
  if(target&&(event.key==='Enter'||event.key===' ')){event.preventDefault();showGloss(target)}
});
document.addEventListener('keydown',event=>{if(event.key==='Escape')closeGloss(true)});

function renderRecap(recap,items={}){
  const language=activeReader?.language||state.learner.language;
  const vocabHost=$('recap-vocabulary'),grammarHost=$('recap-grammar'),warningsHost=$('recap-warnings');
  vocabHost.replaceChildren();grammarHost.replaceChildren();warningsHost.replaceChildren();
  const vocabulary=recap.vocabulary||[],grammar=recap.grammar||[],warnings=recap.warnings||[];
  $('recap-empty').hidden=vocabulary.length>0||grammar.length>0;
  if($('recap-empty').hidden===false)$('recap-empty').textContent='לא נוספו פריטי לימוד חדשים בפרק זה.';
  for(const entry of vocabulary){
    const li=document.createElement('li'),foreign=document.createElement('bdi');
    foreign.dir=language==='yi'?'rtl':'ltr';foreign.lang=language;foreign.textContent=items[entry.item_id]?.lemma||entry.item_id;
    li.append(foreign,document.createTextNode(' — '+(entry.gloss_he||'')));vocabHost.append(li);
  }
  for(const entry of grammar){
    const li=document.createElement('li');li.textContent=entry.explanation_he||'';grammarHost.append(li);
    for(const example of entry.examples||[]){
      if(!example.foreign)continue;
      const row=document.createElement('li'),foreign=document.createElement('bdi');
      foreign.dir=language==='yi'?'rtl':'ltr';foreign.lang=language;foreign.textContent=example.foreign;
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
