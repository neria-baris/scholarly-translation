"""Structure of Japanese and mixed Japanese/Latin pages (CJK-STRUCTURE).

Synthetic pages with line geometry modelled on a real Japanese journal article: body
lines 10.32pt tall, but 11.31pt when the line also holds digits/Latin letters/ASCII
brackets (the Latin font's taller box), footnote lines 8.88/9.73pt, a 13.9pt title.
"""
import unittest

from scholarly_translation import article_layout as al
from scholarly_translation import document_structure as ds
from scholarly_translation.document_structure import classify_line

LEFT, RIGHT, INDENT = 59.5, 456.6, 69.4
BODY, MIXED = 10.32, 11.31


def _page(lines, page_id="p1"):
    """A resolved digital reading from ``[(text, x0, x1, top, height)]``."""
    text = "\n".join(t for t, *_ in lines)
    anchors, pos = [], 0
    for line, x0, x1, top, height in lines:
        anchors.append({"kind": "line", "source_char_start": pos, "source_char_end": pos + len(line),
                        "bbox": [x0, top, x1, top + height]})
        pos += len(line) + 1
    candidate = {"origin": "digital", "candidate_hash": "h-" + page_id, "anchors": anchors}
    return {"reading_id": "r-" + page_id, "version": 1, "document_id": "d1", "page_id": page_id,
            "language": "ja", "status": "resolved", "text": text,
            "selected": {"origin": "digital", "candidate_hash": "h-" + page_id},
            "alternatives": [candidate], "selected_anchors": anchors}


def _rows(spec, top=100.0, pitch=18.0):
    """``[(text, x0, x1, height)]`` stacked at a regular line pitch."""
    return [(t, x0, x1, top + i * pitch, h) for i, (t, x0, x1, h) in enumerate(spec)]


def _nodes(*pages):
    overrides = al.analyze_readings(list(pages))
    return [(n["kind"], n["text"]) for page in pages
            for n in ds._build_nodes_for_reading(page, None, overrides.get(page["page_id"]))]


BODY_PAGE = _rows([
    ("〈数学の無尽蔵性〉と二つの哲学", LEFT, 261.3, 13.92),
    ("前世紀初頭における数学基礎論論争は、論理主義、直観主義、形式主義の間で起こった", INDENT, RIGHT, BODY),
    ("ものと一般に整理される。そして1931年にクルト・ゲーデル（Kurt Gödel, 1906-1978）の", LEFT, RIGHT, MIXED),
    ("論文によって示されたいわゆる「不完全性定理」が、論争の一つの中断符点をなす。", LEFT, RIGHT, BODY),
    ("本稿は、不完全性定理以降の数理思想の一断面を、よく知られた先の三つの立場とは異", INDENT, RIGHT, BODY),
    ("なった視角から描き出すことを目的とする。いま、すべての数学が含まれるような包括的", LEFT, RIGHT, BODY),
    ("な形式体系Aがあるとせよ。その体系の定理がすべて真であることを数学的に確信できる", LEFT, RIGHT, MIXED),
    ("ならば、「Aは無矛盾である」も数学的確実さをもって同様に主張できる。", LEFT, 380.0, MIXED),
    ("1. ゲーデルにおける数学の現象学", LEFT, 211.0, MIXED),
    ("不完全性定理の結果を示すことから始めよう。今日、この定理は以下の二つの部分から", INDENT, RIGHT, BODY),
    ("なるものとして提示される。", LEFT, 188.8, BODY),
], top=88.0)


class ClassifyLineTests(unittest.TestCase):
    def test_japanese_lines_with_latin_capitals_are_body_text(self):
        for line in ("べての数学が含まれるような包括的な形式体系Aがあるとせよ。その体系の定理がすべて",
                     "ものと一般に整理される。そして1931年にクルト・ゲーデル（Kurt Gödel, 1906-1978）の",
                     "というより強い条件が使われていた。しかし1936年にJ・B・ロッサーの手によって、こ",
                     "1938 年に出版した。それらはいずれも19 世紀以来の数学史の中に集合論の進展と基礎論"):
            self.assertEqual(classify_line(line), ("paragraph", None), line)

    def test_japanese_section_headings(self):
        self.assertEqual(classify_line("1. ゲーデルにおける数学の現象学"), ("subsection", 4))
        self.assertEqual(classify_line("序論"), ("subsection", 4))
        self.assertEqual(classify_line("結論"), ("subsection", 4))

    def test_latin_case_rules_unchanged(self):
        self.assertEqual(classify_line("INTRODUCTION"), ("heading", 5))
        self.assertEqual(classify_line("The Modern Development"), ("heading", 5))
        self.assertEqual(classify_line("2 Results and Discussion"), ("subsection", 4))


