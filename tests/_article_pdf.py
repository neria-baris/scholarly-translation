"""Synthetic journal article PDF for ARTICLE-NOTES tests (reportlab, no network).

Three A4 pages: a running header and a page number on every page, 11pt body text with
superscript note marks, 8pt footnotes under a rule at the page bottom (note 2 continues on
page 2), a display formula and an inline power, and a reference list on page 3."""
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

HEADER = "Journal of Test Studies 12 (2024) 101-140"
BODY = 11
NOTE = 8
LEFT = 72


def _body(c, y, parts):
    """``parts``: strings, or ("sup", "1") for a raised note mark right after the text."""
    x = LEFT
    for part in parts:
        if isinstance(part, tuple):
            c.setFont("Times-Roman", 7)
            c.drawString(x, y + 4, part[1])
            x += c.stringWidth(part[1], "Times-Roman", 7)
        else:
            c.setFont("Times-Roman", BODY)
            c.drawString(x, y, part)
            x += c.stringWidth(part, "Times-Roman", BODY)
    return y - BODY * 1.4


def _notes(c, lines):
    y = 72 + NOTE * 1.3 * len(lines)
    c.line(LEFT, y + 6, LEFT + 120, y + 6)
    c.setFont("Times-Roman", NOTE)
    for text in lines:
        c.drawString(LEFT, y, text)
        y -= NOTE * 1.3


def _frame(c, number):
    c.setFont("Times-Roman", 9)
    c.drawString(LEFT, 800, HEADER)
    c.drawString(290, 40, str(number))


def build(path):
    c = canvas.Canvas(str(path), pagesize=A4)
    _frame(c, 101)
    y = 760
    c.setFont("Times-Bold", 14)
    c.drawString(LEFT, y, "Justice and the Measure of Things")
    y -= 30
    y = _body(c, y, ["The argument of this essay is that justice is a relation between persons,"])
    y = _body(c, y, ["as argued earlier by several authors.", ("sup", "1"), " The relation is not a quantity, and"])
    y = _body(c, y, ["the measure x2 of a claim is never its weight. Rawls defends a similar view,", ("sup", "2")])
    y = _body(c, y, ["although he does not use the word relation in this sense at all."])
    y = _body(c, y, ["E = mc2 (3)"])
    y = _body(c, y, ["The equation (3) is only an analogy for the argument that follows here."])
    _notes(c, ["1 See Smith (2019), p. 4, and the discussion in Jones (2020).",
               "2 Rawls, A Theory of Justice, 1971, where the view is developed at length",
               "over several chapters and in the later lectures on political"])
    c.showPage()
    _frame(c, 102)
    y = 760
    y = _body(c, y, ["A second claim follows from the first one without further assumptions;", ("sup", "3")])
    y = _body(c, y, ["the persons who stand in the relation need not be equals in every respect."])
    _notes(c, ["liberalism, which revise the earlier account in important ways.",
               "3 On equality of standing see Anderson (1999)."])
    c.showPage()
    _frame(c, 103)
    y = 760
    y = _body(c, y, ["This concludes the argument of the essay about the relation of justice."])
    c.setFont("Times-Bold", 12)
    c.drawString(LEFT, y - 10, "References")
    y -= 34
    for line in ["Anderson, E. (1999). What is the point of equality? Ethics 109,",
                 "    287-337.",
                 "Rawls, J. (1971). A Theory of Justice. Cambridge, MA: Harvard University Press.",
                 "Smith, A. (2019). Relations and Measures. Oxford: Clarendon Press."]:
        c.setFont("Times-Roman", 10)
        c.drawString(LEFT, y, line)
        y -= 14
    c.showPage()
    c.save()
    return path
