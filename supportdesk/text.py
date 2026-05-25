"""Text helpers used by deterministic local agents."""

from __future__ import annotations

import re
from collections import Counter

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_'-]*")

STOP_WORDS = {
    "a",
    "about",
    "after",
    "all",
    "am",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "by",
    "can",
    "could",
    "do",
    "for",
    "from",
    "had",
    "has",
    "have",
    "i",
    "if",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "please",
    "that",
    "the",
    "this",
    "to",
    "we",
    "with",
    "you",
    "your",
}


def normalize(text: str) -> str:
    return " ".join(text.lower().split())


def tokenize(text: str) -> list[str]:
    return [token for token in TOKEN_RE.findall(normalize(text)) if token not in STOP_WORDS]


def token_counts(text: str) -> Counter[str]:
    return Counter(tokenize(text))


def phrase_hits(text: str, phrases: list[str]) -> list[str]:
    normalized = normalize(text)
    return [phrase for phrase in phrases if phrase in normalized]


def keyword_score(text: str, keywords: list[str]) -> tuple[float, list[str]]:
    normalized = normalize(text)
    counts = token_counts(text)
    score = 0.0
    hits: list[str] = []

    for keyword in keywords:
        keyword_normalized = normalize(keyword)
        if " " in keyword_normalized:
            if keyword_normalized in normalized:
                score += 3.0
                hits.append(keyword)
            continue

        count = counts.get(keyword_normalized, 0)
        if count:
            score += 1.0 + min(count, 4) * 0.25
            hits.append(keyword)

    return score, sorted(set(hits))
