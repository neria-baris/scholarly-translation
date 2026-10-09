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
  learning_save_failed:'קובץ השמירה נעול. השמירה לא הושלמה; העותק הקודם וקובץ ביניים מלא נשמרו. סגרו תוכנה שמשתמשת בקובץ ונסו שוב.',
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
  book_not_found:'הספר לא נמצא; רעננו את הדף.',
  invalid_title:'יש להזין שם באורך 1 עד 500 תווים.',
  invalid_model:'המודל או רמת האיכות שנבחרו אינם זמינים ללמידה.',
  book_in_use:'הספר נמצא בלמידה פעילה. יש לסיים או לנטוש אותו לפני מחיקה.',
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
  const waiting=Object.values(state.jobs).some(j=>j.auto_retry&&j.auto_retry.retry_at);
  if(waiting||state.sessions.some(s=>s.status==='preparing'))pollTimer=setTimeout(async()=>{
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
  return {imported:'לא הוכן',preparing:'בהכנה',ready:'מוכן לקריאה',paused:'מושהה',
    failed:'נעצר',completed:'נקרא',}[status]||status;
}
function usageLine(usage){
  if(!usage)return'';
  if(usage.accounting_unavailable)return errorText('accounting_unavailable');
  return `עלות עד כה: $${usage.list_estimated_spent_usd.toFixed(4)} (לפי מחירון) · ${usage.attempted_calls} קריאות למודל`+
    (usage.held_usd>0?` · עוד $${usage.held_usd.toFixed(4)} שמורים לקריאה שתוצאתה לא ידועה`:'');
}
function element(tag,className,text){const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node}
function button(text,kind,onclick){const node=element('button',kind,text);node.type='button';node.onclick=onclick;return node}
function noteParagraph(text){return element('p','muted',text)}
function errorParagraph(text){const p=element('p','message',text);p.setAttribute('role','alert');return p}
async function act(body,work){try{await work();await loadState()}catch(error){body.append(errorParagraph(error.message))}}

function renderBooks(){
  const host=$('books-list');host.replaceChildren();
  $('books-empty').hidden=state.books.length>0;
  const rank=book=>{const status=sessionForBook(book.book_id)?.status;
    return status&&status!=='completed'?0:status==='completed'?2:1};
  for(const book of [...state.books].sort((a,b)=>rank(a)-rank(b))){
    const session=sessionForBook(book.book_id);
    const job=session?state.jobs[session.session_id]:null;
    const status=session?session.status:'new';
    const item=element('li','book-item');item.dataset.status=status;
    const head=element('div','book-head');
    const title=element('strong',null,book.title);title.dir='auto';
    head.append(title,element('span','status-badge',session?bookStatusLabel(status):'לא הוכן'),bookMenu(book,item));
    head.querySelector('.status-badge').dataset.status=status;
    const body=element('div','book-body');
    item.append(head,body);
    const blocked=!session&&!!state.learner.active_book_id;
    item.classList.toggle('blocked',blocked);
    body.append(blocked?noteParagraph('לא הוכן. אפשר להכין אותו אחרי שמסיימים או נוטשים את הספר שבהכנה או בקריאה.'):statusLine(session,job));
    if(job&&job.total_chunks&&['preparing','paused','failed'].includes(status))body.append(progressBar(job));
    const actions=element('div','book-actions-row');body.append(actions);
    if(!session){
      if(!blocked)actions.append(button('הכנה לקריאה…','secondary-button',()=>{actions.replaceChildren();body.append(prepareForm(book))}));
    }else if(status==='preparing'){
      actions.append(button('השהיה','secondary-button',()=>act(body,()=>request('/learning/pause',{session_id:session.session_id}))));
    }else if(['imported','paused','failed'].includes(status)){
      if(job?.auto_retry?.retry_at)
        actions.append(button('ביטול הניסיון האוטומטי','secondary-button',()=>act(body,()=>request('/learning/pause',{session_id:session.session_id}))));
      else if(job?.error_code==='budget_exhausted')actions.append(budgetForm(session,job,'הגדלת התקציב והמשך'));
      else actions.append(button('המשך הכנה','primary-button',()=>act(body,()=>
        request('/learning/resume',{session_id:session.session_id,retry:status==='failed'}))));
      body.append(moreOptions(session,job));
    }else{
      const read=button(status==='completed'?'קריאה חוזרת':(session.read_cursor?'המשך קריאה':'התחלת קריאה'),'primary-button',()=>openReader(session,book));
      actions.append(read);
      const download=element('details','more');download.append(element('summary',null,'הורדת ספר הלמידה'),exportForm(session));
      body.append(download);
    }
    if(job)body.append(detailsBlock(book,job));
    host.append(item);
  }
}
function statusLine(session,job){
  if(!session)return noteParagraph('עדיין לא הוכן לקריאה. ההכנה משלבת מילים בשפה הנלמדת בתוך הטקסט העברי.');
  const done=job?`${job.accepted_chunks} מתוך ${job.total_chunks} קטעים`:'';
  const percent=job&&job.total_chunks?Math.floor(100*job.accepted_chunks/job.total_chunks)+'%':'';
  const retry=job?.auto_retry;
  switch(session.status){
    case 'preparing':
      return noteParagraph(job&&job.lessons_total&&job.accepted_chunks===job.total_chunks?
        `כותב שיעורי דקדוק: ${job.lessons_done} מתוך ${job.lessons_total} פרקים.`:`מכין את הספר: ${percent} (${done}).`);
    case 'paused': return noteParagraph(`ההכנה מושהית אחרי ${done}. מה שהוכן נשמר.`);
    case 'imported': return noteParagraph('ההכנה עוד לא התחילה.');
    case 'failed':
      if(retry?.retry_at){
        const seconds=Math.max(0,Math.round(retry.retry_at-Date.now()/1000));
        const line=element('p','retry-note',`תשובת המודל לא התקבלה כראוי. מנסה שוב אוטומטית בעוד ${seconds} שניות (ניסיון ${retry.count} מתוך 10).`);
        line.setAttribute('role','status');return line;
      }
      return errorParagraph(errorText(job?.error_code)+(retry?.stopped?` הניסיונות האוטומטיים נעצרו (${retry.count} ניסיונות, $${retry.wasted_usd.toFixed(4)}).`:''));
    case 'ready': return noteParagraph(session.read_cursor?`בקריאה: פרק ${session.read_cursor.chapter_index+1}.`:'מוכן לקריאה.');
    case 'completed': return noteParagraph('סימנת שקראת את הספר; המילים נשמרו להמשך.');
  }
  return noteParagraph(bookStatusLabel(session.status));
}
function progressBar(job){
  const bar=element('div','prep-progress');bar.setAttribute('role','progressbar');
  bar.setAttribute('aria-label','התקדמות ההכנה');bar.setAttribute('aria-valuemin','0');
  bar.setAttribute('aria-valuemax',String(job.total_chunks));bar.setAttribute('aria-valuenow',String(job.accepted_chunks));
  const fill=element('span');fill.style.width=Math.round(100*job.accepted_chunks/job.total_chunks)+'%';
  bar.append(fill);
  return bar;
}
function detailsBlock(book,job){
  const details=element('details','more');details.append(element('summary',null,'פרטים'));
  if(job.model)details.append(noteParagraph('מודל: '+modelLabel(job.model)+(job.model.reasoning?' · חשיבה: '+(REASONING_NAMES[job.model.reasoning]||job.model.reasoning):'')));
  if(job.budget_usd)details.append(noteParagraph(`תקציב מרבי: $${job.budget_usd}`));
  if(job.usage)details.append(noteParagraph(usageLine(job.usage)));
  details.append(noteParagraph(book.origin==='hebrew_epub'?'מקור: EPUB שהועלה.':'מקור: ספריית התרגומים.'));
  return details;
}
function moreOptions(session,job){
  const details=element('details','more');details.append(element('summary',null,'עוד אפשרויות'));
  if(job&&job.error_code!=='budget_exhausted')details.append(budgetForm(session,job,'שמירת תקציב והמשך'));
  details.append(noteParagraph('נטישה משחררת את הספר בלי לשמור התקדמות, כדי שאפשר יהיה להכין ספר אחר.'));
  details.append(button('נטישת הספר','secondary-button',()=>{
    if(confirm('לנטוש את הספר? ההתקדמות בו לא תישמר.'))act(details,()=>request('/learning/abandon',{session_id:session.session_id}))}));
  return details;
}
function budgetForm(session,job,label){
  const form=element('form','inline-form');
  form.innerHTML=`<label>תקציב מרבי ($)<input name="budget" type="number" min="${esc(job.budget_usd)}" step="any" value="${esc(job.budget_usd*(job.error_code==='budget_exhausted'?2:1))}" required dir="ltr"></label>
    <button type="submit" class="primary-button">${esc(label)}</button>`;
  form.onsubmit=event=>{event.preventDefault();act(form,()=>request('/learning/resume',{session_id:session.session_id,
    budget_usd:Number(form.querySelector('[name=budget]').value),retry:session.status==='failed'}))};
  return form;
}
function bookMenu(book,item){
  const menu=element('details','book-menu');
  const summary=element('summary',null,'⋯');summary.setAttribute('aria-label','פעולות על הספר');
  const list=element('div','book-menu-list');
  list.append(button('שינוי שם','quiet-button',()=>{
    const title=prompt('שם חדש לספר:',book.title);
    if(title===null||title.trim()===book.title)return;
    act(item,()=>request('/learning/rename-book',{book_id:book.book_id,title}));
  }),button('מחיקה מהרשימה','quiet-button',()=>{
    if(confirm(`למחוק את "${book.title}" מהרשימה? מילים שכבר נלמדו נשמרות.`))act(item,()=>request('/learning/delete-book',{book_id:book.book_id}));
  }));
  menu.append(summary,list);
  return menu;
}
function exportForm(session){
  const form=element('form','export-form');
  form.innerHTML=`<label>פורמט<select name="format"><option value="epub">EPUB לקורא ספרים</option><option value="html">HTML לדפדפן</option></select></label>
    <label><input name="meanings" type="checkbox" checked> פירוש בלחיצה בקובץ</label>
    <label><input name="preserve" type="checkbox" checked> שמירת העיצוב והתמונות של המקור</label>
    <button type="submit" class="secondary-button">הורדה</button>`;
  const message=element('p','muted');message.setAttribute('role','status');
  const book=state.books.find(entry=>entry.book_id===session.book_id);
  message.textContent=book?.epub_layout==='retained'?'אחרי קריאה מחוץ לאתר חזרו לכאן וסמנו "קראתי".':
    'לספר זה אין עותק EPUB מקורי שמור, לכן הקובץ יהיה טקסט בלי תמונות המקור. אחרי הקריאה חזרו לסמן "קראתי".';
  form.append(message);
  form.onsubmit=async(event)=>{
    event.preventDefault();const submit=form.querySelector('button');submit.disabled=true;
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
      message.textContent=(warning?.includes('reflowed_text')?'הורד טקסט בעימוד חדש, בלי תמונות ועיצוב המקור. ':'הקובץ הורד עם עיצוב המקור. ')+
        'ההורדה אינה מסמנת קריאה; אחרי הקריאה סמנו "קראתי".';
    }catch(error){message.textContent=Object.values(ERROR_MESSAGES).includes(error.message)?error.message:errorText('export_failed')}
    finally{submit.disabled=false}
  };
  return form;
}

