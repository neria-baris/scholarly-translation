# התקנה ראשונית (Windows, ללא שורת פקודה)

## התקנה

1. התקינו Python 3.10 ואילך מ־[python.org](https://www.python.org/downloads/) אם אין לכם — בעת ההתקנה סמנו **Add python.exe to PATH**. המתקין מזהה גם את סביבת Python המקומית של Codex, אם היא קיימת במחשב.
2. בתיקיית הפרויקט, לחצו פעמיים על **Install.bat**.
3. נפתח חלון קטן שמתקין את התלויות הנדרשות (`pdfplumber`, `reportlab`, `Pillow`, `tiktoken`, `openai`, `anthropic`) מתוך `requirements.txt` בסביבה מבודדת של הפרויקט. אם `.venv` קיימת אך אינה תקינה, היא נשמרת וההתקנה משתמשת ב־`outputs/tooling/runtime-venv`. בסיום נוצר קיצור דרך **Scholarly Translation** בשולחן העבודה.
4. אם ההתקנה נכשלת (למשל Python לא נמצא), תקנו את הבעיה ולחצו **Retry** בחלון עצמו.

## הרצה

- לחצו על קיצור הדרך **Scholarly Translation** בשולחן העבודה שנוצר בהתקנה, **או**
- לחצו פעמיים על **Run Scholarly Translation.vbs** בתיקיית הפרויקט.

המפעיל בודק שה־Python שנבחר הוא לפחות 3.10 וכולל את כל התלויות. הוא פותח את השרת המקומי והדפדפן. השאירו את חלון השרת פתוח; סגירתו או `Ctrl+C` עוצרים את השרת. לפרטים על השימוש ראו [UI_README_HE.md](UI_README_HE.md).

## הערות

- ההתקנה וההרצה מורידות חבילות Python סטנדרטיות בלבד (מ־PyPI); אין התקנת תוכנה חיצונית לא-Python, ואין צריכת הרשאות מערכת.
- ספירת הטוקנים המקומית אינה פונה לספק. היא משתמשת בקובצי קידוד מקומיים מאומתים כשישנם, ובאומדן דטרמיניסטי מסומן כשאין קידוד מתאים. ראו [MODEL_COSTS_HE.md](MODEL_COSTS_HE.md).
- ניתן גם להריץ את ההתקנה וההרצה ישירות מטרמינל PowerShell, ללא קיצורי הדרך:
  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
  .\run-ui.ps1
  ```
- OCR למסמכי PDF סרוקים הוא רכיב CLI מקומי נפרד שדורש התקנת [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) בנפרד; הוא אינו מותקן על ידי `Install.bat` ואינו חלק מהממשק הפשוט (ראו README.md, Gate 3).
