"""STT + 화자분할 파이프라인 (Phase 1에서 구현)."""

from dataclasses import dataclass


@dataclass
class Utterance:
    start: float        # 초
    end: float
    speaker: str        # pyannote 원본 라벨 (SPEAKER_00 등)
    text: str


def transcribe(audio_path: str) -> list[Utterance]:
    """오디오 파일을 발화 단위 리스트로 변환.

    Phase 1 구현 예정:
      1. faster-whisper(large-v3, word_timestamps=True)로 단어 단위 전사
      2. pyannote.audio(speaker-diarization-3.1)로 화자 구간 추출
      3. 단어와 화자 구간을 시간 기준으로 매칭 → Utterance 리스트 생성
    """
    raise NotImplementedError("Phase 1에서 구현")