// ---- model choice ----
const REASONING_NAMES={none:'בסיסית (בלי חשיבה)',low:'טובה (חשיבה קלה)',medium:'גבוהה (חשיבה בינונית)',
  high:'גבוהה מאוד (חשיבה רבה)',xhigh:'מעולה (חשיבה רבה מאוד)',max:'מרבית (איטית ויקרה)'};
const PROVIDER_NAMES={openai:'OpenAI',anthropic:'Anthropic'};
function modelLabel(model){
  const id=model.model;
  if(id.startsWith('claude-')){const [,family,...version]=id.split('-');return family.charAt(0).toUpperCase()+family.slice(1)+' '+version.join('.')}
  const name=id.replace(/^gpt-[\d.]+-/,'');
  return name.charAt(0).toUpperCase()+name.slice(1);
}
function prepareForm(book){
  const form=element('form','prepare-form');
  const models=state.models||[];
  const cheapest=Math.min(...models.map(m=>m.rates_per_million.output));
  const options=models.map(m=>{const ratio=m.rates_per_million.output/cheapest;
    return `<option value="${esc(m.model)}">${esc(modelLabel(m))} · ${PROVIDER_NAMES[m.provider]||m.provider} — ${ratio<1.01?'הזול ביותר':'יקר פי '+Math.round(ratio)}</option>`}).join('');
  form.innerHTML=`<div class="form-row">
      <label>מודל<select name="model">${options}</select></label>
      <label class="reasoning-field">איכות<select name="reasoning"></select></label>
      <label>תקציב מרבי ($)<input name="budget" type="number" min="0.000001" step="any" required dir="ltr" placeholder="למשל 5"></label>
    </div>
    <div class="key-field" hidden><label><span class="key-label"></span><input name="key" type="password" autocomplete="off" dir="ltr"></label>
      <p class="muted">המפתח נשמר בזיכרון השרת המקומי עד לכיבויו.</p></div>
    <p class="muted">מודל זול יותר מתאים לרוב הספרים; מודל יקר יותר בוחר מילים ומסביר דקדוק בדיוק רב יותר. ההקשר ואורך התשובה נקבעים אוטומטית, ותשובה שנכשלה נשלחת שוב מעצמה.</p>
    <div class="book-actions-row"><button type="submit" class="primary-button">התחלת ההכנה</button></div>`;
  const model=form.querySelector('[name=model]'),reasoning=form.querySelector('[name=reasoning]');
  const fill=()=>{
    const entry=models.find(m=>m.model===model.value);
    reasoning.innerHTML=entry.reasoning_values.map(v=>`<option value="${v}">${esc(REASONING_NAMES[v]||v)}</option>`).join('');
    reasoning.value=entry.default_reasoning||'';
    form.querySelector('.reasoning-field').hidden=!entry.reasoning_values.length;
    const missing=state.keys_available&&!state.keys_available[entry.provider];
    form.querySelector('.key-field').hidden=!missing;
    form.querySelector('[name=key]').required=!!missing;
    form.querySelector('.key-label').textContent=`מפתח ${PROVIDER_NAMES[entry.provider]||entry.provider} (חסר)`;
  };
  model.value=state.model;model.onchange=fill;fill();
  form.onsubmit=event=>{
    event.preventDefault();
    const entry=models.find(m=>m.model===model.value),key=form.querySelector('[name=key]');
    act(form,async()=>{
      if(!form.querySelector('.key-field').hidden&&key.value)await request('/model-keys',{keys:{[entry.provider]:key.value}});
      key.value='';
      await request('/learning/prepare',{book_id:book.book_id,budget_usd:Number(form.querySelector('[name=budget]').value),
        model:entry.model,...(entry.reasoning_values.length?{reasoning:reasoning.value}:{})});
    });
  };
  return form;
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
    const details=document.createElement('details'),summary=document.createElement('summary');
    summary.className='vocab-summary';summary.append(foreign,hebrew,tags);
    details.append(summary,entryBody(row.base));
    li.append(details);host.append(li);
  }
}
const PART_OF_SPEECH_HE={noun:'שם עצם',verb:'פועל',adjective:'שם תואר',adverb:'תואר הפועל',pronoun:'כינוי',
  preposition:'מילת יחס',conjunction:'מילת חיבור',determiner:'מגדיר (יידוע או כמות)',numeral:'שם מספר',
  interjection:'מילת קריאה',phrase:'ביטוי',other:'אחר'};
