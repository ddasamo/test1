"""STT + 화자분할 파이프라인.

faster-whisper(large-v3)로 단어 단위 전사를 수행하고,
pyannote.audio(speaker-diarization-3.1)로 화자 구간을 추출한 뒤,
두 결과를 시간 기준으로 정렬해 발화 단위 리스트를 생성한다.

요구 환경변수
  HF_TOKEN: pyannote 게이트 모델 다운로드용 (필수)

요구 사전 동의
  https://huggingface.co/pyannote/speaker-diarization-3.1
  https://huggingface.co/pyannote/segmentation-3.0
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import torch
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline


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
    speaker: str        # pyannote 원본 라벨 (예: "SPEAKER_00")
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class TranscribeConfig:
    whisper_model: str = "small"
    language: str = "ko"
    diarization_model: str = "pyannote/speaker-diarization-3.1"
    # 한 발화 내 단어 간 최대 허용 간격(초). 이보다 크면 새 발화로 분리.
    word_gap_threshold: float = 1.0


def _select_device() -> tuple[str, str]:
    if torch.cuda.is_available():
        return "cuda", "float16"
    return "cpu", "int8"


def _run_whisper(audio_path: str, config: TranscribeConfig) -> list[Word]:
    device, compute_type = _select_device()
    model = WhisperModel(config.whisper_model, device=device, compute_type=compute_type)
    segments, _ = model.transcribe(
        audio_path,
        language=config.language,
        word_timestamps=True,
        vad_filter=True,
    )
    words: list[Word] = []
    for segment in segments:
        if not segment.words:
            continue
        for w in segment.words:
            if w.start is None or w.end is None:
                continue
            words.append(Word(start=float(w.start), end=float(w.end), text=w.word.strip()))
    return words


def _run_diarization(audio_path: str, config: TranscribeConfig) -> list[tuple[float, float, str]]:
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError(
            "HF_TOKEN 환경변수가 필요합니다. pyannote 게이트 모델 다운로드용 토큰을 설정하세요."
        )
    pipeline = Pipeline.from_pretrained(config.diarization_model, use_auth_token=token)
    device, _ = _select_device()
    pipeline.to(torch.device(device))
    diarization = pipeline(audio_path)
    return [
        (float(segment.start), float(segment.end), str(speaker))
        for segment, _, speaker in diarization.itertracks(yield_label=True)
    ]


def _assign_speakers(words: list[Word], speaker_segments: list[tuple[float, float, str]]) -> None:
    """각 단어의 중간 시점이 속하는 화자 구간을 찾아 라벨 부여 (in-place)."""
    if not speaker_segments:
        return
    # 화자 구간을 시작 시간 기준 정렬 (대부분 정렬돼 있지만 안전하게)
    segments = sorted(speaker_segments, key=lambda s: s[0])
    seg_idx = 0
    for word in words:
        mid = (word.start + word.end) / 2.0
        # 단어 mid 이전에 끝나는 구간은 건너뛴다
        while seg_idx < len(segments) and segments[seg_idx][1] < mid:
            seg_idx += 1
        if seg_idx >= len(segments):
            # 마지막 구간 이후로 떨어진 경우 → 가장 가까운 구간에 매칭
            word.speaker = segments[-1][2]
            continue
        start, end, spk = segments[seg_idx]
        if start <= mid <= end:
            word.speaker = spk
        else:
            # mid가 구간 사이 공백에 떨어진 경우 → 직전·직후 중 가까운 쪽
            prev_seg = segments[seg_idx - 1] if seg_idx > 0 else None
            next_seg = segments[seg_idx]
            if prev_seg is None:
                word.speaker = next_seg[2]
            else:
                dist_prev = abs(mid - prev_seg[1])
                dist_next = abs(next_seg[0] - mid)
                word.speaker = prev_seg[2] if dist_prev <= dist_next else next_seg[2]


def _group_into_utterances(words: list[Word], config: TranscribeConfig) -> list[Utterance]:
    """같은 화자의 연속된 단어들을 한 발화로 묶는다.

    분리 조건:
      - 화자가 바뀜
      - 같은 화자라도 단어 간 간격이 word_gap_threshold(초) 초과
    """
    utterances: list[Utterance] = []
    current: list[Word] = []
    for word in words:
        if not word.speaker:
            continue
        if not current:
            current = [word]
            continue
        last = current[-1]
        same_speaker = word.speaker == last.speaker
        gap = word.start - last.end
        if same_speaker and gap <= config.word_gap_threshold:
            current.append(word)
        else:
            utterances.append(_words_to_utterance(current))
            current = [word]
    if current:
        utterances.append(_words_to_utterance(current))
    return utterances


def _words_to_utterance(words: list[Word]) -> Utterance:
    text = " ".join(w.text for w in words).strip()
    return Utterance(
        start=words[0].start,
        end=words[-1].end,
        speaker=words[0].speaker or "UNKNOWN",
        text=text,
        words=list(words),
    )


def transcribe(audio_path: str, config: TranscribeConfig | None = None) -> list[Utterance]:
    """오디오 파일을 발화 단위 리스트로 변환.

    Args:
        audio_path: mp3/wav 등 오디오 파일 경로
        config: 전사·화자분할 설정 (생략 시 기본값)

    Returns:
        시간 순으로 정렬된 Utterance 리스트
    """
    cfg = config or TranscribeConfig()
    words = _run_whisper(audio_path, cfg)
    speakers = _run_diarization(audio_path, cfg)
    _assign_speakers(words, speakers)
    return _group_into_utterances(words, cfg)
