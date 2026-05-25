"""전사 정제: 화자 매핑 + 침묵 검출 (Phase 2에서 구현)."""

from dataclasses import dataclass

from .transcribe import Utterance


@dataclass
class RefinedLine:
    tag: str            # "T001", "S001", "SS", "(침묵 N초)"
    text: str
    start: float | None = None
    end: float | None = None


TEACHER_CUES = [
    "친구들", "여러분", "자,", "자 ",
    "시작할게요", "시작하겠습니다",
    "이동할게요", "이동하겠습니다",
    "다음으로", "정리하겠습니다", "시간 됐",
]


def refine(utterances: list[Utterance], silence_threshold: float = 3.0) -> list[RefinedLine]:
    """pyannote 화자 라벨을 T/S 라벨로 매핑하고 침묵 구간을 삽입.

    Phase 2 구현 예정:
      1. 화자별 총 발화 시간 + 단서어 빈도 집계
      2. 최다 발화 + 단서어 1위 화자 = T 확정
      3. 다른 화자들은 발화 시간 순으로 S1, S2, S3 …
      4. 두 화자 이상이 겹치면 SS
      5. 연속 발화 사이 간격 ≥ silence_threshold(기본 3초) → (침묵 N초) 라인 삽입
      6. 같은 라벨 연속 발화는 하나로 병합
    """
    raise NotImplementedError("Phase 2에서 구현")
