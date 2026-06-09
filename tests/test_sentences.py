import unittest

from pdf_to_html import WordBox, build_sentences, sentence_break


def word(text, x, y):
    return WordBox(text=text, x=x, y=y, w=max(1, len(text) * 5), h=10)


def line(line_id, x, y, text, indexes):
    return {"id": line_id, "x": x, "y": y, "w": 100, "h": 10, "text": text, "wordIndexes": indexes}


def block(block_id, x, line_ids):
    return {"id": block_id, "x": x, "y": 0, "w": 100, "h": 100, "lineIds": line_ids}


class SentenceBreakTests(unittest.TestCase):
    def test_period_requires_following_uppercase_word(self):
        self.assertTrue(sentence_break("Done.", "Next"))
        self.assertFalse(sentence_break("Done.", "next"))
        self.assertFalse(sentence_break("Done.", "123"))

    def test_abbreviation_and_initial_continue_sentence(self):
        self.assertFalse(sentence_break("Dr.", "Smith"))
        self.assertFalse(sentence_break("A.B.", "Smith"))


class BlockTransitionTests(unittest.TestCase):
    def build(self, words, lines, blocks):
        return build_sentences(words, lines, blocks, [], page_width=1000)

    def test_left_block_can_continue_into_next_right_block(self):
        words = [word("continues", 50, 0), word("here", 750, 0)]
        lines = [line(1, 50, 0, "continues", [0]), line(2, 750, 0, "here", [1])]
        sentences = self.build(words, lines, [block(1, 50, [1]), block(2, 750, [2])])
        self.assertEqual([sentence["text"] for sentence in sentences], ["continues here"])

    def test_center_block_only_continues_into_center_block(self):
        words = [word("center", 450, 0), word("continues", 460, 20), word("right", 750, 0)]
        lines = [line(1, 450, 0, "center", [0]), line(2, 460, 20, "continues", [1]), line(3, 750, 0, "right", [2])]
        blocks = [block(1, 450, [1]), block(2, 460, [2]), block(3, 750, [3])]
        sentences = self.build(words, lines, blocks)
        self.assertEqual([sentence["text"] for sentence in sentences], ["center continues", "right"])
        self.assertEqual(sentences[0]["rule"], "text_block_boundary")

    def test_indent_change_splits_inside_block_but_not_on_allowed_transition(self):
        words = [word("first", 50, 0), word("indented", 100, 20), word("right", 750, 0)]
        lines = [line(1, 50, 0, "first", [0]), line(2, 100, 20, "indented", [1]), line(3, 750, 0, "right", [2])]
        blocks = [block(1, 50, [1, 2]), block(2, 750, [3])]
        sentences = self.build(words, lines, blocks)
        self.assertEqual([sentence["text"] for sentence in sentences], ["first", "indented right"])
        self.assertEqual(sentences[0]["rule"], "left_indent_change")


if __name__ == "__main__":
    unittest.main()
