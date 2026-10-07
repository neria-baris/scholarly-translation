"""Client-side English for server-produced Hebrew text (SERVER_EN / serverText in ui.js).

CoverageTests fail until SERVER_EN holds every Hebrew template the server can show.
"""
import ast
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "scholarly_translation"
JS = PKG / "ui.js"

HEB = re.compile('[א-ת]')
PCT = re.compile(r'%(?:\([^)]*\))?[-+ #0]*\d*(?:\.\d+)?[sdifr]')
FMT = re.compile(r'\{[^{}]*\}')

# Modules whose Hebrew is linguistic word lists, regex character classes or model prompts,
# never shown as UI text.
EXCLUDED_MODULES = {"semantic_review.py", "evaluation.py", "export_html.py", "review_qa.py", "name_table.py"}
# Concatenated fragments in web_ui.py, covered by the composite template below.
FRAGMENTS = {'יש לשמור מפתח API עבור: ', ' לפני התחלת עבודה אמיתית.'}
COMPOSITE = "יש לשמור מפתח API עבור: {1} לפני התחלת עבודה אמיתית."
# key_store.py has short real messages; elsewhere fewer than 3 Hebrew letters is not a message.
SHORT_OK_MODULES = {"key_store.py"}
# Keys the client composes from stage labels; the AST sees them only as a plain label.
STAGE_EXTRA = {"בדיקה רוחבית של פרקים {1}–{2}"}


def _numbered(parts):
    out, n = [], 0
    for kind, text in parts:
        if kind == 'lit':
            out.append(text)
        else:
            n += 1
            out.append('{%d}' % n)
    return ''.join(out)


def _from_pct(s):
    parts, pos = [], 0
    for m in PCT.finditer(s):
        parts += [('lit', s[pos:m.start()]), ('var', '')]
        pos = m.end()
    parts.append(('lit', s[pos:]))
    return _numbered(parts).replace('%%', '%')


def _from_format(s):
    parts, pos = [], 0
    for m in FMT.finditer(s):
        parts += [('lit', s[pos:m.start()]), ('var', '')]
        pos = m.end()
    parts.append(('lit', s[pos:]))
    return _numbered(parts)


def _templates(path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    seen, found = set(), []

    def add(node, text, kind):
        if HEB.search(text):
            found.append({'module': path.name, 'line': node.lineno, 'kind': kind, 'he': text})

    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            parts = []
            for v in node.values:
                if isinstance(v, ast.Constant):
                    parts.append(('lit', v.value))
                    seen.add(id(v))
                else:
                    parts.append(('var', ''))
            add(node, _numbered(parts), 'fstring')
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Constant) \
                and isinstance(node.left.value, str):
            seen.add(id(node.left))
            add(node, _from_pct(node.left.value), 'percent')
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'format' \
                and isinstance(node.func.value, ast.Constant) and isinstance(node.func.value.value, str):
            seen.add(id(node.func.value))
            add(node, _from_format(node.func.value.value), 'format')
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in seen:
            text = _from_pct(node.value) if PCT.search(node.value) else node.value
            add(node, text, 'constant')
    return found


def source_templates():
    """Return {template: module} for every Hebrew UI template the server can produce."""
    result = {}
    for path in sorted(PKG.glob('*.py')):
        if path.name.startswith('learning') or path.name == 'gui.py' or path.name in EXCLUDED_MODULES:
            continue
        for row in _templates(path):
            he = row['he']
            if he.startswith('[') or he in FRAGMENTS:
                continue
            if len(HEB.findall(he)) < 3 and path.name not in SHORT_OK_MODULES:
                continue
            result.setdefault(he, path.name)
    result.setdefault(COMPOSITE, 'web_ui.py')
    return result


def server_table():
    """SERVER_EN as {he: en}, read from the one-entry-per-line block in ui.js."""
    js = JS.read_text(encoding='utf-8')
    start = js.index('const SERVER_EN={')
    block = js[start:js.index('\n};', start)]
    table = {}
    for line in block.split('\n')[1:]:
        line = line.strip()
        if not line:
            continue
        match = re.fullmatch(r'("(?:[^"\\]|\\.)*")\s*:\s*("(?:[^"\\]|\\.)*"),?', line)
        if not match:
            raise AssertionError('SERVER_EN line is not one "he": "en" entry: %s' % line[:80])
        table[json.loads(match.group(1))] = json.loads(match.group(2))
    return table


