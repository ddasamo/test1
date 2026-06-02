"""화자 라벨링된 발화 데이터 구조."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Word:
    start: float
    end: float
    text: str
    speaker: str | None = None


@dataclass
class Utterance:
    start: float
    end: float
    speaker: str
    text: str
    words: list[Word] = field(default_factory=list)
