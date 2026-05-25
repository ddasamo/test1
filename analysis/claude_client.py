"""Claude Opus 4.7로 5가지 이론별 분석을 수행 (Phase 3에서 구현)."""

from pathlib import Path

THEORIES = {
    "flanders": "Flanders 언어상호작용분석",
    "irf": "IRF 시퀀스 구조 분석",
    "wait_time": "Rowe Wait Time 분석",
    "bloom": "Bloom 발문 인지수준 분석",
    "feedback": "MET 피드백 9유형 분석",
}

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(theory_key: str) -> str:
    return (PROMPTS_DIR / f"{theory_key}.md").read_text(encoding="utf-8")


def analyze(theory_key: str, refined_transcript: str) -> str:
    """Claude Opus 4.7 호출 → Markdown 분석 결과 반환.

    Phase 3 구현 예정:
      - anthropic.Anthropic().messages.create(model="claude-opus-4-7", ...)
      - system = 해당 이론 프롬프트
      - user = 정제 전사 텍스트
      - prompt caching으로 system 블록 캐싱
    """
    raise NotImplementedError("Phase 3에서 구현")
