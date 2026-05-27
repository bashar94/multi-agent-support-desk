import tempfile
import unittest
from pathlib import Path

from supportdesk.knowledge import KnowledgeBase


class MarkdownKnowledgeBaseTest(unittest.TestCase):
    def test_loads_markdown_articles_with_front_matter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            (base / "billing.md").write_text(
                """---
id: kb-refunds
title: Refund Playbook
category: billing
team: Revenue Operations
keywords: [refund, duplicate charge, invoice]
---
# Refund Playbook

Confirm invoice evidence before promising a refund.
""",
                encoding="utf-8",
            )

            knowledge_base = KnowledgeBase.from_markdown_dir(base)

            self.assertEqual(len(knowledge_base.articles), 1)
            article = knowledge_base.articles[0]
            self.assertEqual(article.id, "kb-refunds")
            self.assertEqual(article.title, "Refund Playbook")
            self.assertEqual(article.category, "billing")
            self.assertEqual(article.team, "Revenue Operations")
            self.assertEqual(article.keywords, ["refund", "duplicate charge", "invoice"])
            self.assertNotIn("# Refund Playbook", article.content)

    def test_markdown_loader_uses_fallback_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            (base / "account-access.md").write_text(
                "# Account Access\n\nCollect workspace and account email.",
                encoding="utf-8",
            )

            knowledge_base = KnowledgeBase.from_path(base)
            article = knowledge_base.articles[0]

            self.assertEqual(article.id, "account-access")
            self.assertEqual(article.title, "Account Access")
            self.assertEqual(article.category, "general")
            self.assertEqual(article.team, "Support Operations")


if __name__ == "__main__":
    unittest.main()