class JapaneseParagraphTests(unittest.TestCase):
    def test_mixed_script_lines_are_not_headings_and_paragraphs_follow_indents(self):
        nodes = _nodes(_page(BODY_PAGE))
        self.assertEqual([k for k, _ in nodes], ["heading", "paragraph", "paragraph", "subsection", "paragraph"])
        self.assertTrue(nodes[1][1].startswith("前世紀") and nodes[1][1].endswith("中断符点をなす。"))
        # A full-width line ending in 。 continues its paragraph; the indent starts the next one.
        self.assertTrue(nodes[2][1].startswith("本稿は") and nodes[2][1].endswith("同様に主張できる。"))

    def test_emphasis_dots_and_subscripts_stay_inside_the_paragraph(self):
        lines = _rows([
            ("として、有限命題を引き出すための便利な道具とみなされていたことであろう。ところで、", LEFT, RIGHT, BODY),
            ("ゲーデルが証明したことは、事態がそのようでない、ということであった。数学における", LEFT, RIGHT, BODY),
            ("すなわち、ε までの超限帰納法を用いている限りで、この証明はゲーデルによって示唆", LEFT, RIGHT, BODY),
            ("された数学とメタ数学の交錯の最初の明確な事例をなす。", LEFT, 300.0, BODY),
            ("実際、彼は『抽象集合論の形成』、『公理的方法と形式主義』の二著作で、直観的操作の", INDENT, RIGHT, BODY),
        ])
        dots = ("、、、、、、", 399.9, 459.8, lines[0][3] + BODY - 2.4, BODY)
        subscript = ("0", 205.1, 208.5, lines[2][3] + 5.0, 7.0)
        lines = lines[:1] + [dots] + lines[1:3] + [subscript] + lines[3:]
        nodes = _nodes(_page(lines))
        self.assertEqual([k for k, _ in nodes], ["paragraph", "paragraph"])
        self.assertIn("、、、、、、", nodes[0][1])
        self.assertIn("\n0\n", nodes[0][1])

    def test_without_geometry_a_sentence_end_still_breaks(self):
        raw = ds._classified_lines("一行目の文である。\n二行目の文である。")
        self.assertEqual(len(ds._merge_paragraph_lines("一行目の文である。\n二行目の文である。", raw)), 2)


class JapaneseNotesAndReferencesTests(unittest.TestCase):
    def _back_matter(self):
        body = BODY_PAGE[1:8]
        page1 = _page(body + _rows([
            ("註", LEFT, 68.4, 8.88),
            ("(1) 飯田 (2006, pp. 139–141) を参照。この箇所で分析されているのは、「無尽蔵性」の", LEFT, RIGHT, 9.73),
            ("言葉が登場する一節周辺である。", LEFT, 200.0, 8.88),
            ("(2) 「定理 XI［第二不完全性定理］は、ヒルベルトの形式主義的な視点と矛盾しない」。", LEFT, RIGHT, 9.73),
        ], top=260.0, pitch=12.0), "p1")
        page2 = _page(_rows([
            ("(3) Gödel (1990, pp. 261–264, 邦訳, 26–30頁) を参照。", LEFT, 300.0, 9.73),
            ("文献", LEFT, 80.0, 8.88),
            ("van Atten, M., Kennedy, J. (2003). ‘On the philosophical development of Kurt Gödel,’", LEFT, RIGHT, 8.88),
            ("9, 4, 425–476.", LEFT, 120.0, 8.88),
            ("Gödel, K. (1986). ‘Über formal unentscheidbare Sätze,’ (2006, 林晋・八杉満利", LEFT, RIGHT, 9.73),
            ("子訳, 「プリンキピア・マテマティカおよび関連した体系の命題についてI」, 岩波書店.)", LEFT, RIGHT, 9.73),
            ("ハオ・ワン (1995). 『ゲーデル再考』, 土屋俊・戸田山和久訳, 産業図書.", LEFT, 400.0, 9.73),
        ], top=80.0, pitch=12.0), "p2")
        return _nodes(page1, page2)

    def test_endnotes_and_reference_list(self):
        kinds = [k for k, _ in self._back_matter()]
        self.assertEqual(kinds, ["paragraph", "paragraph", "heading", "note", "note", "note", "heading",
                                 "bibliography_entry", "bibliography_entry", "bibliography_entry"])

    def test_bracketed_note_labels(self):
        self.assertEqual(al.note_label("(12) 「意識はそのたびごとに」"), "12")
        self.assertEqual(al.note_label("（3） 参照。"), "3")

    def test_bracketed_marks_after_japanese_only(self):
        text = "カヴァイエスの第二の肯定的な評価である(8)。関数 f(1) は数式である。"
        marks = al.find_marks(text, ["8", "1"])
        self.assertEqual([(text[s:e], label) for s, e, label in marks], [("(8)", "8")])


if __name__ == "__main__":
    unittest.main()
