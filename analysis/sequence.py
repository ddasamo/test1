"""발문 시퀀스 패턴 + Probing 분석 (v3 사양 §5).

Bloom 분류 결과의 bloom_level 시퀀스를 분석하여 다음 패턴 식별:
- plateau (수평형): 3+ 연속 동일 단계
- stairs (계단형): 3+ 연속 단조 비감소 + 시작보다 끝이 높음
- inductive (귀납형): L1/L2 → L4 → L5/L6 패턴 (6발문 윈도우 이내)
- fragmented (분절형): 5-윈도우 내 distinct 단계 ≥ 4

Probing: 직전 학생 응답이 있고, 발문에 signal word 포함, bloom_level ≥ L4.
"""

from __future__ import annotations

import json
from typing import Any

from .claude_client import AnalysisResult

PROBING_SIGNALS: tuple[str, ...] = (
    "왜", "어떻게", "더 자세히", "예를 들면", "그렇게 생각한 이유",
    "구체적으로", "근거", "이유는",
)


def _level_to_int(raw: Any) -> int:
    if not raw:
        return 0
    s = str(raw).strip().upper()
    if s.startswith("L") and len(s) >= 2 and s[1].isdigit():
        return int(s[1])
    return 0


def _q_label(items: list[dict], idx: int) -> str:
    return items[idx].get("question_id") or f"Q{idx + 1:02d}"


def _detect_plateaus(levels: list[int], qids: list[str]) -> list[dict]:
    out: list[dict] = []
    i = 0
    n = len(levels)
    while i < n:
        if levels[i] == 0:
            i += 1
            continue
        j = i
        while j + 1 < n and levels[j + 1] == levels[i]:
            j += 1
        if j - i + 1 >= 3:
            out.append({
                "type": "plateau",
                "start_question": qids[i],
                "end_question": qids[j],
                "levels": [f"L{l}" for l in levels[i:j + 1]],
            })
        i = j + 1
    return out


def _detect_stairs(levels: list[int], qids: list[str]) -> list[dict]:
    out: list[dict] = []
    n = len(levels)
    i = 0
    while i < n - 2:
        if levels[i] == 0:
            i += 1
            continue
        j = i
        while j + 1 < n and levels[j + 1] >= levels[j] > 0:
            j += 1
        if j - i + 1 >= 3 and levels[j] > levels[i]:
            out.append({
                "type": "stairs",
                "start_question": qids[i],
                "end_question": qids[j],
                "levels": [f"L{l}" for l in levels[i:j + 1]],
            })
            i = j + 1
        else:
            i += 1
    return out


def _detect_inductive(levels: list[int], qids: list[str]) -> list[dict]:
    """L1/L2 → L4 → L5/L6, 인접 6발문 이내. 중첩 방지로 검출 후 i를 패턴 끝 다음으로 이동."""
    out: list[dict] = []
    n = len(levels)
    i = 0
    while i < n - 2:
        if not (1 <= levels[i] <= 2):
            i += 1
            continue
        end_k = -1
        for j in range(i + 1, min(i + 5, n - 1)):
            if levels[j] != 4:
                continue
            for k in range(j + 1, min(i + 7, n)):
                if 5 <= levels[k] <= 6:
                    end_k = k
                    break
            if end_k >= 0:
                break
        if end_k >= 0:
            out.append({
                "type": "inductive",
                "start_question": qids[i],
                "end_question": qids[end_k],
                "levels": [f"L{l}" for l in levels[i:end_k + 1]],
            })
            i = end_k + 1
        else:
            i += 1
    return out


def _detect_fragmented(
    levels: list[int], qids: list[str], window: int = 5, distinct_threshold: int = 4
) -> list[dict]:
    out: list[dict] = []
    n = len(levels)
    if n < window:
        return out
    i = 0
    while i <= n - window:
        win = [l for l in levels[i:i + window] if l > 0]
        if len(win) >= window - 1 and len(set(win)) >= distinct_threshold:
            out.append({
                "type": "fragmented",
                "start_question": qids[i],
                "end_question": qids[i + window - 1],
                "levels": [f"L{l}" if l else "?" for l in levels[i:i + window]],
            })
            i += window  # skip to reduce heavy overlap
        else:
            i += 1
    return out


def detect_patterns(classifications: list[dict]) -> list[dict]:
    levels = [_level_to_int(c.get("bloom_level")) for c in classifications]
    qids = [c.get("question_id") or f"Q{i + 1:02d}" for i, c in enumerate(classifications)]
    return (
        _detect_plateaus(levels, qids)
        + _detect_stairs(levels, qids)
        + _detect_inductive(levels, qids)
        + _detect_fragmented(levels, qids)
    )


def detect_probing(classifications: list[dict]) -> tuple[int, int, list[dict]]:
    """(probing_count, denominator=학생응답이있던_발문수, probing_items)."""
    probing_items: list[dict] = []
    denom = 0
    for item in classifications:
        prior = item.get("prior_student_response")
        if not prior or prior in ("null", "None", ""):
            continue
        denom += 1
        content = str(item.get("question_text") or "")
        if not any(sig in content for sig in PROBING_SIGNALS):
            continue
        if _level_to_int(item.get("bloom_level")) >= 4:
            probing_items.append(item)
    return len(probing_items), denom, probing_items


def build_sequence_json(result: AnalysisResult, session_id: str = "") -> str:
    """v3 사양 §6.3 — sequence_patterns.json."""
    classifications = result.consensus_classifications
    patterns = detect_patterns(classifications)
    probing_count, denom, _ = detect_probing(classifications)
    probing_ratio = round(probing_count / denom, 3) if denom else 0.0

    payload: dict[str, Any] = {
        "session_id": session_id.strip() or "",
        "total_questions": len(classifications),
        "pattern_counts": {
            "plateau": sum(1 for p in patterns if p["type"] == "plateau"),
            "stairs": sum(1 for p in patterns if p["type"] == "stairs"),
            "inductive": sum(1 for p in patterns if p["type"] == "inductive"),
            "fragmented": sum(1 for p in patterns if p["type"] == "fragmented"),
        },
        "patterns_detected": patterns,
        "probing_count": probing_count,
        "probing_denominator": denom,
        "probing_ratio": probing_ratio,
        "probing_denominator_note": "직전 학생 응답이 있던 발문 수 대비",
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
