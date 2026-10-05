# התקנה ראשונית (Windows, ללא שורת פקודה)

## התקנה

1. התקינו Python 3.9 ואילך מ־[python.org](https://www.python.org/downloads/) אם אין לכם — בעת ההתקנה סמנו **Add python.exe to PATH**.
2. בתיקיית הפרויקט, לחצו פעמיים על **Install.bat**.
3. נפתח חלון קטן שמתקין את התלויות הנדרשות (`pdfplumber`, `reportlab`, `Pillow`) בתוך תיקיית `.venv` מבודדת של הפרויקט בלבד — אין שינוי להתקנת Python הכללית במחשב, ואין צורך בהרשאות מנהל. בסיום נוצר קיצור דרך **Scholarly Translation** בשולחן העבודה.
4. אם ההתקנה נכשלת (למשל Python לא נמצא), תוקנו את הבעיה ולחצו **Retry** בחלון עצמו.

## הרצה

- לחצו על קיצור הדרך **Scholarly Translation** בשולחן העבודה שנוצר בהתקנה, **או**
- לחצו פעמיים על **Run Scholarly Translation.vbs** בתיקיית הפרויקט.

כל אחת מהדרכים פותחת חלון קטן שמריץ את השרת המקומי ופותחת את הדפדפן אוטומטית בכתובת המקומית. השאירו את החלון פתוח כל עוד אתם משתמשים בתרגום; סגירתו (או `Ctrl+C` בתוכו) עוצרת את השרת. לפרטים על השימוש עצמו ראו [UI_README_HE.md](UI_README_HE.md).

## הערות

- ההתקנה וההרצה מורידות חבילות Python סטנדרטיות בלבד (מ־PyPI); אין התקנת תוכנה חיצונית לא-Python, ואין צריכת הרשאות מערכת.
- ניתן גם להריץ את ההתקנה וההרצה ישירות מטרמינל PowerShell, ללא קיצורי הדרך:
  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
  .\run-ui.ps1
  ```
- OCR למסמכי PDF סרוקים הוא רכיב CLI מקומי נפרד שדורש התקנת [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) בנפרד; הוא אינו מותקן על ידי `Install.bat` ואינו חלק מהממשק הפשוט (ראו README.md, Gate 3).
