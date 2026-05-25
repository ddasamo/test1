"""Claude Opus 4.7로 이론별 발화 분석을 수행 (Phase 3에서 구현).

KCI 논문 범위: Flanders + Bloom 두 이론에 집중.
나머지 3개(IRF, Wait Time, Feedback)는 향후 확장 슬롯으로 둔다.
"""

from pathlib import Path

# 논문에 사용하는 이론 (현재 활성)
THEORIES = {
    "flanders": "Flanders 언어상호작용분석",
    "bloom": "Bloom 발문 인지수준 분석",
}

# 향후 확장 슬롯 — 프롬프트와 코드 정비되면 THEORIES에 합치기
FUTURE_THEORIES = {
    "irf": "IRF 시퀀스 구조 분석",
    "wait_time": "Rowe Wait Time 분석",
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