const GENDER_HE={masculine:'זכר',feminine:'נקבה',neuter:'סתמי',common:'זכר ונקבה'};
function foreignText(text){
  const node=document.createElement('bdi');node.dir=state.learner.language==='yi'?'rtl':'ltr';
  node.lang=state.learner.language;node.textContent=text;return node;
}
function entryBody(base){
  const body=document.createElement('div');body.className='vocab-entry';
  const line=(text,cls)=>{const p=document.createElement('p');p.textContent=text;if(cls)p.className=cls;body.append(p);return p};
  if(base.kind==='grammar'){
    line(base.explanation_he||'אין הסבר שמור למבנה זה.');
  }else if(base.entry){
    const entry=base.entry;
    line(PART_OF_SPEECH_HE[entry.part_of_speech]+(entry.gender?' · '+GENDER_HE[entry.gender]:''),'entry-kind');
    const senses=document.createElement('ol');senses.className='entry-senses';
    for(const sense of entry.senses_he){const li=document.createElement('li');li.textContent=sense;senses.append(li)}
    body.append(senses);
    if(entry.forms.length){
      const table=document.createElement('table');table.className='entry-forms';
      for(const form of entry.forms){
        const tr=document.createElement('tr'),label=document.createElement('th'),value=document.createElement('td');
        label.textContent=form.label_he;value.append(foreignText(form.form));tr.append(label,value);table.append(tr);
      }
      body.append(table);
    }
    if(entry.notes_he)line(entry.notes_he,'muted');
  }else{
    line('אין עדיין ערך מילוני לפריט זה. ערכים נוצרים בספרים שמוכנים מעכשיו, בפעם הראשונה שהמילה משולבת.','muted');
  }
  if((base.examples||[]).length){
    const title=document.createElement('p');title.className='entry-subtitle';title.textContent='מהספרים שקראתם';body.append(title);
    const list=document.createElement('ul');list.className='entry-examples';
    for(const example of base.examples){
      const li=document.createElement('li');li.textContent=example.sentence;
      if(example.book_title){const book=document.createElement('span');book.className='muted';book.textContent=' — '+example.book_title;li.append(book)}
      list.append(li);
    }
    body.append(list);
  }
  return body;
}

