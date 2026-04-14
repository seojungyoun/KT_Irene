from __future__ import annotations

import re


def recommended_limit_by_seconds(seconds: int) -> int:
    # Korean news pace: ~6-8 chars/sec. choose middle point 7.
    return int(seconds * 7)


def split_script(script: str, max_chars: int) -> list[str]:
    normalized = re.sub(r"\s+", " ", script).strip()
    if not normalized:
        return []

    # Prefer sentence-based split.
    sentence_chunks = [s.strip() for s in re.split(r"(?<=[.!?다])\s+", normalized) if s.strip()]

    scenes: list[str] = []
    for sentence in sentence_chunks:
        if len(sentence) <= max_chars:
            scenes.append(sentence)
            continue

        # Forced split on comma/pauses first.
        phrases = [p.strip() for p in re.split(r"[,،]\s*", sentence) if p.strip()]
        bucket = ""
        for phrase in phrases:
            candidate = f"{bucket}, {phrase}" if bucket else phrase
            if len(candidate) <= max_chars:
                bucket = candidate
            else:
                if bucket:
                    scenes.append(bucket)
                if len(phrase) <= max_chars:
                    bucket = phrase
                else:
                    # Hard wrap by char limit.
                    start = 0
                    while start < len(phrase):
                        scenes.append(phrase[start : start + max_chars])
                        start += max_chars
                    bucket = ""
        if bucket:
            scenes.append(bucket)

    return scenes
