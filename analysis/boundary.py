"""L2/L4 경계 사례 자동 추출 (v3 사양 §4 — 본 연구 학술적 차별성).

AI가 직접 is_boundary_case=true로 지정한 발문 + 다음 폴백 조건을 만족하는 발문을 추출:
- bloom_level이 L2 또는 L4이고
- confidence가 '중'/'하' 이거나
- 3단 질문 답에 모호함/논리 비일관성이 있는 경우

각 경계 사례에 대해 "왜 경계인가"를 자동 설명.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from .claude_client import AnalysisResult
from .export import _build_content_lookup


def derive_is_boundary(item: dict) -> bool:
    """AI 출력에 is_boundary_case가 없을 때 폴백 판정."""
    level = item.get("bloom_level", "")
    confidence = item.get("confidence", "")
    bc = item.get("boundary_check") or {}

    if level not in ("L2", "L4"):
        return False
    if confidence in ("중", "하"):
        return True

    qs = [bc.get("q1", ""), bc.get("q2", ""), bc.get("q3", "")]
    if any(q == "모호" for q in qs):
        return True
    # Q1=예(L2 신호)인데 L4로 분류 → 경계
    if level == "L4" and bc.get("q1") == "예":
        return True
    # Q2=예(L4 신호)인데 L2로 분류 → 경계
    if level == "L2" and bc.get("q2") == "예":
        return True
    return False


def is_boundary_case(item: dict) -> bool:
    """AI 명시값 우선, 없으면 derive_is_boundary 폴백."""
    flag = item.get("is_boundary_case")
    if flag is True:
        return True
    if flag is False:
        return False
    return derive_is_boundary(item)


def explain_why_boundary(item: dict) -> str:
    level = item.get("bloom_level", "")
    confidence = item.get("confidence", "")
    bc = item.get("boundary_check") or {}
    reasons: list[str] = []

    if confidence in ("중", "하"):
        reasons.append(f"confidence가 '{confidence}'로 모호함")

    qs = [bc.get("q1"), bc.get("q2"), bc.get("q3")]
    if any(q == "모호" for q in qs):
        reasons.append("3단 질문 중 모호한 답 포함")

    if level == "L4" and bc.get("q1") == "예":
        reasons.append("Q1=예(교재에 답 있음)인데 L4로 분류 — L2와 경계")
    if level == "L2" and bc.get("q2") == "예":
        reasons.append("Q2=예(근거·관계 구성 필요)인데 L2로 분류 — L4와 경계")

    if not reasons:
        reasons.append("AI가 is_boundary_case=true로 직접 지정")
    return "; ".join(reasons)


def filter_boundary_cases(result: AnalysisResult) -> list[dict]:
    """경계로 판정된 분류만 추출."""
    return [
        item
        for item in result.consensus_classifications
        if is_boundary_case(item)
    ]


def boundary_to_csv(result: AnalysisResult, refined_transcript: str) -> str:
    """v3 사양 §4.2 — boundary_cases.csv 생성."""
    content_lookup = _build_content_lookup(refined_transcript)
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "question_id", "content", "ai_bloom_level", "ai_rationale",
        "q1", "q2", "q3", "confidence",
        "prior_student_response", "why_boundary",
    ])
    for idx, item in enumerate(filter_boundary_cases(result), start=1):
        uid = item.get("utterance_id", "")
        bc = item.get("boundary_check") or {}
        writer.writerow([
            item.get("question_id") or f"BQ{idx:02d}",
            item.get("question_text") or content_lookup.get(uid, ""),
            item.get("bloom_level", ""),
            item.get("rationale", ""),
            bc.get("q1", ""),
            bc.get("q2", ""),
            bc.get("q3", ""),
            item.get("confidence", ""),
            item.get("prior_student_response") or "",
            explain_why_boundary(item),
        ])
    return buf.getvalue()


def boundary_distribution(result: AnalysisResult) -> dict[str, Any]:
    """통합 JSON의 distributions 섹션에 들어갈 통계."""
    total = len(result.consensus_classifications)
    cases = filter_boundary_cases(result)
    return {
        "boundary_case_count": len(cases),
        "boundary_case_ratio": round(len(cases) / total, 3) if total else 0.0,
    }
