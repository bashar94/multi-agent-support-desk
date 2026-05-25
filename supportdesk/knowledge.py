"""Local knowledge base search for agent grounding."""

from __future__ import annotations

import json
from pathlib import Path

from supportdesk.models import KnowledgeArticle, KnowledgeMatch
from supportdesk.text import keyword_score, tokenize


class KnowledgeBase:
    def __init__(self, articles: list[KnowledgeArticle]) -> None:
        self.articles = articles

    @classmethod
    def from_json(cls, path: Path) -> "KnowledgeBase":
        with path.open("r", encoding="utf-8") as handle:
            raw_articles = json.load(handle)

        articles = [
            KnowledgeArticle(
                id=str(item["id"]),
                title=str(item["title"]),
                category=str(item["category"]),
                content=str(item["content"]),
                team=str(item["team"]),
                keywords=[str(keyword) for keyword in item.get("keywords", [])],
            )
            for item in raw_articles
        ]
        return cls(articles)

    def search(self, query: str, category: str = "", limit: int = 3) -> list[KnowledgeMatch]:
        query_terms = set(tokenize(query))
        matches: list[KnowledgeMatch] = []

        for article in self.articles:
            article_text = " ".join(
                [
                    article.title,
                    article.category,
                    " ".join(article.keywords),
                    article.content,
                    article.team,
                ]
            )
            keyword_points, keyword_hits = keyword_score(query, article.keywords)
            overlap = sorted(query_terms.intersection(set(tokenize(article_text))))
            category_boost = 2.5 if category and article.category == category else 0.0
            score = keyword_points + len(overlap) * 0.6 + category_boost

            if score <= 0:
                continue

            matched_terms = sorted(set(keyword_hits + overlap))
            matches.append(KnowledgeMatch(article=article, score=round(score, 2), matched_terms=matched_terms))

        return sorted(matches, key=lambda match: match.score, reverse=True)[:limit]
