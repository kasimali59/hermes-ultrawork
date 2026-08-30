"""Versioned lexical intent policy for automatic normal-chat routing."""
from __future__ import annotations

import re

POLICY_VERSION = "hermes-ultrawork-normal-chat-v1"
POSITIVE = (
    "in the background", "delegate this", "delegate the task", "use kanban",
    "queue this", "queue the task", "send this to a worker", "send this to the worker",
    "fan this out", "fan out this task",
)
NEGATIVE = (
    "do not delegate", "don't delegate", "no delegation", "do not use kanban",
    "don't use kanban", "no kanban", "do not queue", "don't queue", "no background",
    "just answer", "answer only", "plan only", "do not execute",
)
ACTION_TOKENS = frozenset({
    "analyze", "build", "create", "document", "fix", "implement", "investigate",
    "migrate", "plan", "refactor", "research", "review", "test", "update", "verify", "write",
})
MENTION_PREFIXES = frozenset({"example", "phrase", "text", "literal", "quote", "say", "contains"})


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    words = [re.escape(word) for word in phrase.split()]
    return re.compile(r"(?<!\w)" + r"[\W_]+".join(words) + r"(?!\w)", re.IGNORECASE)


def _protected_spans(text: str) -> str:
    text = re.sub(r"```.*?```", lambda match: " " * len(match.group(0)), text, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", lambda match: " " * len(match.group(0)), text)
    return re.sub(r"(?:\"[^\"]*\"|'[^']*')", lambda match: " " * len(match.group(0)), text)


def _is_mention(text: str, start: int) -> bool:
    prefix = text[:start]
    words = re.findall(r"\w+", prefix.casefold())
    return bool(words and words[-1] in MENTION_PREFIXES)


def _matches(text: str, phrases: tuple[str, ...], *, mentions: bool) -> tuple[str, ...]:
    visible = _protected_spans(text)
    found = []
    for phrase in phrases:
        for match in _phrase_pattern(phrase).finditer(visible):
            if not mentions or not _is_mention(visible, match.start()):
                found.append(phrase)
                break
    return tuple(found)


def classify_intent(text: str) -> dict[str, object]:
    """Return deterministic lexical intent without inspecting configuration or host state."""
    if not isinstance(text, str) or not text.strip():
        return {"positive": (), "negative": (), "complete": False}
    negative = _matches(text, NEGATIVE, mentions=False)
    positive = _matches(text, POSITIVE, mentions=True)
    visible = _protected_spans(text)
    for phrase in positive:
        visible = _phrase_pattern(phrase).sub(" ", visible)
    tokens = re.findall(r"\b[\w]+\b", visible.casefold())
    complete = len(tokens) >= 3 and bool(ACTION_TOKENS.intersection(tokens))
    return {"positive": positive, "negative": negative, "complete": complete}


class IntentClassifier:
    def classify(self, text: str, platform: str | None = None) -> dict[str, object]:
        del platform
        return classify_intent(text)