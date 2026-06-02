"""CLOVA Note 형식 텍스트 → Utterance 리스트 파싱.

CLOVA Note는 다음과 같은 형태로 출력합니다 (변형 다수):
    화자1 00:00:03
    안녕하세요 오늘 수업을 시작하겠습니다.

    화자2 00:00:08
    네 선생님.

또는:
    [00:00:03] 화자1: 안녕하세요...
    00:00:08 화자2 네 선생님

파서는 시간 표기(HH:MM:SS 또는 MM:SS)와 화자 라벨이 같은 줄에 있으면
헤더로 보고, 나머지 줄은 직전 화자의 발화 텍스트로 이어붙입니다.
"""

from __future__ import annotations

import re

from .utterance import Utterance

_TS_RE = re.compile(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b")
_SPEAKER_RE = re.compile(
    r"(?:화자\s*\d+|Speaker\s*\d+|SPEAKER[_\s]?\d+|발화자\s*\d+)",
    re.IGNORECASE,
)


def _parse_timestamp(line: str) -> float | None:
    m = _TS_RE.search(line)
    if not m:
        return None
    a, b, c = m.group(1), m.group(2), m.group(3)
    if c is not None:
        return int(a) * 3600 + int(b) * 60 + int(c)
    return int(a) * 60 + int(b)


def _extract_speaker(line: str) -> str | None:
    m = _SPEAKER_RE.search(line)
    if not m:
        return None
    return re.sub(r"\s+", "", m.group(0))


def _strip_header(line: str) -> str:
    """헤더 줄에서 시간/화자 라벨/구두점을 제거하고 나머지 텍스트만 반환."""
    line = _TS_RE.sub("", line)
    line = _SPEAKER_RE.sub("", line)
    return line.strip(" :-[](){}\t")


def parse_clova_text(raw: str) -> list[Utterance]:
    """CLOVA Note 형식 텍스트를 Utterance 리스트로 변환.

    - 화자 라벨과 시간 표기가 함께 있는 줄을 헤더로 인식
    - 이후 빈 줄 또는 다음 헤더 전까지의 줄을 발화 텍스트로 결합
    - end 시간은 다음 발화의 start로 근사 (CLOVA는 시작 시간만 제공)
    """
    utterances: list[Utterance] = []
    cur_speaker: str | None = None
    cur_start: float | None = None
    cur_parts: list[str] = []

    def flush() -> None:
        nonlocal cur_speaker, cur_start, cur_parts
        if cur_speaker is not None and cur_start is not None:
            text = " ".join(p.strip() for p in cur_parts if p.strip())
            if text:
                utterances.append(
                    Utterance(
                        start=cur_start,
                        end=cur_start,
                        speaker=cur_speaker,
                        text=text,
                    )
                )
        cur_parts = []

    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        speaker = _extract_speaker(line)
        ts = _parse_timestamp(line)

        if speaker is not None and ts is not None:
            flush()
            cur_speaker = speaker
            cur_start = ts
            tail = _strip_header(line)
            if tail:
                cur_parts.append(tail)
        else:
            cur_parts.append(line)

    flush()

    # end 시간 보정: 다음 발화의 start, 마지막은 +5초 근사
    for i in range(len(utterances) - 1):
        utterances[i].end = max(utterances[i].start, utterances[i + 1].start)
    if utterances:
        utterances[-1].end = utterances[-1].start + 5.0

    return utterances
