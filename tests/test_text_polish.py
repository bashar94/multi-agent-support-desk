import unittest

from supportdesk.agents import article_for


class TextPolishTest(unittest.TestCase):
    def test_article_for_category_phrase(self) -> None:
        self.assertEqual(article_for("account access"), "an")
        self.assertEqual(article_for("billing"), "a")


if __name__ == "__main__":
    unittest.main()