def placeholders(text):
    return sorted(re.findall(r'\{\d+\}', text))


class CoverageTests(unittest.TestCase):
    """Fail until the full table is inserted."""

    @classmethod
    def setUpClass(cls):
        cls.table = server_table()
        cls.sources = source_templates()

    def test_every_server_template_has_english(self):
        missing = sorted("%s: %s" % (self.sources[he], he) for he in self.sources if he not in self.table)
        self.assertEqual(missing, [], "%d Hebrew server templates have no SERVER_EN entry" % len(missing))

    def test_no_dead_entries(self):
        dead = sorted(he for he in self.table if he not in self.sources and he not in STAGE_EXTRA)
        self.assertEqual(dead, [], "SERVER_EN keys with no source template")


class TableShapeTests(unittest.TestCase):
    def test_entries_are_well_formed(self):
        table = server_table()
        self.assertGreaterEqual(len(table), 3)
        for he, en in table.items():
            self.assertEqual(placeholders(he), placeholders(en), he)
            self.assertIsNone(HEB.search(en), en)
            self.assertTrue(en.strip(), he)


@unittest.skipUnless(shutil.which('node'), 'node not installed')
class ServerTextBehaviourTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        js = JS.read_text(encoding='utf-8')
        block = js[js.index('/*I18N-BEGIN*/'):js.index('/*I18N-END*/')]
        start = js.index('let SERVER_PATTERNS')
        fn = js[start:js.index('\n', js.index('function stageLabel(')) + 1]
        cls.program = block + '\n' + fn + '\n'

    def test_behaviour(self):
        amount = 'העלאת התקציב ל־$12.50'
        nested = 'הבדיקה הרוחבית של פרקים 1–3 לא בוצעה (תקציב או כשל בקריאה); אפשר להפעיל אותה שוב מכפתור הבדיקה הרוחבית.'
        note = 'מחברת הספר לא עודכנה אחרי פרק 4 (תקציב או כשל בקריאה); ההמשך לא הושפע.' + ' · ' + nested
        body = (
            'const o={exact:serverText("תקציב או כשל בקריאה"),amount:serverText(%s),nested:serverText(%s),'
            'joined:serverText(%s),lines:serverText("תקציב או כשל בקריאה\\nלרשום x ולנסות שוב"),'
            'unknown:serverText("טקסט לא מוכר"),empty:serverText(""),nonstr:serverText(null),'
            'stage:stageLabel("מתרגם")};LANG="he";o.he=serverText("תקציב או כשל בקריאה");o.heT=serverText(%s);'
            'console.log(JSON.stringify(o))'
        ) % (json.dumps(amount), json.dumps(nested), json.dumps(note), json.dumps(amount))
        script = "let LANG='en';\n" + self.program + body
        out = json.loads(subprocess.run(['node', '-e', script], capture_output=True, text=True,
                                        encoding='utf-8', check=True).stdout)
        self.assertEqual(out['exact'], 'budget or call failure')
        self.assertEqual(out['amount'], 'Raise the budget to $12.50')
        self.assertEqual(out['nested'], 'The cross-chapter review of chapters 1–3 did not run (budget or call failure); '
                         'you can run it again from the cross-chapter review button.')
        self.assertEqual(out['joined'].count(' · '), 1)
        self.assertTrue(out['joined'].startswith('The book notebook was not updated after chapter 4'))
        self.assertIsNone(HEB.search(out['joined']))
        self.assertEqual(out['lines'], 'budget or call failure\nRecord x and retry')
        self.assertEqual(out['unknown'], 'טקסט לא מוכר')
        self.assertEqual(out['empty'], '')
        self.assertIsNone(out['nonstr'])
        self.assertEqual(out['stage'], 'Translating')
        self.assertEqual(out['he'], 'תקציב או כשל בקריאה')
        self.assertEqual(out['heT'], amount)


if __name__ == '__main__':
    unittest.main()
