"""Local knowledge base search for agent grounding."""

from __future__ import annotations

import json
import re
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

    @classmethod
    def from_markdown_dir(cls, path: Path) -> "KnowledgeBase":
        articles = []
        for markdown_path in sorted(path.rglob("*.md")):
            front_matter, body = _split_front_matter(markdown_path.read_text(encoding="utf-8"))
            relative_id = markdown_path.relative_to(path).with_suffix("").as_posix()
            title = str(front_matter.get("title") or _first_heading(body) or _title_from_stem(markdown_path))
            category = str(front_matter.get("category") or "general")
            team = str(front_matter.get("team") or "Support Operations")
            keywords = _parse_keywords(front_matter.get("keywords", ""))

            articles.append(
                KnowledgeArticle(
                    id=str(front_matter.get("id") or _slugify(relative_id)),
                    title=title.strip(),
                    category=category.strip() or "general",
                    content=_content_without_title(body).strip(),
                    team=team.strip() or "Support Operations",
                    keywords=keywords,
                )
            )
        return cls(articles)

    @classmethod
    def from_path(cls, path: Path) -> "KnowledgeBase":
        if path.is_dir():
            return cls.from_markdown_dir(path)
        return cls.from_json(path)

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


def _split_front_matter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    front_matter: dict[str, str] = {}
    body_start = 0
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body_start = index + 1
            break
        if ":" in line:
            key, value = line.split(":", 1)
            front_matter[key.strip().lower()] = value.strip()
    else:
        return {}, text

    return front_matter, "\n".join(lines[body_start:]).strip()


def _parse_keywords(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    raw = str(value or "").strip()
    if not raw:
        return []
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]

    return [item.strip().strip("\"'") for item in raw.split(",") if item.strip().strip("\"'")]


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return ""


def _content_without_title(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("# "):
        return "\n".join(lines[1:]).strip()
    return text.strip()


def _title_from_stem(path: Path) -> str:
    return path.stem.replace("-", " ").replace("_", " ").title()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "article"
