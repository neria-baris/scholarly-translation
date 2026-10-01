"""Declarative command forms for the local browser UI."""

from __future__ import annotations

import sys
from dataclasses import dataclass


LANGUAGES = ("en", "fr", "ja")
PROVIDERS = ("mock", "openai")


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    flag: str = ""
    kind: str = "file"
    required: bool = False
    values: tuple[str, ...] = ()


@dataclass(frozen=True)
class Step:
    command: str
    title: str
    help: str
    fields: tuple[Field, ...]
    result: str = ""


def field(key: str, label: str, flag: str = "", kind: str = "file", required: bool = False,
          values: tuple[str, ...] = ()) -> Field:
    return Field(key, label, flag, kind, required, values)


STEPS = (
    Step("demo", "דוגמה מקומית", "יוצר מסמך דמה ללא PDF או קריאה בתשלום.", (), "document.json"),
    Step("extract-pdf", "1 · חילוץ PDF", "מחלץ טקסט ותמונות עמודים. המקור דורש בדיקה אנושית.", (
        field("input", "קובץ PDF", required=True),
        field("language", "שפת מקור", "--language", "choice", True, LANGUAGES),
    ), "comparison.html"),
    Step("ocr-pdf", "2 · OCR מקומי", "דורש Tesseract מותקן וקובץ PDF זהה לזה שחולץ.", (
        field("input", "קובץ PDF", required=True),
        field("document_json", "document.json", required=True),
        field("language", "שפת מקור", "--language", "choice", True, LANGUAGES),
        field("tesseract", "קובץ tesseract.exe", "--tesseract", required=True),
        field("tessdata_dir", "תיקיית tessdata", "--tessdata-dir", "dir"),
        field("pages", "מספרי עמודים (רווחים)", "--pages", "text"),
    ), "ocr.json"),
    Step("structure", "3 · מקור ומקטעים", "ללא קובץ החלטות אנושי המקור נשאר לא פתור ולא נוצרים מקטעים לתרגום.", (
        field("document_json", "document.json", required=True),
        field("ocr", "חבילת OCR", "--ocr"),
        field("decisions", "החלטות מקור JSON", "--decisions"),
        field("boundaries", "גבולות מקטעים JSON", "--boundaries"),
        field("previous", "מבנה קודם JSON", "--previous"),
    ), "structure.json"),
    Step("terminology", "4 · מילון", "יצירה, סקירה ופתרון מונחים לפי קובץ פעולה JSON.", (
        field("structure_json", "structure.json", required=True),
        field("glossary", "glossary.json (יכול להיות חדש)", "--glossary", required=True),
        field("memory", "memory.json", "--memory"),
        field("action", "פעולה JSON", "--action"),
    ), "glossary.json"),
    Step("translate-unit", "5 · תרגום מקטע", "ברירת המחדל היא mock. פלט mock אינו תרגום אמיתי.", (
        field("structure_json", "structure.json", required=True),
        field("glossary", "glossary.json", "--glossary", required=True),
        field("unit_id", "מזהה מקטע", "--unit-id", "text", True),
        field("profile", "פרופיל", "--profile", "choice", True, ("scholarly",)),
        field("provider", "ספק", "--provider", "choice", True, PROVIDERS),
        field("control_store", "מאגר תקציב ומטמון", "--control-store"),
        field("task_id", "מזהה משימה (אופציונלי)", "--task-id", "text"),
        field("max_calls", "מספר קריאות מרבי", "--max-calls", "text"),
        field("hard_list_usd", "תקרת מחירון בדולרים", "--hard-list-usd", "text"),
    ), "translation_draft.json"),
    Step("semantic-review", "6 · ביקורת סמנטית", "ביקורת מותנית; לעולם אינה מאשרת תרגום.", (
        field("structure_json", "structure.json", required=True),
        field("glossary", "glossary.json", "--glossary", required=True),
        field("draft", "translation_draft.json", "--draft", required=True),
        field("provider", "ספק", "--provider", "choice", True, PROVIDERS),
        field("control_store", "מאגר תקציב ומטמון", "--control-store"),
        field("task_id", "מזהה משימה (אופציונלי)", "--task-id", "text"),
        field("max_calls", "מספר קריאות מרבי", "--max-calls", "text"),
        field("hard_list_usd", "תקרת מחירון בדולרים", "--hard-list-usd", "text"),
    ), "semantic_review.json"),
    Step("human-review-render", "7 · מסך בדיקה", "פותח דף השוואת מקור ותרגום עם טופס החלטה אנושית.", (
        field("structure_json", "structure.json", required=True),
        field("glossary", "glossary.json", "--glossary", required=True),
        field("draft", "translation_draft.json", "--draft", required=True),
        field("review", "semantic_review.json", "--review"),
    ), "review.html"),
    Step("human-review-decide", "8 · רישום החלטה", "טוען JSON שהורד ממסך הבדיקה ושומר רשומת החלטה.", (
        field("structure_json", "structure.json", required=True),
        field("glossary", "glossary.json", "--glossary", required=True),
        field("draft", "translation_draft.json", "--draft", required=True),
        field("review", "semantic_review.json", "--review"),
        field("decision", "קובץ החלטה JSON", "--decision", required=True),
        field("previous", "החלטה קודמת JSON", "--previous"),
    )),
    Step("human-review-export", "9 · ייצוא דו־לשוני", "הייצוא זמין רק להחלטה אנושית מאושרת ותקפה.", (
        field("structure_json", "structure.json", required=True),
        field("glossary", "glossary.json", "--glossary", required=True),
        field("draft", "translation_draft.json", "--draft", required=True),
        field("review", "semantic_review.json", "--review"),
        field("record", "רשומת החלטה JSON", "--record", required=True),
    ), "export.html"),
    Step("inspect", "בדיקת מסמך", "מציג מזהים, עמודים ומקטעים.", (
        field("document_path", "document.json", required=True),
    )),
    Step("inspect-structure", "בדיקת מבנה", "מציג קריאות מקור ומקטעים מאומתים.", (
        field("structure_json", "structure.json", required=True),
    )),
    Step("probe-provider", "בדיקת ספק", "בדיקת חיבור קטנה; OpenAI עשוי לחייב כסף.", (
        field("provider", "ספק", "--provider", "choice", True, PROVIDERS),
    ), "probe_result.json"),
    Step("evaluate-pilot", "הערכת פיילוט", "דורש manifest מאושר; תוצאות ניסיון אינן אישור איכות.", (
        field("manifest_json", "pilot manifest JSON", required=True),
    ), "pilot_report.json"),
    Step("runtime-status", "סטטוס תקציב ומטמון", "מציג מטא־נתונים בלבד, בלי טקסט מקור או פלט.", (
        field("control_store", "מאגר תקציב ומטמון", "--control-store", required=True),
        field("task_id", "מזהה משימה", "--task-id", "text", True),
    )),
)


def build_command(step: Step, values: dict[str, str], output: str) -> list[str]:
    """Build an argv list. No shell interpretation of user-controlled paths or text."""
    argv = [sys.executable, "-B", "-m", "scholarly_translation", step.command]
    for spec in step.fields:
        value = values.get(spec.key, "").strip()
        if spec.required and not value:
            raise ValueError(f"חסר שדה חובה: {spec.label}")
        if not value:
            continue
        if spec.values and value not in spec.values:
            raise ValueError(f"ערך לא חוקי: {spec.label}")
        if spec.key == "pages":
            parts = value.split()
            if not parts or any(not item.isdecimal() or int(item) < 1 for item in parts):
                raise ValueError("מספרי עמודים חייבים להיות מספרים חיוביים")
            argv.extend([spec.flag, *parts])
        elif spec.flag:
            argv.extend([spec.flag, value])
        else:
            argv.append(value)
    if step.command not in ("inspect", "inspect-structure", "runtime-status"):
        if not output.strip():
            raise ValueError("חסרה תיקיית פלט")
        argv.extend(["--output", output.strip()])
    return argv
