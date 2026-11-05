/* The library cat for the translation app: an illustrated puppet that roams the page.
   Local only: no network, voices or files; two small preferences in localStorage.
   Decorative: it never covers controls or reading text and never changes input. */
(() => {
  'use strict';

  // ---------- The cat: an illustrated puppet ----------
  // One SVG, two bodies (standing and sitting) and a shared head. Poses are CSS on data-pose,
  // so the walk cycle and pose changes move limbs smoothly instead of swapping frames.
  const GW = 32, GH = 24;
  const leg = (cls, x) => `<g class="c-leg ${cls}"><rect x="${x}" y="58" width="9.5" height="30" rx="4.75"/><ellipse class="paw" cx="${x + 4.75}" cy="86.4" rx="5.4" ry="2.8"/></g>`;
  const tail = (cls, d, tip) => `<g class="${cls}"><path class="t-out" d="${d}"/><path class="t-in" d="${d}"/><path class="t-stripe" d="${d}"/><path class="t-tip" d="${tip}"/></g>`;
  const CAT_SVG = `<svg class="cat-svg" viewBox="0 0 120 90" data-pose="sit" aria-hidden="true" focusable="false">
    <ellipse class="c-shadow" cx="60" cy="88.5" rx="36" ry="3.2"/>
    <g class="c-stand">
      ${tail('c-tail', 'M31 51 C17 50 9 37 15 22', 'M16.5 27 C15 25.5 14.7 23.5 15 22')}
      ${leg('far back', 38)}${leg('far front', 78)}
      <path class="c-fur" d="M26 54 C26 42 38 37.5 52 37.5 L72 37.5 C86 37.5 93 46 93 56 C93 66 85 70.5 72 70.5 L44 70.5 C32 70.5 26 64.5 26 54 Z"/>
      <path class="c-cream" d="M40 66.5 C50 71 70 71 82 66 C78 61.5 46 61.5 40 66.5 Z"/>
      <path class="c-stripes" d="M47 38.5 q3.5 6 0 11 M57 37.8 q3.5 7 0 12 M67 38.2 q3.5 6 0 10.5"/>
      ${leg('near back', 30)}${leg('near front', 70)}
    </g>
    <g class="c-sit">
      ${tail('c-tail-sit', 'M37 85.5 C52 92 78 90.5 95 83.5', 'M91.5 84.6 C93 84.1 94 83.8 95 83.5')}
      <path class="c-fur" d="M30 86.5 C19 85 19 68 28 58 C36 47 50 40 64 38 C79 36 87 48 86.5 62 C86.5 75 85.5 86.5 75 86.5 Z"/>
      <ellipse class="c-fur c-haunch" cx="41" cy="74" rx="16.5" ry="13"/>
      <path class="c-stripes" d="M33 66 q6 2.5 10.5 -2 M31 74.5 q6 2.5 10.5 -2"/>
      <ellipse class="c-cream c-belly" cx="78.5" cy="64" rx="6.5" ry="13.5"/>${leg('sit far', 65)}${leg('sit near', 74.5)}
      <ellipse class="c-cream c-chest" cx="77" cy="58" rx="8.5" ry="14"/>
      <ellipse class="paw" cx="37" cy="86.4" rx="7.5" ry="3"/>
    </g>
    <g class="c-head">
      <path class="c-fur" d="M81.5 30 L83 10.5 L96.5 21 Z"/><path class="c-ear-in" d="M85 25.5 L86 15.5 L93 21.5 Z"/>
      <path class="c-fur" d="M98.5 20.5 L112.5 9.5 L113.5 29.5 Z"/><path class="c-ear-in" d="M102 21 L110 14.5 L110.5 26 Z"/>
      <ellipse class="c-fur" cx="97" cy="34" rx="19.5" ry="16.8"/>
      <path class="c-stripes" d="M92 19.5 v5 M97 18.3 v6.2 M102 19.5 v5"/>
      <ellipse class="c-cream c-muzzle" cx="98" cy="41.2" rx="9.2" ry="6.2"/>
      <g class="eyes-open"><ellipse cx="90" cy="32" rx="3.4" ry="4.3"/><ellipse cx="104.5" cy="32" rx="3.4" ry="4.3"/><circle class="glint" cx="91.2" cy="30.4" r="1.25"/><circle class="glint" cx="105.7" cy="30.4" r="1.25"/></g>
      <path class="eyes-closed" d="M86.6 33 q3.4 2.6 6.8 0 M101.1 33 q3.4 2.6 6.8 0"/>
      <path class="eyes-happy" d="M86.6 34.2 q3.4 -4 6.8 0 M101.1 34.2 q3.4 -4 6.8 0"/>
      <ellipse class="blush" cx="84.5" cy="39.5" rx="3.6" ry="2.1"/><ellipse class="blush" cx="111.5" cy="39.5" rx="3.6" ry="2.1"/>
      <path class="c-nose" d="M95.3 37.6 h5.4 l-2.7 3.1 z"/>
      <path class="c-mouth" d="M98 40.6 q-1.6 3 -4.2 2 M98 40.6 q1.6 3 4.2 2"/>
      <ellipse class="c-yawn" cx="98" cy="44.2" rx="3.1" ry="3.7"/>
      <path class="c-whisk" d="M88.5 40.2 L73.5 37.2 M88.5 42.4 L73.8 43.6 M107.5 40.2 L122.5 37.2 M107.5 42.4 L122.2 43.6"/>
    </g></svg>`;

  // ---------- Words ----------
  const he = () => document.documentElement.lang !== 'en';
  const L = pair => pair[he() ? 0 : 1];
  const pick = list => list[Math.floor(Math.random() * list.length)];
  // Thoughts are drawn from a shuffled bag per topic: every line comes up once before any repeats,
  // and a new round never starts with the line that ended the last one.
  const bags = new Map();
  function draw(key, list) {
    if (!list || !list.length) return null;
    let bag = bags.get(key);
    if (!bag || !bag.items.length || bag.size !== list.length) {
      const order = list.map((_, i) => i);
      for (let i = order.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [order[i], order[j]] = [order[j], order[i]]; }
      if (bag && order.length > 1 && order[order.length - 1] === bag.last) order.push(order.shift());
      bag = { items: order, size: list.length, last: bag?.last };
      bags.set(key, bag);
    }
    bag.last = bag.items.pop();
    return list[bag.last];
  }
  const say = (key, list = LINES[key]) => { const line = draw(key, list); return line ? L(line) : ''; };
  // Inner monologue only: the cat thinks about the humans, he never addresses them.
  const LINES = {
    hello: [['הם חזרו. אולי הביאו חטיף.', 'The humans are back. Perhaps snacks.'],
      ['אני הספרן כאן. בערך.', 'I am the librarian here. Roughly.'],
      ['נכנסו בלי לדפוק. אופייני.', 'They came in without knocking. Typical.'],
      ['יום חדש, אותם מדפים. מצוין.', 'A new day, the same shelves. Excellent.'],
      ['הם פה. אעמיד פנים שלא שמתי לב.', 'They’re here. I shall pretend not to notice.'],
      ['המסך נדלק. הפיקוח מתחדש.', 'The screen lights up. Supervision resumes.']],
    morning: [['בוקר. השעה הרשמית לארוחת בוקר שנייה.', 'Morning. Officially time for second breakfast.'],
      ['קפה בשבילם, קרן שמש בשבילי.', 'Coffee for them, a sunbeam for me.']],
    afternoon: [['אחר הצהריים. השמש זזה, ואני זז אחריה.', 'Afternoon. The sun moves; I follow.'],
      ['שעת התנומה של אחר הצהריים. עוד מעט.', 'The afternoon nap hour approaches.']],
    evening: [['ערב. הספרים נעשים שקטים יותר.', 'Evening. The books grow quieter.'],
      ['האור במנורה חם. אשב לידה.', 'The lamp is warm. I’ll sit by it.']],
    night: [['הם עוד ערים. גם אני, אבל לי מותר: אני חתול.', 'They’re still up. So am I, but I’m allowed: I’m a cat.'],
      ['חצות. השעה שבה הספרים מדברים. או שזה המקרר.', 'Midnight, when books whisper. Or the fridge.']],
    idle: [['המדף הזה נבדק. נמצא מתאים לישיבה.', 'This shelf has been inspected. Approved for sitting.'],
      ['קראתי את כל הספרים כאן. בעיקר את הפינות.', 'I have read every book here. Mostly the corners.'],
      ['אם משהו ייפול מהמדף, זה לא אני. אלא אם כן זה אני.', 'If something falls off the shelf, it wasn’t me. Unless it was.'],
      ['הערת שוליים: אני.', 'Footnote: me.'],
      ['אין מילה ל״דדליין״ בשפת חתולים.', 'There is no word for “deadline” in Cat.'],
      ['לא ישנתי. עשיתי הגהה בעיניים עצומות.', 'Not asleep. Proofreading with my eyes closed.'],
      ['עברית, אנגלית, יפנית… ואני עדיין עונה רק ל״טונה״.', 'Hebrew, English, Japanese… and still I answer only to “tuna”.'],
      ['ריח של נייר ישן… ושל עכבר?', 'Old paper… and mouse?'],
      ['ספרתי את הספרים על המדף. יצא: הרבה.', 'I counted the books on the shelf. Result: many.'],
      ['שקט בספרייה. בדיוק כמו שאני אוהב.', 'Quiet in the library. Just how I like it.'],
      ['אם אשב מספיק זמן ליד מילון, אולי משהו ייקלט.', 'If I sit by a dictionary long enough, perhaps something soaks in.'],
      ['כל סימנייה היא צעצוע שעוד לא יודע את זה.', 'Every bookmark is a toy that hasn’t realised it yet.'],
      ['תרגום זה כמו ציד: סבלנות, ואז קפיצה.', 'Translation is like hunting: patience, then a pounce.'],
      ['המילה ״חתול״ מופיעה בספרים האלה פחות מדי.', 'The word “cat” appears far too rarely in these books.'],
      ['אני לא מתעצל. אני חוסך כוח לקפיצה הבאה.', 'Not lazy. Saving strength for the next jump.'],
      ['שמעתי שיש ספרים בלי חתולים. קשה להאמין.', 'I hear some books have no cats. Hard to believe.'],
      ['מישהו השאיר כאן פסיק. אני שומר עליו.', 'Someone left a comma here. I am guarding it.'],
      ['הכריכה הזאת בצבע של הפרווה שלי. לא במקרה.', 'This cover matches my fur. No coincidence.'],
      ['אבק על המדף העליון. אדווח להנהלה. אני ההנהלה.', 'Dust on the top shelf. I’ll tell management. I am management.'],
      ['פעם ישבתי על המקלדת. יצא שיר מודרני.', 'I once sat on a keyboard. It came out as modern poetry.'],
      ['הדף הבא תמיד מעניין יותר. במיוחד כשמישהו מחזיק אותו.', 'The next page is always more interesting. Especially while someone holds it.'],
      ['שבע נשמות, ואף אחת מהן לא מבינה בדקדוק.', 'Nine lives, and not one of them understands grammar.'],
      ['ניסיתי לקרוא מימין לשמאל ומשמאל לימין. נרדמתי באמצע.', 'I tried reading right to left and left to right. Fell asleep in the middle.'],
      ['הערות שוליים הן המקום הכי נעים בעמוד. נמוך וחמים.', 'Footnotes are the coziest part of a page. Low and warm.']],
    library: [['כל ספר כאן הוא כרית בפוטנציה.', 'Every book here is a potential pillow.'],
      ['סידרתי את המדף לפי חום. העליון הכי חם.', 'Shelf sorted by warmth. Top one’s warmest.'],
      ['ה־EPUB הזה מגרגר כשפותחים אותו. או שזה אני.', 'That EPUB purrs when opened. Or that’s me.'],
      ['אין קנסות על איחור. רק על הזזת חתול.', 'No late fees. Only cat-relocation fees.'],
      ['המדף התחתון: ספרים. המדף העליון: אני.', 'Bottom shelf: books. Top shelf: me.'],
      ['הם מסדרים לפי שם. אני לפי ריח.', 'They sort by title. I sort by smell.'],
      ['ספרייה בלי חתול היא סתם מחסן.', 'A library without a cat is just storage.'],
      ['ספר עבה. כלומר כרית טובה.', 'A thick book. That is, a good pillow.'],
      ['כל ספר כאן עבר ביקורת. שלי. ממרחק בטוח.', 'Every book here passed review. Mine. From a safe distance.']],
    new: [['כשיגיע קובץ, אשב עליו. שיישאר חם.', 'When a file arrives, I shall sit on it. Keep it warm.'],
      ['תקציב. אצלי הכול נמדד בקופסאות טונה.', 'Budgets. I measure everything in tuna cans.'],
      ['המונחים שלי: מיאו = שלום, מיאו! = אוכל, מיאו!!! = עכשיו.', 'My terms: meow = hello, meow! = food, meow!!! = now.'],
      ['קובץ חדש. אולי יש בו ציפורים.', 'A new file. Maybe it has birds in it.'],
      ['PDF או EPUB? אני בעד מה שיותר חם.', 'PDF or EPUB? I vote for whichever is warmer.'],
      ['הם בוחרים מודל. אני הייתי בוחר את זה עם הכי הרבה טונה.', 'They’re choosing a model. I’d pick the one with the most tuna.'],
      ['כל כך הרבה אפשרויות. אצלי יש שתיים: לישון או לאכול.', 'So many options. I have two: sleep or eat.']],
    job: [['אני מפקח על התרגום. כלומר, יושב לידו.', 'I am supervising the translation. That is, sitting near it.'],
      ['האותיות עפות. אולי אתפוס אחת.', 'Letters are flying. Perhaps I’ll catch one.'],
      ['העלילה מסתבכת. כמו חוט צמר.', 'The plot thickens. Like yarn.'],
      ['פרק אחרי פרק. כמו קופסאות טונה בשורה.', 'Chapter after chapter. Like tuna cans in a row.'],
      ['אני שומר על הסדר. כלומר, יושב עליו.', 'I am keeping things in order. By sitting on them.'],
      ['המילים עוברות מצד לצד. אני רק עוקב בעיניים.', 'Words cross from one side to the other. I just watch.'],
      ['עוד קצת, עוד קצת. מכיר את התחושה מארוחת הערב.', 'Almost, almost. I know the feeling from dinnertime.'],
      ['ההתקדמות טובה. אני לוקח חלק מהקרדיט.', 'Good progress. I’m taking part of the credit.']],
    result: [['טיוטה. כלומר עוד מותר לשבת עליה.', 'A draft. Like the one under the door.'],
      ['מגיע לי קרדיט בעמוד השער: ״בסיוע החתול״.', 'I deserve credit on the title page: “with help from the cat”.'],
      ['ספר חדש בשפה חדשה. ועדיין מריח כמו נייר.', 'A new book in a new language. Still smells like paper.'],
      ['קראתי את הסוף. בלי ספוילרים: יש בו חתול. אולי.', 'I read the ending. No spoilers: there’s a cat. Maybe.'],
      ['התוצאה מוכנה. עכשיו מגיע החלק החשוב: מנוחה.', 'The result is ready. Now the important part: rest.'],
      ['אם יש בו טעות, היא שלי. אם אין, גם.', 'If it has a mistake, that’s mine. If not, also mine.']],
    learning: [['Le chat. זה אני. בצרפתית אני נשמע יקר יותר.', 'Le chat. That’s me. I sound pricier in French.'],
      ['אוצר המילים שלי: מיאו, מיאו, ותן.', 'My vocabulary: meow, meow, and gimme.'],
      ['Die Katze. בגרמנית אני נשמע רציני.', 'Die Katze. In German I sound serious.'],
      ['El gato. בספרדית אני נשמע כמו כוכב קולנוע.', 'El gato. In Spanish I sound like a film star.'],
      ['Il gatto. באיטלקית אני כמעט אופרה.', 'Il gatto. In Italian I am nearly an opera.'],
      ['قطة. בכל שפה אני מגיע ראשון לקערה.', 'قطة. In every language I reach the bowl first.'],
      ['שינון מילים? אני משנן רק את הצליל של קופסה נפתחת.', 'Memorising words? I memorise only the sound of a tin opening.']],
    pet: [['פררר…', 'Prrrr…'], ['כן… מאחורי האוזן…', 'Yes… behind the ear…'],
      ['ההנאה הזאת תירשם ביומן העלויות.', 'This pleasure goes in the cost ledger.'],
      ['מרשה להם. רק כי זה יום רביעי.', 'I allow it. Only because it’s Wednesday.'],
      ['עוד. בלי לשאול.', 'More. No need to ask.'],
      ['אני מאשר את הליטוף הזה בדיעבד.', 'I retroactively approve this petting.'],
      ['מצאו את הנקודה. ידעתי שיש בהם פוטנציאל.', 'They found the spot. I knew they had potential.'],
      ['גרגור במצב שקט, כדי לא להפריע לתרגום.', 'Purring on quiet mode, so as not to disturb the translation.']],
    tolerate: [['טוב. כמעט מספיק.', 'Alright. Nearly enough.'],
      ['עוד אחד ואני עובר מדף.', 'One more and I’m changing shelves.'],
      ['הזנב שלי מתחיל להתעצבן.', 'My tail is getting irritated.'],
      ['אני סופר. הם לא.', 'I am counting. They are not.']],
    enough: [['די. חתול מקצועי צריך מרחב.', 'Enough. A professional cat needs space.'],
      ['זהו. עובר למדף אחר.', 'That’s it. Moving to another shelf.'],
      ['ליטוף שישי ברצף? אני מגיש תלונה.', 'A sixth pat in a row? I’m filing a complaint.'],
      ['אני צריך רגע לעצמי. ומדף אחר.', 'I need a moment to myself. And another shelf.']],
    held: [['למה הרצפה מתרחקת?!', 'Why is the floor getting farther away?!'],
      ['אני לא שקית קניות!', 'I am not a shopping bag!'],
      ['טוב, הנוף מכאן לא רע.', 'Well, the view from up here isn’t bad.']],
    dropped: [['נחתתי על הרגליים. כרגיל.', 'Landed on my feet. As usual.'],
      ['כמובן שתכננתי את זה.', 'Of course I planned that.'],
      ['עשר מהשופט הצרפתי.', 'A ten from the French judge.']],
    wake: [['כמה זמן ישנתי? כנראה לא מספיק.', 'How long did I sleep? Not enough, clearly.'],
      ['חלמתי על דג שמתרגם את עצמו.', 'Dreamt of a fish that translates itself.'],
      ['מה פספסתי? כלום. מצוין.', 'What did I miss? Nothing. Excellent.']],
    'file-selected': [['ריח של PDF טרי.', 'Smells like a fresh PDF.'],
      ['קובץ חדש על השולחן. בודק אותו עם האף.', 'A new file on the desk. Inspecting it with my nose.']],
    'file-error': [['גם אני לא הייתי פותח את זה. ואני פותח כל ארון.', 'I wouldn’t open that either. And I open every cupboard.']],
    sample: [['ספר לדוגמה. גם אני חתול לדוגמה.', 'A sample book. I am a sample cat.']],
    'job-start': [['התחילו. מישהו צריך להיות אחראי על ההפסקות. אני.', 'They started. Someone must be in charge of breaks. Me.']],
    'job-paused': [['השהיה. מושלם. זמן תנומה.', 'A pause. Perfect. Nap time.']],
    'job-decision': [['הם צריכים להחליט. אני רק מפיל דברים.', 'They must decide. I only knock things over.']],
    'job-error': [['משהו נתקע. לא אני הפעם.', 'Something got stuck. Not me this time.'],
      ['משהו נשבר. הפעם יש להם הוכחה שזה לא אני.', 'Something broke. This time they have proof it wasn’t me.']],
    'job-done': [['גמרנו. עכשיו בטח ילטפו אותי.', 'Done. Surely petting follows.'],
      ['הספר גמור. מגיעה לי ארוחה חגיגית.', 'The book is done. I deserve a celebratory meal.']],
    delete: [['לתוך הריק. כמו הצעצועים שלי מתחת לספה.', 'Into the void. Like my toys under the sofa.']],
    download: [['לא ברור לי מה זה PDF. בכל זאת, גאווה.', 'Unclear what a PDF is. Proud anyway.'],
      ['נשלח למחשב שלהם. מקווה שחם שם.', 'Off to their computer. Hope it’s warm in there.']],
    'search-empty': [['חיפשתי גם מתחת לספה. כלום.', 'Checked under the sofa too. Nothing.'],
      ['לא נמצא. בדיוק כמו הכדור שלי.', 'Not found. Just like my ball.']],
    'key-missing': [['אין להם מפתח. גם לי אין, ובכל זאת אני נכנס לכל חדר.', 'They have no key. Neither do I, yet I enter every room.']],
    typing: [['המקלדת הזאת נראית חמה…', 'That keyboard looks warm…'],
      ['הם מקלידים מהר. אני הייתי עושה את זה עם הכפות.', 'They type fast. I’d use my paws.']],
    update: [['עדכון. אולי הוסיפו כפתור טונה.', 'An update. Maybe a tuna button.']],
    'lang-en': [['אנגלית עכשיו. מיאו נשמע אותו דבר.', 'English now. Meow sounds the same.']],
    'lang-he': [['עברית שוב. מיאו נשאר מיאו.', 'Hebrew again. Meow stays meow.']],
    model: {
      'gpt-6-luna': [['לונה. כמו הירח שאני מיילל אליו בלילות.', 'Luna. Like the moon I yowl at nightly.']],
      'gpt-6.1-sol': [['סול. שמש. מקום טוב לשכב בו.', 'Sol. Sun. A fine place to lie down.']],
      'claude-haiku-4-5': [['חתול על מדף / שמש חמה על הכריכה / אין לי שאלות.', 'cat upon the shelf / warm sun on the cover / no further questions']],
      'claude-sonnet-5-5': [['סונטה. מקווה שעל טונה.', 'A sonnet. Hopefully about tuna.']],
      'claude-opus-5-5': [['אופוס… הייתי מעדיף תמנון.', 'Opus… I’d prefer octopus.']],
      auto: [['Auto. כמוני: עושה רושם של עבודה.', 'Auto. Like me: gives the impression of work.']]
    }
  };
  function budgetLine(amount) {
    const cans = Math.max(1, Math.floor(amount / 1.5));
    return he() ? `$${amount}… זה ${cans} קופסאות טונה.` : `$${amount}… that’s ${cans} cans of tuna.`;
  }

  // ---------- Sound (opt-in, synthesized locally) ----------
  let audio = null, soundOn = false;
  function ensureAudio() {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    audio ||= new Ctx();
    return audio;
  }
  function tone(kind) {
    if (!soundOn || !audio || audio.state !== 'running') return;
    const now = audio.currentTime, gain = audio.createGain(), osc = audio.createOscillator();
    gain.connect(audio.destination);
    if (kind === 'purr') {
      const lfo = audio.createOscillator(), depth = audio.createGain(), filter = audio.createBiquadFilter();
      osc.type = 'sawtooth'; osc.frequency.value = 52;
      filter.type = 'lowpass'; filter.frequency.value = 180;
      lfo.frequency.value = 24; depth.gain.value = .05;
      lfo.connect(depth); depth.connect(gain.gain);
      osc.connect(filter); filter.connect(gain);
      gain.gain.setValueAtTime(.0001, now);
      gain.gain.linearRampToValueAtTime(.06, now + .2);
      gain.gain.linearRampToValueAtTime(.0001, now + 1.6);
      lfo.start(now); lfo.stop(now + 1.65);
      osc.start(now); osc.stop(now + 1.65);
    } else {
      osc.type = 'sine';
      osc.frequency.setValueAtTime(420, now);
      osc.frequency.exponentialRampToValueAtTime(760, now + .12);
      osc.frequency.exponentialRampToValueAtTime(520, now + .22);
      osc.connect(gain);
      gain.gain.setValueAtTime(.0001, now);
      gain.gain.linearRampToValueAtTime(.05, now + .03);
      gain.gain.exponentialRampToValueAtTime(.0001, now + .26);
      osc.start(now); osc.stop(now + .28);
    }
  }

  // ---------- DOM ----------
  const root = document.createElement('div');
  root.className = 'roam-cat';
  root.hidden = true;
  root.innerHTML = `<div class="roam-thought" aria-hidden="true" hidden><p></p><i class="roam-dot"></i></div>
    <button type="button" class="roam-body">${CAT_SVG}</button>
    <span class="roam-fx" aria-hidden="true"></span>`;
  const body = root.querySelector('.roam-body'), svg = root.querySelector('svg');
  const bubble = root.querySelector('.roam-thought'), bubbleText = bubble.querySelector('p'), fx = root.querySelector('.roam-fx');

  // ---------- Geometry ----------
  // Controls and readable text. The cat may sit beside words, never on them.
  const AVOID = 'button,a[href],input,select,textarea,summary,label,[tabindex]:not([tabindex="-1"]),h1,h2,h3,p,li,.eyebrow,.update-notice,.chip,[data-cat-avoid],.toast';
  const scale = () => (innerWidth < 640 ? 2 : innerWidth < 1100 ? 3 : 4);
  const W = () => GW * scale(), H = () => GH * scale();
  const headerBottom = () => Math.max(0, document.querySelector('.app-header,.site-header')?.getBoundingClientRect().bottom || 0);
  const docRect = el => { const r = el.getBoundingClientRect(); return { l: r.left + scrollX, r: r.right + scrollX, t: r.top + scrollY, b: r.bottom + scrollY, w: r.width, h: r.height }; };
  function subtract(intervals, [a, b]) {
    const out = [];
    for (const [x, y] of intervals) {
      if (b <= x || a >= y) { out.push([x, y]); continue; }
      if (a > x) out.push([x, a]);
      if (b < y) out.push([b, y]);
    }
    return out;
  }
  function obstacles() {
    return [...document.querySelectorAll(AVOID)]
      .filter(el => !root.contains(el) && el.getClientRects().length && !el.closest('dialog:not([open]),[hidden]'))
      .map(docRect).filter(r => r.w > 0 && r.h > 0);
  }
  function segments({ visibleOnly = true, onlyEl = null } = {}) {
    const obs = obstacles(), h = H(), w = W();
    const top = scrollY + headerBottom() + 6, bottom = scrollY + innerHeight - 6;
    const out = [];
    for (const el of onlyEl ? [onlyEl] : document.querySelectorAll('[data-perch]')) {
      if (!el.isConnected || !el.getClientRects().length) continue;
      const r = docRect(el);
      if (r.w < w) continue;
      if (visibleOnly && (r.t - h < top || r.t > bottom)) continue;
      let free = [[Math.max(r.l + 4, scrollX + 4), Math.min(r.r - 4, scrollX + innerWidth - 4)]];
      for (const o of obs) {
        if (o.b <= r.t - h + 4 || o.t >= r.t - 1) continue;
        free = subtract(free, [o.l - 6, o.r + 6]);
      }
      for (const [a, b] of free) if (b - a >= w + 4) out.push({ el, key: el.dataset.perch, y: r.t, a, b, left: r.l });
    }
    // The screen-edge floor is a last resort, used only when no real perch is free.
    const real = out.filter(seg => seg.key !== 'floor');
    return real.length || onlyEl ? real.concat(onlyEl ? out.filter(seg => seg.key === 'floor') : []) : out;
  }
  function placeFree(x, y) {
    // Is the cat's box at (x, y) clear of controls and visible?
    const h = H(), w = W(), top = scrollY + headerBottom(), bottom = scrollY + innerHeight;
    if (y - h < top - 2 || y > bottom + 2) return false;
    if (x < scrollX - 2 || x + w > scrollX + innerWidth + 2) return false;
    return !obstacles().some(o => o.l < x + w - 6 && o.r > x + 6 && o.t < y - 4 && o.b > y - h + 4);
  }

  // ---------- State ----------
  const cat = { x: -200, y: -200, face: 1, pose: 'sit', anchor: null, motion: null, airborne: false };
  let mode = 'roam', paused = false, running = false, raf = 0, last = 0, poseStart = 0;
  let nextBlink = 0, blinkUntil = 0, lastActivity = performance.now(), napping = false; // eslint-disable-line
  let token = null, pets = [], lostSince = 0, checkAt = 0, dragging = null, suppressClick = false, annoyedUntil = 0, unseenSince = 0;

  class Token {
    constructor() { this.cancelled = false; this.waiters = new Set(); }
    // A cancelled behaviour never resumes: its pending waits stay pending, so stale code cannot overwrite the new pose.
    cancel() { this.cancelled = true; this.waiters.forEach(fn => fn()); this.waiters.clear(); }
    wait(ms) {
      return new Promise(resolve => {
        if (this.cancelled) return;
        const stop = () => clearTimeout(id);
        const id = setTimeout(() => { this.waiters.delete(stop); resolve(); }, ms);
        this.waiters.add(stop);
      });
    }
  }
  const rand = (a, b) => a + Math.random() * (b - a);
  function setPose(pose) { if (cat.pose !== pose) { cat.pose = pose; poseStart = performance.now(); } }
  function anchorTo(seg) { cat.anchor = { el: seg.el, key: seg.key, left: docRect(seg.el).l }; cat.y = seg.y; }

  function render(now) {
    const s = scale();
    root.style.setProperty('--cat-scale', s);
    root.style.transform = `translate3d(${Math.round(cat.x)}px,${Math.round(cat.y - H())}px,0)`;
    root.classList.toggle('face-left', cat.face < 0);
    if (svg.dataset.pose !== cat.pose) svg.dataset.pose = cat.pose;
    svg.classList.toggle('blink', now < blinkUntil);
    if (!bubble.hidden) placeBubble();
  }
  // The thought always rises from the cat's head, wherever the pose, direction or screen edge put it.
  const headNode = svg.querySelector('.c-head ellipse.c-fur');
  const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), Math.max(lo, hi));
  function placeBubble() {
    const box = root.getBoundingClientRect(), head = headNode.getBoundingClientRect();
    const w = bubble.offsetWidth, h = bubble.offsetHeight, gap = 34;
    const cx = head.left + head.width / 2, top = headerBottom() + 6;
    const above = head.top - gap - h >= top;
    bubble.dataset.side = above ? '' : (innerWidth - head.right >= head.left ? 'right' : 'left');
    let left, y;
    if (above) {
      left = clamp(cx - w / 2, 8, innerWidth - w - 8);
      y = head.top - gap - h;
      const tail = clamp(cx - left, 22, w - 22);
      bubble.style.setProperty('--tail', `${Math.round(tail)}px`);
      bubble.style.setProperty('--lean', `${Math.round(cx - left - tail)}px`);
    } else {
      // Not enough room under the header: think beside the head, dots pointing at it.
      left = bubble.dataset.side === 'right' ? Math.min(head.right + gap, innerWidth - w - 8) : Math.max(head.left - gap - w, 8);
      y = clamp(head.top + head.height / 2 - h / 2, top, innerHeight - h - 8);
      bubble.style.setProperty('--mid', `${Math.round(clamp(head.top + head.height / 2 - y, 14, h - 14))}px`);
    }
    bubble.style.left = `${Math.round(left - box.left)}px`;
    bubble.style.top = `${Math.round(y - box.top)}px`;
  }

  function loop(now) {
    raf = requestAnimationFrame(loop);
    const dt = Math.min(64, now - last); last = now;
    if (paused) return;
    if (cat.motion) cat.motion(now, dt);
    else if (cat.anchor && !dragging) follow(now);
    if (['sit', 'look', 'walk'].includes(cat.pose) && now > nextBlink) { blinkUntil = now + 150; nextBlink = now + rand(2500, 6000); }
    render(now);
  }
  // Last resort when no spot is free (a narrow window full of fields): peek in from the window's side edge at the
  // bottom corner, half outside the frame (the page clips horizontal overflow), facing inward so the head shows.
  function peekX(side) { return side === 'right' ? scrollX + innerWidth - W() * .5 : scrollX - W() * .5; }
  function peekIn() {
    const floor = document.querySelector('.roam-floor');
    if (!floor || !floor.getClientRects().length) return false;
    const r = docRect(floor), w = W(), h = H(), obs = obstacles();
    const cost = x => obs.filter(o => o.l < x + w && o.r > x && o.t < r.t && o.b > r.t - h).length;
    const end = document.documentElement.dir === 'rtl' ? 'left' : 'right';
    const side = ['left', 'right'].sort((a, b) => cost(peekX(a)) - cost(peekX(b)) || (a === end ? -1 : b === end ? 1 : 0))[0];
    cat.x = peekX(side); cat.face = side === 'right' ? -1 : 1;
    anchorTo({ el: floor, key: 'floor', y: r.t });
    cat.anchor.peek = side;
    setPose('sit');
    root.classList.remove('away');
    return true;
  }
  function follow(now) {
    const a = cat.anchor;
    if (a.peek) {
      const r = docRect(a.el);
      cat.x = peekX(a.peek); cat.y = r.t; a.left = r.l;
      // Come back in as soon as a real spot is free.
      if (now > checkAt) { checkAt = now + 1500; if (segments().length) { cat.anchor = null; relocate('found'); } }
      return;
    }
    if (!a.el.isConnected) {
      const again = a.key && document.querySelector(`[data-perch="${CSS.escape(a.key)}"]`);
      if (again) { a.el = again; a.left = docRect(again).l; } else { cat.anchor = null; relocate('lost'); return; }
    }
    const r = docRect(a.el);
    cat.x += r.l - a.left; a.left = r.l;
    cat.y = r.t;
    if (now > checkAt) {
      checkAt = now + 450;
      if (placeFree(cat.x, cat.y)) lostSince = 0;
      else if (!lostSince) lostSince = now;
      else if (now - lostSince > 500) { lostSince = 0; relocate('blocked'); }
    }
  }

  // ---------- Movement ----------
  // One movement at a time. `step` returns true when finished; cancellation lands the cat safely.
  function animate(tk, step, onCancel) {
    return new Promise(resolve => {
      if (tk.cancelled) return;
      const cancel = () => { cat.motion = null; onCancel(); };
      tk.waiters.add(cancel);
      cat.motion = (now, dt) => { if (step(now, dt)) { tk.waiters.delete(cancel); cat.motion = null; resolve(); } };
    });
  }
  function walkTo(tk, x) {
    cat.face = x > cat.x ? 1 : -1;
    setPose('walk');
    const speed = 0.066 * scale() / 3; // px per ms
    return animate(tk, (now, dt) => {
      if (cat.anchor?.el.isConnected) { const r = docRect(cat.anchor.el); cat.x += r.l - cat.anchor.left; cat.anchor.left = r.l; cat.y = r.t; }
      const step = speed * dt, d = x - cat.x;
      if (Math.abs(d) > step) { cat.x += Math.sign(d) * step; return false; }
      cat.x = x; setPose('sit'); return true;
    }, () => setPose('sit'));
  }
  async function arcTo(tk, seg, x, { drop = false } = {}) {
    if (!drop) { root.classList.add('crouch'); await tk.wait(170); root.classList.remove('crouch'); }
    if (tk.cancelled) return;
    const x0 = cat.x, y0 = cat.y, x1 = x, y1 = seg.y, dist = Math.hypot(x1 - x0, y1 - y0);
    const duration = drop ? Math.max(260, Math.sqrt(Math.abs(y1 - y0)) * 26) : Math.min(1000, Math.max(450, 380 + dist * .45));
    const lift = drop ? 0 : Math.max(36, Math.min(160, Math.abs(y1 - y0) * .25 + 50));
    const start = performance.now();
    cat.face = x1 >= x0 ? 1 : -1;
    cat.anchor = null; cat.airborne = true;
    setPose(drop ? 'held' : 'jump');
    const land = () => { cat.airborne = false; cat.x = x1; anchorTo(seg); setPose('sit'); };
    await animate(tk, now => {
      const t = Math.min(1, (now - start) / duration), e = drop ? t * t : t;
      cat.x = x0 + (x1 - x0) * t;
      cat.y = y0 + (y1 - y0) * e - (drop ? 0 : 4 * lift * t * (1 - t));
      if (t < 1) return false;
      land();
      root.classList.add('land'); setTimeout(() => root.classList.remove('land'), 160);
      if (dist > 220) tone('mrrp');
      return true;
    }, land);
  }
  function xIn(seg, prefer) {
    const lo = seg.a, hi = seg.b - W();
    return Math.min(hi, Math.max(lo, prefer ?? rand(lo, hi)));
  }
  async function goTo(tk, seg, prefer) {
    const x = xIn(seg, prefer);
    const here = cat.anchor && cat.anchor.el === seg.el && !cat.airborne && cat.x >= seg.a - 2 && cat.x + W() <= seg.b + 2;
    if (here) return walkTo(tk, x);
    const visibleNow = cat.y - H() > scrollY && cat.y < scrollY + innerHeight && cat.x > scrollX - W() && cat.x < scrollX + innerWidth;
    const far = Math.abs(seg.y - cat.y) > innerHeight * .8 || Math.abs(x - cat.x) > innerWidth * .85;
    if (!visibleNow || far || cat.x < -100) return dropIn(tk, seg, x);
    return arcTo(tk, seg, x);
  }
  async function dropIn(tk, seg, x = xIn(seg)) {
    // Without a target spot the old code set the position to undefined (NaN) and the cat vanished.
    cat.x = x; cat.y = Math.max(scrollY + headerBottom() + H() * .2, seg.y - innerHeight * .5);
    cat.anchor = null;
    root.classList.add('arriving');
    setTimeout(() => root.classList.remove('arriving'), 260);
    await arcTo(tk, seg, x, { drop: true });
  }

  // ---------- Thoughts and effects ----------
  async function think(tk, text, ms = 4200) {
    if (tk.cancelled || !text) return;
    bubbleText.textContent = text;
    bubble.hidden = false;
    placeBubble();
    await tk.wait(ms + text.length * 25);
    bubble.hidden = true;
  }
  function burst(kind, n = 3) {
    for (let i = 0; i < n; i++) {
      const p = document.createElement('i');
      p.className = `roam-${kind}`;
      p.style.setProperty('--dx', `${Math.round(rand(-22, 22))}px`);
      p.style.animationDelay = `${i * 180}ms`;
      if (kind === 'zzz') p.textContent = 'z';
      fx.append(p);
      setTimeout(() => p.remove(), 1700 + i * 180);
    }
  }

  // ---------- Behaviour ----------
  function daypart() {
    const h = new Date().getHours();
    return h >= 5 && h < 12 ? 'morning' : h < 17 ? 'afternoon' : h < 22 ? 'evening' : 'night';
  }
  function routeThought() {
    const route = document.body.dataset.route || 'library';
    return say(`route:${route}`, [...(LINES[route] || []), ...LINES.idle, ...LINES[daypart()]]);
  }
  // Where the cat lies down: a visible basket, else the visible bottom edge of the window, else any visible perch.
  function napSpot() {
    const segs = segments();
    return segs.find(s => s.key === 'basket') || segments({ onlyEl: document.querySelector('.roam-floor') }).find(s => s.key === 'floor') || segs[0] || null;
  }
  async function nap(tk) {
    napping = true;
    setPose('yawn'); await tk.wait(900);
    setPose('loaf');
    const zzz = setInterval(() => !paused && burst('zzz', 1), 1500);
    tk.waiters.add(() => { clearInterval(zzz); napping = false; });
    while (!tk.cancelled && (mode === 'nap' || performance.now() - lastActivity > 20000)) await tk.wait(800);
    clearInterval(zzz);
    napping = false;
    if (tk.cancelled) return;
    setPose('yawn'); await tk.wait(700); setPose('sit');
    if (mode === 'roam' && Math.random() < .5) await think(tk, say('wake'), 2500);
  }
  async function life(tk) {
    while (!tk.cancelled) {
      if (mode === 'nap') {
        // The napping cat stays in sight: the old spot at the very end of the page was often off-screen.
        const spot = napSpot();
        if (!spot) {
          if (!cat.anchor?.peek && !peekIn()) { root.classList.add('away'); await tk.wait(1500); continue; }
        } else {
          root.classList.remove('away');
          if (!cat.anchor || cat.anchor.el !== spot.el || cat.anchor.peek || !placeFree(cat.x, cat.y)) { cat.x = xIn(spot, spot.b - W()); anchorTo(spot); }
        }
        await nap(tk);
        continue;
      }
      if (!cat.anchor && !cat.motion) {
        const segs = segments();
        if (!segs.length) {
          if (!peekIn()) root.classList.add('away');
          await tk.wait(1500); continue;
        }
        root.classList.remove('away');
        await dropIn(tk, pick(segs));
        continue;
      }
      if (performance.now() - lastActivity > 45000) { await nap(tk); continue; }
      const r = Math.random();
      if (r < .3) {
        // Stroll only within the free stretch the cat is on; never walk across text between stretches.
        const seg = segments({ onlyEl: cat.anchor?.el }).find(s => s.a <= cat.x + 2 && cat.x + W() <= s.b + 2);
        if (seg) await walkTo(tk, xIn(seg));
        setPose('sit'); await tk.wait(rand(1500, 3500));
      } else if (r < .52) {
        const segs = segments().filter(s => s.el !== cat.anchor?.el);
        if (segs.length) {
          const near = segs.sort((a, b) => Math.abs(a.y - cat.y) - Math.abs(b.y - cat.y)).slice(0, 3);
          await goTo(tk, pick(near));
        }
        await tk.wait(rand(1200, 3000));
      } else if (r < .64) {
        setPose('groom'); await tk.wait(rand(2200, 3600)); setPose('sit');
      } else if (r < .72) {
        setPose('yawn'); await tk.wait(900); setPose('sit'); await tk.wait(1200);
      } else if (r < .86) {
        setPose('sit'); await think(tk, routeThought());
        await tk.wait(rand(1500, 3000));
      } else {
        setPose('look'); await tk.wait(rand(1400, 2600)); setPose('sit'); await tk.wait(rand(2000, 5000));
      }
    }
  }
  function run(script) {
    token?.cancel();
    bubble.hidden = true;
    root.classList.remove('crouch');
    const tk = token = new Token();
    (async () => {
      try { if (script) await script(tk); if (!tk.cancelled) await life(tk); }
      catch (error) { console.error(error); }
    })();
  }
  function relocate(reason) {
    if (dragging || mode === 'away' || performance.now() < annoyedUntil) return;
    if (mode === 'nap') { run(); return; } // life() puts the napping cat back on a visible spot
    run(async tk => {
      const segs = segments();
      if (!segs.length) { cat.anchor = null; return; }
      const near = segs.sort((a, b) => Math.abs(a.y - cat.y) + Math.abs(a.a - cat.x) * .3 - (Math.abs(b.y - cat.y) + Math.abs(b.a - cat.x) * .3));
      await goTo(tk, near[0], cat.x);
      if (reason === 'lost' && Math.random() < .5) await think(tk, routeThought());
    });
  }

  // ---------- Interaction ----------
  // Somewhere clearly elsewhere and visible: another perch, else a far stretch of this one, else the window's bottom edge.
  function escapeSpot() {
    const w = W(), segs = segments();
    const far = s => Math.abs(xIn(s, s.a + (s.b - s.a) / 2) - cat.x) > w * 1.5 || Math.abs(s.y - cat.y) > H();
    const others = segs.filter(s => s.el !== cat.anchor?.el && far(s));
    if (others.length) return pick(others.sort((a, b) => Math.abs(a.y - cat.y) - Math.abs(b.y - cat.y)).slice(0, 4));
    const floorEl = document.querySelector('.roam-floor');
    const pool = [...segs, ...(floorEl ? segments({ onlyEl: floorEl }) : [])].filter(far);
    if (!pool.length) return null;
    // Prefer the stretch whose far end is farthest from the cat.
    const end = s => (Math.abs(s.a - cat.x) > Math.abs(s.b - w - cat.x) ? s.a : s.b - w);
    const best = pool.sort((a, b) => Math.abs(end(b) - cat.x) - Math.abs(end(a) - cat.x))[0];
    return { seg: best, x: end(best) };
  }
  function pet() {
    const now = performance.now();
    lastActivity = now;
    // While he is leaving, more clicks do not cancel the move: he has made up his mind.
    if (now < annoyedUntil) return;
    pets = pets.filter(t => now - t < 9000).concat(now);
    run(async tk => {
      if (napping || cat.pose === 'loaf') { setPose('yawn'); await tk.wait(500); }
      if (pets.length >= 6) {
        pets = [];
        annoyedUntil = performance.now() + 5000;
        const thought = say('enough');
        bubbleText.textContent = thought; bubble.hidden = false; placeBubble();
        announce((he() ? 'חתול הספרייה חושב: ' : 'The library cat thinks: ') + thought);
        const spot = escapeSpot();
        if (spot?.seg) await goTo(tk, spot.seg, spot.x);
        else if (spot) await goTo(tk, spot);
        else { root.classList.add('crouch'); await tk.wait(170); root.classList.remove('crouch'); } // nowhere to go: a huffy hop
        setPose('look'); await tk.wait(1600);
        bubble.hidden = true;
        annoyedUntil = 0;
        return;
      }
      const tired = pets.length >= 4;
      setPose(tired ? 'look' : 'happy');
      if (!tired) { burst('heart', 3); tone('purr'); }
      const thought = say(tired ? 'tolerate' : 'pet');
      announce((he() ? 'חתול הספרייה חושב: ' : 'The library cat thinks: ') + thought);
      await think(tk, thought, 2400);
      setPose('sit');
      if (mode === 'nap') await nap(tk);
    });
  }
  function announce(text) {
    const node = document.getElementById('cat-announcer');
    if (!node) return;
    node.textContent = '';
    requestAnimationFrame(() => { node.textContent = text; });
  }
  body.addEventListener('click', event => {
    if (suppressClick) { suppressClick = false; event.preventDefault(); return; }
    pet();
  });
  body.addEventListener('pointerdown', event => {
    if (event.button !== 0 || mode === 'away') return;
    dragging = { id: event.pointerId, sx: event.pageX, sy: event.pageY, held: false };
    body.setPointerCapture(event.pointerId);
  });
  body.addEventListener('pointermove', event => {
    if (!dragging || dragging.id !== event.pointerId) return;
    if (!dragging.held && Math.hypot(event.pageX - dragging.sx, event.pageY - dragging.sy) > 7) {
      dragging.held = true;
      token?.cancel();
      cat.motion = null; cat.anchor = null;
      setPose('held'); root.classList.add('held');
      bubbleText.textContent = say('held'); bubble.hidden = false;
    }
    if (dragging.held) {
      const minY = scrollY + headerBottom() + H() * .8;
      cat.x = Math.min(scrollX + innerWidth - W() - 2, Math.max(scrollX + 2, event.pageX - W() * .62));
      cat.y = Math.max(minY, event.pageY + H() * .8);
    }
  });
  function endDrag(event) {
    if (!dragging || dragging.id !== event.pointerId) return;
    const held = dragging.held;
    dragging = null;
    if (!held) return;
    suppressClick = true;
    setTimeout(() => { suppressClick = false; }, 50);
    root.classList.remove('held');
    lastActivity = performance.now();
    run(async tk => {
      const cx = cat.x + W() / 2, all = segments();
      const below = all.filter(s => s.a <= cx && cx <= s.b && s.y >= cat.y - 8).sort((a, b) => a.y - b.y)[0];
      const target = below || all.sort((a, b) => Math.hypot(a.a - cat.x, a.y - cat.y) - Math.hypot(b.a - cat.x, b.y - cat.y))[0];
      if (!target) { bubble.hidden = true; return; }
      if (below) await arcTo(tk, target, xIn(target, cat.x), { drop: true });
      else await arcTo(tk, target, xIn(target, cat.x));
      await think(tk, say('dropped'), 2200);
    });
  }
  body.addEventListener('pointerup', endDrag);
  body.addEventListener('pointercancel', endDrag);

  // ---------- Lifecycle ----------
  function setPaused(next) {
    if (next === paused) return;
    paused = next;
    root.classList.toggle('paused', paused);
    if (paused) { token?.cancel(); cat.motion = null; bubble.hidden = true; }
    else if (running) run();
  }
  function reconcile() {
    const dialogOpen = !!document.querySelector('dialog[open]');
    setPaused(document.hidden || dialogOpen);
  }
  function start() {
    if (running || mode === 'away') return;
    running = true;
    root.hidden = false;
    last = performance.now();
    raf = requestAnimationFrame(loop);
    reconcile();
    if (!paused) run(async tk => {
      await tk.wait(500);
      const segs = segments();
      if (segs.length) {
        const seg = segs.find(s => s.key === 'hero') || pick(segs);
        await dropIn(tk, seg, xIn(seg));
        if (mode === 'roam') await think(tk, Math.random() < .35 ? say(daypart()) : say('hello'), 3800);
      }
    });
  }
  function stop() {
    running = false;
    token?.cancel();
    cancelAnimationFrame(raf);
    root.hidden = true;
    cat.anchor = null; cat.motion = null; cat.x = -200;
  }
  ['pointermove', 'keydown', 'wheel', 'touchstart', 'scroll'].forEach(type =>
    addEventListener(type, () => { lastActivity = performance.now(); }, { passive: true }));
  document.addEventListener('visibilitychange', reconcile);
  addEventListener('resize', () => { if (running && !paused) { cat.x = Math.min(cat.x, scrollX + innerWidth - W() - 4); } });
  addEventListener('pagehide', () => { token?.cancel(); audio?.close().catch(() => {}); audio = null; });

  // ---------- Preferences: roam / nap / away, and opt-in sound ----------
  const readPref = key => { try { return localStorage.getItem(key); } catch { return null; } };
  const writePref = (key, value) => { try { localStorage.setItem(key, value); } catch { /* private mode: keep in memory */ } };
  const MODE_LABEL = { roam: ['החתול מסתובב', 'Cat: roaming'], nap: ['החתול ישן', 'Cat: napping'], away: ['החתול בחופשה', 'Cat: on holiday'] };
  function labels() {
    const button = document.getElementById('cat-button');
    if (button) { button.textContent = `🐾 ${L(MODE_LABEL[mode])}`; button.setAttribute('aria-haspopup', 'dialog'); button.hidden = false; }
    body.setAttribute('aria-label', he() ? 'חתול הספרייה. לחיצה מלטפת, גרירה מרימה אותו' : 'The library cat. Click to pet, drag to pick up');
  }
  function openSettings() {
    let dialog = document.querySelector('.cat-dialog');
    if (!dialog) { dialog = document.createElement('dialog'); dialog.className = 'cat-dialog'; dialog.setAttribute('aria-labelledby', 'cat-dialog-title'); document.body.append(dialog); }
    const option = (value, label, caption) => `<label class="cat-option"><input type="radio" name="cat-mode" value="${value}" ${mode === value ? 'checked' : ''}><span><b>${label}</b><small>${caption}</small></span></label>`;
    dialog.innerHTML = `<h2 id="cat-dialog-title">${L(['חתול הספרייה', 'The library cat'])}</h2>
      <div class="cat-options" role="radiogroup" aria-labelledby="cat-dialog-title">
        ${option('roam', L(['מסתובב', 'Roaming']), L(['קופץ בין המדפים וחושב מחשבות', 'Hops between shelves and thinks thoughts']))}
        ${option('nap', L(['ישן בפינה', 'Napping']), L(['נשאר בתחתית הדף ונוחר בשקט', 'Stays at the bottom and snores quietly']))}
        ${option('away', L(['בחופשה', 'On holiday']), L(['בלי חתול. הוא יתגעגע.', 'No cat. He will miss you.']))}</div>
      <label class="cat-check"><input type="checkbox" name="cat-sound" ${soundOn ? 'checked' : ''}> ${L(['צלילי גרגור קטנים, נוצרים כאן במחשב', 'A small purr, synthesized on this computer'])}</label>
      <p class="cat-sound-note" hidden>${L(['הצלילים אינם זמינים בדפדפן הזה. החתול ימשיך בשקט.', 'Sounds are unavailable in this browser. The cat carries on silently.'])}</p>
      <p class="cat-hint">${L(['אפשר ללטף אותו (לחיצה או Enter) ולהרים אותו בגרירה. הוא לא יושב על כפתורים או על טקסט.', 'Pet him with a click or Enter, lift him by dragging. He never sits on buttons or text.'])}</p>
      <div class="cat-actions"><button type="button" class="primary-button" data-cat-close>${L(['סגירה', 'Close'])}</button></div>`;
    dialog.showModal();
    dialog.querySelector('input:checked')?.focus();
  }
  document.addEventListener('click', event => {
    if (event.target.closest('#cat-button')) openSettings();
    if (event.target.closest('[data-cat-close]')) event.target.closest('dialog').close();
  });
  document.addEventListener('change', async event => {
    if (event.target.name === 'cat-mode') { writePref('cat-mode', event.target.value); window.libraryCat.setMode(event.target.value); labels(); }
    if (event.target.name === 'cat-sound') {
      const ok = await window.libraryCat.setSound(event.target.checked);
      writePref('cat-sound', event.target.checked && ok ? 'on' : 'off');
      const note = event.target.closest('dialog').querySelector('.cat-sound-note');
      note.hidden = !(event.target.checked && !ok);
      if (event.target.checked && !ok) event.target.checked = false;
    }
  });

  // ---------- Public API used by the app ----------
  window.libraryCat = {
    mount() {
      if (root.isConnected) return;
      document.body.append(root);
      if (!document.getElementById('cat-announcer')) {
        const live = document.createElement('div');
        live.id = 'cat-announcer'; live.className = 'visually-hidden'; live.setAttribute('role', 'status');
        document.body.append(live);
      }
      // The footer is the cat's floor of last resort on every page.
      const footer = document.querySelector('.app-footer');
      if (footer && !footer.dataset.perch) footer.dataset.perch = 'footer';
      const saved = readPref('cat-mode');
      if (['roam', 'nap', 'away'].includes(saved)) mode = saved;
      // With reduced motion asked by the system, the cat naps until someone wakes him in the settings.
      else if (matchMedia('(prefers-reduced-motion: reduce)').matches) mode = 'nap';
      new MutationObserver(labels).observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
      labels();
      if (!document.querySelector('.roam-floor')) {
        const floor = document.createElement('div');
        floor.className = 'roam-floor'; floor.dataset.perch = 'floor'; floor.setAttribute('aria-hidden', 'true');
        document.body.append(floor);
      }
      new MutationObserver(reconcile).observe(document.body, { subtree: true, attributes: true, attributeFilter: ['open'] });
      // The app changes layout without telling the cat (panels, options, results): recheck the spot at once.
      let layoutTimer = 0;
      new ResizeObserver(() => { clearTimeout(layoutTimer); layoutTimer = setTimeout(() => window.libraryCat.refresh(), 60); }).observe(document.body);
      if (mode !== 'away') start();
    },
    refresh() {
      body.setAttribute('aria-label', he() ? 'חתול הספרייה. לחיצה מלטפת, גרירה מרימה אותו' : 'The library cat. Click to pet, drag to pick up');
      reconcile();
      // A re-render may have put a control under the cat: move at once, don't wait for the periodic check.
      if (running && !paused && !dragging && !cat.airborne && cat.anchor && !cat.anchor.peek && cat.anchor.el.isConnected) {
        const r = docRect(cat.anchor.el); cat.y = r.t;
        if (!placeFree(cat.x, cat.y)) relocate('blocked');
      }
    },
    setMode(next) {
      mode = next;
      if (mode === 'away') { stop(); return; }
      if (!running) start(); else run();
    },
    async setSound(on) {
      if (!on) { soundOn = false; return true; }
      try {
        const ctx = ensureAudio();
        if (!ctx) return false;
        await ctx.resume();
        soundOn = ctx.state === 'running';
        if (soundOn) tone('mrrp');
        return soundOn;
      } catch { soundOn = false; return false; }
    },
    react(type, detail = {}) {
      if (!running || mode !== 'roam' || dragging) return;
      let text = '';
      if (type === 'budget') text = budgetLine(detail.amount);
      else if (type === 'model') text = say(`model:${detail.id}`, LINES.model[detail.id] || LINES.model.auto);
      else if (Array.isArray(LINES[type])) text = say(type);
      if (type === 'route') text = Math.random() < .55 ? routeThought() : '';
      if (paused) return;
      run(async tk => {
        await tk.wait(type === 'route' ? 450 : 60);
        const target = detail.perch && document.querySelector(`[data-perch="${CSS.escape(detail.perch)}"]`);
        if (target) {
          const seg = segments({ onlyEl: target })[0];
          if (seg) await goTo(tk, seg);
        } else if (!cat.anchor || !placeFree(cat.x, cat.y)) {
          const segs = segments();
          if (segs.length) await goTo(tk, segs.sort((a, b) => Math.abs(a.y - cat.y) - Math.abs(b.y - cat.y))[0]);
        }
        if (type === 'job-done') {
          const seg = segments({ onlyEl: cat.anchor?.el })[0];
          if (seg) await arcTo(tk, seg, xIn(seg, cat.x + 30));
          setPose('happy'); burst('heart', 4);
        }
        if (type === 'job-paused') { setPose('loaf'); await tk.wait(400); }
        if (text) await think(tk, text);
        if (type === 'job-paused') { await tk.wait(1500); }
      });
    },
    // Test hooks for the verification script: place the cat and show a thought without running behaviour.
    _testThink({ face = 1, pose = 'sit', x = 200, y = 400, text = '…' } = {}) {
      token?.cancel(); token = new Token(); cat.motion = null; cat.anchor = null;
      cat.face = face; setPose(pose); cat.x = x + scrollX; cat.y = y + scrollY;
      bubbleText.textContent = text; bubble.hidden = false;
    },
    debug: () => ({ x: cat.x, y: cat.y, w: W(), h: H(), pose: cat.pose, anchor: cat.anchor?.key || null, peek: cat.anchor?.peek || null, paused, running, mode, thought: bubble.hidden ? '' : bubbleText.textContent, free: placeFree(cat.x, cat.y), segments: segments().length })
  };
})();
// The app loads this script at the end of <body>, so the page is ready.
window.libraryCat.mount();
