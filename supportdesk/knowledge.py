"""Local knowledge base search for agent grounding."""

from __future__ import annotations

import json
import re
import zlib
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
        articles = [
            _article_from_markdown(markdown_path, path)
            for markdown_path in sorted(path.rglob("*.md"))
        ]
        return cls(articles)

    @classmethod
    def from_pdf(cls, path: Path) -> "KnowledgeBase":
        return cls([_article_from_pdf(path, path.parent)])

    @classmethod
    def from_document_dir(cls, path: Path) -> "KnowledgeBase":
        articles = []
        for markdown_path in sorted(path.rglob("*.md")):
            articles.append(_article_from_markdown(markdown_path, path))
        for pdf_path in sorted(path.rglob("*.pdf")):
            articles.append(_article_from_pdf(pdf_path, path))
        return cls(articles)

    @classmethod
    def from_path(cls, path: Path) -> "KnowledgeBase":
        if path.is_dir():
            return cls.from_document_dir(path)
        if path.suffix.lower() == ".pdf":
            return cls.from_pdf(path)
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
            matches.append(
                KnowledgeMatch(article=article, score=round(score, 2), matched_terms=matched_terms)
            )

        return sorted(matches, key=lambda match: match.score, reverse=True)[:limit]


def _article_from_markdown(markdown_path: Path, root: Path) -> KnowledgeArticle:
    front_matter, body = _split_front_matter(markdown_path.read_text(encoding="utf-8"))
    relative_id = markdown_path.relative_to(root).with_suffix("").as_posix()
    title = str(front_matter.get("title") or _first_heading(body) or _title_from_stem(markdown_path))
    category = str(front_matter.get("category") or "general")
    team = str(front_matter.get("team") or "Support Operations")
    keywords = _parse_keywords(front_matter.get("keywords", ""))

    return KnowledgeArticle(
        id=str(front_matter.get("id") or _slugify(relative_id)),
        title=title.strip(),
        category=category.strip() or "general",
        content=_content_without_title(body).strip(),
        team=team.strip() or "Support Operations",
        keywords=keywords,
    )


def _article_from_pdf(pdf_path: Path, root: Path) -> KnowledgeArticle:
    metadata = _document_metadata(pdf_path)
    relative_id = pdf_path.relative_to(root).with_suffix("").as_posix()
    content = _extract_pdf_text(pdf_path)
    if not content:
        content = "No extractable text found. Use searchable text PDFs for best results."

    return KnowledgeArticle(
        id=str(metadata.get("id") or _slugify(relative_id)),
        title=str(metadata.get("title") or _title_from_stem(pdf_path)).strip(),
        category=str(metadata.get("category") or "general").strip() or "general",
        content=content,
        team=str(metadata.get("team") or "Support Operations").strip() or "Support Operations",
        keywords=_parse_keywords(metadata.get("keywords", "")),
    )


def _document_metadata(path: Path) -> dict[str, object]:
    sidecar = path.with_suffix(".json")
    if not sidecar.exists():
        return {}
    with sidecar.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


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


def _extract_pdf_text(path: Path) -> str:
    data = path.read_bytes()
    if not data.startswith(b"%PDF"):
        raise ValueError(f"{path} is not a PDF file")

    chunks = []
    stream_pattern = re.compile(rb"<<(.*?)>>\s*stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
    for match in stream_pattern.finditer(data):
        dictionary, stream = match.groups()
        content = stream.strip(b"\r\n")
        if b"/FlateDecode" in dictionary:
            try:
                content = zlib.decompress(content)
            except zlib.error:
                continue

        decoded = content.decode("latin-1", errors="ignore")
        chunks.extend(_pdf_literal_strings(decoded))
        chunks.extend(_pdf_hex_strings(decoded))

    return _clean_pdf_text(" ".join(chunks))


def _pdf_literal_strings(content: str) -> list[str]:
    values = []
    index = 0
    while index < len(content):
        if content[index] != "(":
            index += 1
            continue

        index += 1
        depth = 1
        buffer = []
        while index < len(content) and depth:
            char = content[index]
            if char == "\\":
                escaped, index = _read_pdf_escape(content, index + 1)
                buffer.append(escaped)
                continue
            if char == "(":
                depth += 1
                buffer.append(char)
            elif char == ")":
                depth -= 1
                if depth:
                    buffer.append(char)
            else:
                buffer.append(char)
            index += 1

        value = "".join(buffer).strip()
        if value:
            values.append(value)
    return values


def _read_pdf_escape(content: str, index: int) -> tuple[str, int]:
    if index >= len(content):
        return "", index

    char = content[index]
    escapes = {"n": "\n", "r": "\n", "t": "\t", "b": "\b", "f": "\f", "\\": "\\", "(": "(", ")": ")"}
    if char in escapes:
        return escapes[char], index + 1
    if char in "\r\n":
        if char == "\r" and index + 1 < len(content) and content[index + 1] == "\n":
            return "", index + 2
        return "", index + 1
    if char in "01234567":
        octal = char
        index += 1
        for _ in range(2):
            if index < len(content) and content[index] in "01234567":
                octal += content[index]
                index += 1
        return chr(int(octal, 8)), index
    return char, index + 1


def _pdf_hex_strings(content: str) -> list[str]:
    values = []
    for match in re.finditer(r"<([0-9A-Fa-f\s]+)>", content):
        raw = re.sub(r"\s+", "", match.group(1))
        if not raw:
            continue
        if len(raw) % 2:
            raw += "0"
        try:
            data = bytes.fromhex(raw)
        except ValueError:
            continue
        values.append(_decode_pdf_bytes(data))
    return [value for value in values if value]


def _decode_pdf_bytes(data: bytes) -> str:
    if data.startswith(b"\xfe\xff"):
        return data[2:].decode("utf-16-be", errors="ignore")
    return data.decode("latin-1", errors="ignore")


def _clean_pdf_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