// ---- grammar notebook ----
let notebook=null;
$('notebook-open').onclick=async()=>{
  const section=$('grammar-notebook');
  if(!section.hidden){section.hidden=true;$('notebook-open').setAttribute('aria-expanded','false');return}
  section.hidden=false;$('notebook-open').setAttribute('aria-expanded','true');
  $('notebook-content').replaceChildren();$('notebook-status').textContent='טוען…';
  try{notebook=await request('/learning/grammar-notebook',{});renderNotebook()}
  catch(error){$('notebook-status').textContent=error.message}
};
$('notebook-search').oninput=()=>{if(notebook)renderNotebook()};
function renderNotebook(){
  const host=$('notebook-content');host.replaceChildren();
  const query=($('notebook-search').value||'').trim().toLocaleLowerCase();
  const matches=paragraph=>!query||[paragraph.heading_he,paragraph.text_he,
    ...paragraph.examples.flatMap(x=>[x.foreign,x.hebrew,x.note_he])].join(' ').toLocaleLowerCase().includes(query);
  let shown=0;
  for(const book of notebook.books){
    const bookSection=document.createElement('section');bookSection.className='notebook-book';
    const title=document.createElement('h3');title.dir='auto';title.textContent=book.title;bookSection.append(title);
    let bookShown=0;
    for(const chapter of book.chapters){
      const topicHit=query&&chapter.topics.some(t=>t.toLocaleLowerCase().includes(query));
      const paragraphs=chapter.paragraphs.filter(p=>topicHit||matches(p));
      if(!paragraphs.length)continue;
      const details=document.createElement('details');details.className='notebook-chapter';details.open=!!query;
      const summary=document.createElement('summary');
      summary.textContent=`פרק ${chapter.chapter_index+1}: ${chapter.chapter_title}`+(chapter.topics.length?` — ${chapter.topics.join(' · ')}`:'');
      details.append(summary);
      for(const paragraph of paragraphs){
        const heading=document.createElement('h4'),text=document.createElement('p');
        heading.textContent=paragraph.heading_he;text.textContent=paragraph.text_he;details.append(heading,text);
        if(paragraph.examples.length){
          const list=document.createElement('ul');list.className='lesson-examples';
          for(const example of paragraph.examples){
            const li=document.createElement('li'),foreign=foreignText(example.foreign);foreign.className='lesson-foreign';
            li.append(foreign,document.createTextNode(' — '+example.hebrew));
            if(example.note_he){const note=document.createElement('span');note.className='lesson-note';note.textContent=example.note_he;li.append(note)}
            list.append(li);
          }
          details.append(list);
        }
      }
      bookSection.append(details);bookShown++;shown++;
    }
    if(bookShown)host.append(bookSection);
  }
  $('notebook-status').textContent=notebook.books.length?(shown?'':'לא נמצאו שיעורים מתאימים.'):
    'עדיין אין שיעורי דקדוק. שיעורים נוצרים בספרים שמוכנים מעכשיו, פרק אחר פרק.';
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
  const remember=!$('learning-remember').hidden&&$('learning-remember-key').checked;
  try{await request('/model-keys',{keys:{[$('learning-key-provider').value]:value},...($('learning-remember').hidden?{}:{remember})});await loadState();
    $('key-message').textContent=remember?'המפתח נשמר במחשב (מנהל האישורים של Windows) ויישאר גם אחרי סגירת התוכנית.':'המפתח נשמר בזיכרון עד לכיבוי השרת.'}
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
  $('recap-empty').hidden=vocabulary.length>0||grammar.length>0||recap.lesson?.status==='ready';
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
  renderLesson(recap.lesson,language);
  for(const warning of warnings){
    const li=document.createElement('li');li.textContent=warning.code==='coverage_shortfall'?
      'חלק מהמילים המתוכננות לא התאימו לקטע, ולכן לא שולבו.':'חלק מההחלפות הושמטו בגלל משמעות לא ברורה.';
    if(![...warningsHost.children].some(x=>x.textContent===li.textContent))warningsHost.append(li);
  }
}

