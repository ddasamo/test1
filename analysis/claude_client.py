"""Claude Sonnet 4.6으로 이론별 발화 분석을 수행.

KCI 논문 범위: Flanders + Bloom 두 이론에 집중.
나머지 3개(IRF, Wait Time, Feedback)는 향후 확장 슬롯으로 둔다.

주요 설계 (docs/methodology_decisions.md 결정 8 참조)
  - 동일 전사문에 대해 Claude를 3회 호출 (sequential — prompt cache 활용)
  - 발화별 다수결(majority vote)을 최종 분류로 채택
  - 3회 모두 다르면 confidence: "low"로 강제 표기
  - 결과 캐싱: 같은 (theory, prompt_version, transcript, model) 조합은 디스크에서 재사용
  - prompt caching: system 블록 cache_control: ephemeral
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import anthropic

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 16000
DEFAULT_RUNS = 3

# 논문에 사용하는 이론 (현재 활성)
THEORIES: dict[str, str] = {
    "flanders": "Flanders 언어상호작용분석",
    "bloom": "Bloom 발문 인지수준 분석",
}

# 향후 확장 슬롯 — 프롬프트와 코드 정비되면 THEORIES에 합치기
FUTURE_THEORIES: dict[str, str] = {
    "irf": "IRF 시퀀스 구조 분석",
    "wait_time": "Rowe Wait Time 분석",
    "feedback": "MET 피드백 9유형 분석",
}

ROOT_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = ROOT_DIR / "prompts"
CACHE_DIR = ROOT_DIR / "outputs" / "cache"

JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


@dataclass
class AnalysisResult:
    theory: str
    markdown: str                              # 사용자에게 보여줄 본문 (1차 호출 기반)
    consensus_classifications: list[dict]      # 다수결 결과
    raw_runs: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    cache_hit: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)


def load_prompt(theory_key: str) -> str:
    return (PROMPTS_DIR / f"{theory_key}.md").read_text(encoding="utf-8")


def _cache_key(theory_key: str, transcript: str) -> str:
    prompt = load_prompt(theory_key)
    h = hashlib.sha256()
    h.update(MODEL.encode())
    h.update(b"\n")
    h.update(theory_key.encode())
    h.update(b"\n")
    h.update(prompt.encode("utf-8"))
    h.update(b"\n")
    h.update(transcript.encode("utf-8"))
    return h.hexdigest()


def _load_cache(key: str) -> AnalysisResult | None:
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return AnalysisResult(**data)


def _save_cache(key: str, result: AnalysisResult) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{key}.json"
    path.write_text(result.to_json(), encoding="utf-8")


def _extract_json_block(text: str) -> dict | None:
    matches = JSON_BLOCK_RE.findall(text)
    if not matches:
        return None
    try:
        return json.loads(matches[-1])
    except json.JSONDecodeError:
        return None


def _call_once(client: anthropic.Anthropic, prompt: str, transcript: str) -> tuple[str, dict, dict]:
    """Claude를 1회 호출하고 (markdown_text, parsed_json, usage_dict) 반환."""
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": transcript}],
    )
    text_blocks = [b.text for b in response.content if b.type == "text"]
    text = "\n".join(text_blocks)
    parsed = _extract_json_block(text) or {}
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cache_creation_input_tokens": getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0) or 0,
    }
    return text, parsed, usage


def _majority_vote(runs: list[dict]) -> list[dict]:
    """3회 호출 결과의 classifications를 발화/발문 단위로 다수결.

    각 run["classifications"]는 dict 리스트.
    공통 식별자(utterance_id 또는 question_id)로 묶어 category(혹은 bloom_level)를 다수결.
    """
    id_field_candidates = ("utterance_id", "question_id")
    cat_field_candidates = ("category", "bloom_level")

    by_id: dict[str, list[dict]] = {}
    id_field = None
    cat_field = None

    for run in runs:
        classifications = run.get("classifications", [])
        if not classifications:
            continue
        sample = classifications[0]
        if id_field is None:
            id_field = next((f for f in id_field_candidates if f in sample), None)
            cat_field = next((f for f in cat_field_candidates if f in sample), None)
        if id_field is None or cat_field is None:
            continue
        for item in classifications:
            uid = item.get(id_field)
            if uid is None:
                continue
            by_id.setdefault(uid, []).append(item)

    if id_field is None or cat_field is None:
        return []

    consensus: list[dict] = []
    for uid, items in by_id.items():
        cats = [it.get(cat_field) for it in items]
        counter = Counter(cats)
        top_cat, top_count = counter.most_common(1)[0]
        agreement = top_count / len(items)

        # 1차 결과를 기본 형태로 가져오고 카테고리만 다수결 결과로 덮어씀
        base = dict(items[0])
        base[cat_field] = top_cat
        if agreement >= 1.0:
            pass  # 신뢰도 그대로 유지
        elif agreement >= 0.5:
            # 2/3 일치 → medium 이상이면 유지, low면 medium으로 격상
            if base.get("confidence") == "low":
                base["confidence"] = "medium"
        else:
            # 3개 모두 다르거나 다수결 실패
            base["confidence"] = "low"
        base["_test_retest_agreement"] = round(agreement, 2)
        consensus.append(base)

    return consensus


def analyze(theory_key: str, refined_transcript: str, runs: int = DEFAULT_RUNS) -> AnalysisResult:
    """이론별 분석을 수행하고 결과를 반환.

    Args:
        theory_key: THEORIES 키 ("flanders" | "bloom")
        refined_transcript: refine.render_text() 출력
        runs: 반복 호출 횟수 (기본 3, 다수결용)

    Returns:
        AnalysisResult — markdown 본문 + 다수결 classifications + raw_runs + usage
    """
    if theory_key not in THEORIES and theory_key not in FUTURE_THEORIES:
        raise ValueError(f"Unknown theory key: {theory_key}")

    cache_key = _cache_key(theory_key, refined_transcript)
    cached = _load_cache(cache_key)
    if cached is not None:
        cached.cache_hit = True
        return cached

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")

    client = anthropic.Anthropic()
    prompt = load_prompt(theory_key)

    raw_runs: list[dict[str, Any]] = []
    first_markdown = ""
    total_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }

    # Sequential: prompt cache 활용 (parallel이면 첫 호출 외에는 캐시 못 읽음)
    for i in range(runs):
        try:
            text, parsed, usage = _call_once(client, prompt, refined_transcript)
        except anthropic.APIError as e:
            raise RuntimeError(f"Claude API 호출 실패 (run {i+1}/{runs}): {e}") from e
        if i == 0:
            first_markdown = text
        raw_runs.append({"run": i + 1, "markdown": text, "parsed": parsed, "usage": usage})
        for k in total_usage:
            total_usage[k] += usage.get(k, 0)

    consensus = _majority_vote([r["parsed"] for r in raw_runs])

    result = AnalysisResult(
        theory=theory_key,
        markdown=first_markdown,
        consensus_classifications=consensus,
        raw_runs=raw_runs,
        usage=total_usage,
        cache_hit=False,
    )
    _save_cache(cache_key, result)
    return result
