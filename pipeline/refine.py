"""전사 정제: pyannote 화자 라벨 → T/S 매핑 + 침묵 삽입 + 연속 발화 병합.

화자 식별 규칙 (docs/methodology_decisions.md 결정 7 참조)
  1. 화자별 총 발화 시간 + 단서어 빈도 집계
  2. 발화 시간 1위가 단서어 빈도 1위와 일치 → T 확정
  3. 두 지표가 불일치 → 단서어 빈도 우선 (학생 장발표 케이스 대비)
  4. 나머지 화자들은 총 발화 시간 내림차순으로 S1, S2, S3, ...
  5. 발화 간 간격 ≥ 3.0초 → (침묵 N초) 라인 자동 삽입 (Rowe 기준)
  6. 동일 라벨 연속 발화는 한 항목으로 병합
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .transcribe import Utterance


@dataclass
class RefinedLine:
    tag: str            # "T001", "S1_001", "(침묵 N초)" 등
    text: str
    start: float | None = None
    end: float | None = None


TEACHER_CUES: tuple[str, ...] = (
    "친구들", "여러분",
    "자,", "자 ",
    "시작할게요", "시작하겠습니다", "시작합시다",
    "이동할게요", "이동하겠습니다",
    "다음으로", "다음은",
    "정리하겠습니다", "정리할게요",
    "시간 됐", "시간이 됐",
    "잘했어요", "잘했어",
    "조용히",
)


def _count_cues(text: str) -> int:
    return sum(text.count(cue) for cue in TEACHER_CUES)


def _identify_teacher(utterances: list[Utterance]) -> str | None:
    """화자 라벨 중 교사로 추정할 라벨을 반환. 발화가 없으면 None."""
    if not utterances:
        return None
    duration_by_speaker: dict[str, float] = defaultdict(float)
    cues_by_speaker: dict[str, int] = defaultdict(int)
    for u in utterances:
        duration_by_speaker[u.speaker] += max(0.0, u.end - u.start)
        cues_by_speaker[u.speaker] += _count_cues(u.text)

    top_by_duration = max(duration_by_speaker, key=duration_by_speaker.get)
    if any(c > 0 for c in cues_by_speaker.values()):
        top_by_cues = max(cues_by_speaker, key=cues_by_speaker.get)
    else:
        top_by_cues = top_by_duration  # 단서어 없으면 발화 시간 1위로 폴백

    # 규칙 2~3: 일치하면 그 라벨, 불일치하면 단서어 우선
    return top_by_cues if top_by_cues == top_by_duration else top_by_cues


def _build_speaker_map(utterances: list[Utterance], teacher_label: str | None) -> dict[str, str]:
    """pyannote 라벨 → 'T' 또는 'S1', 'S2', ... 매핑 생성."""
    duration_by_speaker: dict[str, float] = defaultdict(float)
    for u in utterances:
        duration_by_speaker[u.speaker] += max(0.0, u.end - u.start)

    mapping: dict[str, str] = {}
    if teacher_label is not None and teacher_label in duration_by_speaker:
        mapping[teacher_label] = "T"

    student_labels = [
        s for s in sorted(
            duration_by_speaker, key=lambda k: duration_by_speaker[k], reverse=True
        )
        if s != teacher_label
    ]
    for idx, label in enumerate(student_labels, start=1):
        mapping[label] = f"S{idx}"
    return mapping


def _merge_consecutive(utterances: list[Utterance]) -> list[Utterance]:
    """동일 화자의 연속 발화를 하나로 합친다."""
    if not utterances:
        return []
    merged: list[Utterance] = [utterances[0]]
    for u in utterances[1:]:
        last = merged[-1]
        if u.speaker == last.speaker:
            merged[-1] = Utterance(
                start=last.start,
                end=u.end,
                speaker=last.speaker,
                text=f"{last.text} {u.text}".strip(),
                words=last.words + u.words,
            )
        else:
            merged.append(u)
    return merged


def _format_lines(
    utterances: list[Utterance],
    speaker_map: dict[str, str],
    silence_threshold: float,
) -> list[RefinedLine]:
    """병합된 발화 → 번호 부여 + 침묵 라인 삽입."""
    lines: list[RefinedLine] = []
    teacher_counter = 0
    student_counters: dict[str, int] = defaultdict(int)
    prev_end: float | None = None

    for u in utterances:
        # 침묵 삽입
        if prev_end is not None:
            gap = u.start - prev_end
            if gap >= silence_threshold:
                lines.append(
                    RefinedLine(
                        tag=f"(침묵 {gap:.1f}초)",
                        text="",
                        start=prev_end,
                        end=u.start,
                    )
                )

        mapped = speaker_map.get(u.speaker, "S?")
        if mapped == "T":
            teacher_counter += 1
            tag = f"T{teacher_counter:03d}"
        else:
            student_counters[mapped] += 1
            tag = f"{mapped}_{student_counters[mapped]:03d}"

        lines.append(RefinedLine(tag=tag, text=u.text, start=u.start, end=u.end))
        prev_end = u.end

    return lines


def refine(utterances: list[Utterance], silence_threshold: float = 3.0) -> list[RefinedLine]:
    """pyannote 출력 → T/S 매핑 + 침묵 삽입 + 연속 발화 병합.

    Args:
        utterances: transcribe()의 출력
        silence_threshold: 침묵 라인 삽입 임계점 (초). 기본 3.0 (Rowe 기준)

    Returns:
        정제된 라인 리스트. 각 라인은 발화 또는 침묵 표시.
    """
    if not utterances:
        return []
    teacher_label = _identify_teacher(utterances)
    speaker_map = _build_speaker_map(utterances, teacher_label)
    merged = _merge_consecutive(utterances)
    return _format_lines(merged, speaker_map, silence_threshold)


def render_text(lines: list[RefinedLine]) -> str:
    """RefinedLine 리스트를 사람이 읽기 좋은 텍스트로 변환."""
    rendered: list[str] = []
    for line in lines:
        if line.tag.startswith("(침묵"):
            rendered.append(line.tag)
        else:
            rendered.append(f"{line.tag}: {line.text}")
    return "\n".join(rendered)