function renderLesson(lesson,language){
  const host=$('recap-lesson');host.replaceChildren();host.hidden=!lesson;
  if(!lesson)return;
  const title=document.createElement('h4');title.textContent='שיעור דקדוק לפרק';host.append(title);
  if(lesson.status!=='ready'){
    const note=document.createElement('p');note.className='muted';
    note.textContent='שיעור הדקדוק לפרק זה לא התקבל בצורה תקינה ולכן אינו מוצג.';host.append(note);return;
  }
  for(const paragraph of lesson.paragraphs||[]){
    const heading=document.createElement('h5'),text=document.createElement('p');
    heading.textContent=paragraph.heading_he;text.textContent=paragraph.text_he;host.append(heading,text);
    if(!(paragraph.examples||[]).length)continue;
    const list=document.createElement('ul');list.className='lesson-examples';
    for(const example of paragraph.examples){
      const li=document.createElement('li'),foreign=document.createElement('bdi');
      foreign.dir=language==='yi'?'rtl':'ltr';foreign.lang=language;foreign.className='lesson-foreign';foreign.textContent=example.foreign;
      li.append(foreign,document.createTextNode(' — '+example.hebrew));
      if(example.note_he){const note=document.createElement('span');note.className='lesson-note';note.textContent=example.note_he;li.append(note)}
      list.append(li);
    }
    host.append(list);
  }
  const disclaimer=document.createElement('p');disclaimer.className='muted';
  disclaimer.textContent='השיעור נכתב בעזרת המודל ולא עבר ביקורת לשונית נפרדת.';host.append(disclaimer);
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

request('/model-keys',{}).then(result=>{
  $('learning-remember').hidden=!result.remember_supported;
  $('learning-remember-key').checked=!!(result.saved&&result.saved.openai);
  if(result.saved&&result.saved.openai)$('key-message').textContent='מפתח OpenAI שמור במחשב.';
}).catch(()=>{});
(async function initialize(){
  try{await importFromQuery();await loadState()}
  catch(error){$('import-error').textContent=error.message;$('import-error').hidden=false}
})();
