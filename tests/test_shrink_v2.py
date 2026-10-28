"""PromptShrink v2: redundancy, gated telegraphic, v1 unchanged."""
import unittest

from greensearch.shrink import shrink, shrink_v2


class TestShrinkV2(unittest.TestCase):
    def test_v1_unchanged(self):
        self.assertEqual(shrink("Could you please explain how DNS works?").text,
                         "Explain how DNS works?")

    def test_duplicate_word_removed(self):
        self.assertEqual(shrink_v2("Explain why that that happens").text,
                         "Explain why that happens")

    def test_duplicate_sentence_removed(self):
        self.assertEqual(shrink_v2("Explain DNS. Explain DNS.").text, "Explain DNS.")

    def test_telegraphic_simple(self):
        self.assertEqual(shrink_v2("Explain the DNS system").text, "Explain DNS system")

    def test_telegraphic_gated_off_multi_sentence(self):
        out = shrink_v2("Explain the DNS system. It is important for a small business.").text
        self.assertIn("the DNS", out)

    def test_telegraphic_gated_off_fence(self):
        prompt = "Explain the DNS system\n```\nthe the code\n```"
        out = shrink_v2(prompt).text
        self.assertIn("the the code", out)

    def test_empty_unchanged(self):
        r = shrink_v2("   ")
        self.assertEqual(r.text, "   ")
        self.assertEqual(r.saved_tokens, 0)

    def test_count_fn_respected(self):
        r = shrink_v2("Explain the DNS system", count_fn=lambda s: len(s.split()))
        self.assertEqual(r.original_tokens, 4)
        self.assertEqual(r.shrunk_tokens, 3)
        self.assertEqual(r.saved_tokens, 1)


if __name__ == "__main__":
    unittest.main()
