import unittest

from matchapi import Matcher
from regexlite import Regex


class TestRegexLite(unittest.TestCase):
    def test_literal_search(self):
        self.assertEqual(Regex("ab").search("zzabzz")[:2], (2, 4))

    def test_literal_missing(self):
        self.assertIsNone(Regex("ab").search("zzz"))

    def test_literal_anchored(self):
        self.assertEqual(Regex("ab").match("abzz")[:2], (0, 2))

    def test_stats_shape(self):
        self.assertIn("nodes", Regex("ab").stats())

    def test_matcher_wraps_regex(self):
        self.assertEqual(Matcher("ab").search("zzab")[:2], (2, 4))


if __name__ == "__main__":
    unittest.main()
