"""INDENTED-QUOTES: block quotations set off by indentation alone become ``quotation`` nodes.

Synthetic pages with geometry modelled on real sources: a Japanese journal article (body at
x=59.5, first-line indent 69.4, quotations at 79.4) and single-/two-column Latin pages.
"""
import unittest

from scholarly_translation import document_structure as ds
from test_cjk_structure import BODY, INDENT, LEFT, RIGHT, _nodes, _page, _rows

QUOTE = 79.4
JA = "前世紀初頭における数学基礎論論争は、論理主義、直観主義、形式主義の間で起こった"
JA_Q = "実際、意味のそのような明確化のための体系的な方法を有すると主張する学問が現在"


def _kinds(*pages):
    return [k for k, _ in _nodes(*pages)]


def _body(n, x0=LEFT, text=JA):
    return [(text, x0, RIGHT, BODY) for _ in range(n)]


class IndentedQuotationTests(unittest.TestCase):
    def test_japanese_block_quotation_between_paragraphs(self):
        page = _rows(
            [(JA, INDENT, RIGHT, BODY)] + _body(4) + [("以下は1961年の草稿の一節である", LEFT, 451.6, BODY)]
            + [(JA_Q, QUOTE, RIGHT, BODY)] * 5 + [("の力等々に対してなされるのである。(Gödel, 1995a, p. 383)", QUOTE, 336.8, BODY)]
            + [(JA, INDENT, RIGHT, BODY)] + _body(4))
        self.assertEqual(_kinds(_page(page)), ["paragraph", "quotation", "paragraph"])

    def test_sentence_end_inside_a_latin_quotation_does_not_split_it(self):
        body = "Avant de s'engager dans cet examen il ne paraît pas déraisonnable de rappeler"
        page = _rows(
            [(body, LEFT + 8, RIGHT, 11.0)] + [(body, LEFT, RIGHT, 11.0)] * 4 + [("comme suit.", LEFT, 150.0, 11.0)]
            + [("Non, ne te mêle pas d'éduquer ces gens-là, laisse-les vivre comme ils sont.", QUOTE, RIGHT - 20, 10.0),
               ("Ils ne connaissent rien de mieux que leur propre condition et leur état actuel", QUOTE, RIGHT - 20, 10.0),
               ("et ils en souffriraient criminellement. (p. 501-502)", QUOTE, 300.0, 10.0)]
            + [(body, LEFT + 8, RIGHT, 11.0)] + [(body, LEFT, RIGHT, 11.0)] * 4, pitch=14.0)
        self.assertEqual(_kinds(_page(page)), ["paragraph", "quotation", "paragraph"])

    def test_two_line_quotation_set_off_by_space(self):
        rows = _rows(_body(6) + [("確定的多様体批判の直前に登場する以下の一節は重要である。", LEFT, 337.6, BODY)])
        quote = _rows([(JA_Q, QUOTE, RIGHT, BODY), ("基礎付けられねばならない (Cavaillès, 1997, p. 84)", QUOTE, 327.9, BODY)],
                      top=rows[-1][3] + 36.0)
        after = _rows([(JA, INDENT, RIGHT, BODY)] + _body(4), top=quote[-1][3] + 36.0)
        self.assertEqual(_kinds(_page(rows + quote + after)), ["paragraph", "quotation", "paragraph"])

    def test_two_indented_lines_without_space_stay_paragraph_text(self):
        page = _rows(_body(5) + [("確定的多様体批判の直前に登場する。", LEFT, 337.6, BODY)]
                     + [(JA_Q, QUOTE, RIGHT, BODY)] * 2 + [(JA, INDENT, RIGHT, BODY)] + _body(4))
        self.assertNotIn("quotation", _kinds(_page(page)))

    def test_quotation_continuing_from_the_previous_page(self):
        page = _rows([(JA_Q, QUOTE, RIGHT, BODY), ("みが考察されていた (Cavaillès, 1981, pp. 143–144)", QUOTE, 300.0, BODY)]
                     + [(JA, INDENT, RIGHT, BODY)] + _body(6))
        self.assertEqual(_kinds(_page(page)), ["quotation", "paragraph"])


class NotAQuotationTests(unittest.TestCase):
    def test_right_column_of_a_two_column_page(self):
        latin = "The participants were asked to solve the problem and explain"
        rows = []
        for i in range(12):
            rows += [(latin, 50.0, 290.0, i * 13.0), (latin, 310.0, 550.0, i * 13.0)]
        page = _page([(t, x0, x1, 100.0 + top, 10.0) for t, x0, x1, top in rows])
        self.assertNotIn("quotation", _kinds(page))

    def test_lines_beside_a_drop_capital(self):
        line = "L'A dit et répété à juste titre que ses ouvrages se divisent en deux"
        page = _rows([("O", 66.0, 101.0, 49.0)], top=95.0) + _rows(
            [(line, 104.5, 368.5, 11.0)] * 3 + [(line, 68.0, 368.5, 11.0)] * 8 + [("fin.", 68.0, 120.0, 11.0)],
            top=100.0, pitch=12.5)
        self.assertNotIn("quotation", _kinds(_page(page)))

    def test_running_header_and_footer_in_the_margin_do_not_set_the_body_edge(self):
        latin = "Mathematical training and reasoning skills were compared across"
        page = (_rows([("PLOS ONE Mathematical training and reasoning skills", 35.0, 576.0, 11.0)], top=37.0)
                + _rows([(latin, 200.0, 570.0, 10.0)] * 10 + [("problem.", 200.0, 260.0, 10.0)], top=76.0, pitch=13.0)
                + _rows([("PLOS ONE | https://doi.org/10.1371/journal.pone.0236153", 35.0, 570.0, 8.0)], top=760.0))
        self.assertNotIn("quotation", _kinds(_page(page)))

    def test_page_whose_lines_join_two_japanese_columns(self):
        merged = "学習者が置かれている様々な背景や社会的 かわらず，ここでは日本語"
        page = _rows(_body(4, text=merged) + [(merged, 87.8, RIGHT, BODY)] * 4 + _body(4, text=merged))
        self.assertNotIn("quotation", _kinds(_page(page)))

    def test_list_item_continuation_lines(self):
        page = _rows(_body(4) + [("• 第一の論点として、確定的多様体の概念を", LEFT, RIGHT, BODY)]
                     + [(JA_Q, QUOTE, RIGHT, BODY)] * 3 + _body(4))
        self.assertNotIn("quotation", _kinds(_page(page)))

    def test_centered_display_lines_share_no_edge(self):
        page = _rows(_body(5) + [("第一行", 200.0, 300.0, BODY), ("第二の行です", 180.0, 320.0, BODY),
                                 ("三", 240.0, 260.0, BODY)] + _body(5))
        self.assertNotIn("quotation", _kinds(_page(page)))

    def test_body_edge_needs_a_share_of_wide_lines(self):
        wide = [{"x0": 35.0}, {"x0": 35.2}] + [{"x0": 200.0}] * 20
        self.assertEqual(ds._body_left(wide, 10.0), 200.0)
        self.assertEqual(ds._body_left([{"x0": 59.5}] * 4 + [{"x0": 79.4}] * 6, 10.0), 59.5)


if __name__ == "__main__":
    unittest.main()
