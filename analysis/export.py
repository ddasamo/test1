"""CSV + 통합 JSON export — 인간-AI 일치도(Cohen's κ) 측정 및 재현가능성."""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from .claude_client import MODEL, PROMPT_VERSION, AnalysisResult

FLANDERS_CIRCLE_TO_INT: dict[str, int] = {
    "①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5,
    "⑥": 6, "⑦": 7, "⑧": 8, "⑨": 9, "⑩": 10,
}
FLANDERS_NAMES: dict[int, str] = {
    1: "감정수용", 2: "칭찬", 3: "아이디어수용", 4: "질문",
    5: "강의", 6: "지시", 7: "비판", 8: "반응", 9: "자발", 10: "침묵",
}
BLOOM_NAMES: dict[str, str] = {
    "L1": "기억", "L2": "이해", "L3": "적용",
    "L4": "분석", "L5": "평가", "L6": "창조",
}
OPENNESS_KR: dict[str, str] = {"open": "열림", "closed": "닫힘"}

_TRANSCRIPT_LINE_RE = re.compile(r"^([A-Za-z]+\d+(?:_\d+)?)\s*:\s*(.+)$")
_KST = timezone(timedelta(hours=9))


def _parse_flanders_category(raw: Any) -> int | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if s in FLANDERS_CIRCLE_TO_INT:
        return FLANDERS_CIRCLE_TO_INT[s]
    if s.isdigit():
        n = int(s)
        return n if 1 <= n <= 10 else None
    m = re.search(r"\d+", s)
    if m:
        n = int(m.group(0))
        return n if 1 <= n <= 10 else None
    return None


def _build_content_lookup(refined_transcript: str) -> dict[str, str]:
    """전사 라인 → utterance_id → 내용 매핑."""
    lookup: dict[str, str] = {}
    for line in refined_transcript.splitlines():
        m = _TRANSCRIPT_LINE_RE.match(line.strip())
        if m:
            lookup[m.group(1)] = m.group(2).strip()
    return lookup


def _disagreement_flag(item: dict) -> str:
    """3-run 일치도 < 1.0이면 TRUE."""
    agr = item.get("_test_retest_agreement")
    return "TRUE" if (agr is not None and agr < 1.0) else "FALSE"


def flanders_to_csv(result: AnalysisResult, refined_transcript: str) -> str:
    content_lookup = _build_content_lookup(refined_transcript)
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "utterance_id", "speaker", "content",
        "flanders_AI", "flanders_name_AI", "rationale_AI",
        "flanders_human_coder1", "flanders_human_coder2",
        "disagreement_flag",
    ])
    for item in result.consensus_classifications:
        uid = item.get("utterance_id", "")
        cat_int = _parse_flanders_category(item.get("category"))
        writer.writerow([
            uid,
            item.get("speaker", ""),
            content_lookup.get(uid, ""),
            cat_int if cat_int is not None else "",
            FLANDERS_NAMES.get(cat_int, "") if cat_int else "",
            item.get("rationale", ""),
            "", "",
            _disagreement_flag(item),
        ])
    return buf.getvalue()


def bloom_to_csv(result: AnalysisResult, refined_transcript: str) -> str:
    content_lookup = _build_content_lookup(refined_transcript)
    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "question_id", "utterance_id", "content",
        "bloom_AI", "bloom_name_AI", "openness_AI", "rationale_AI",
        "bloom_human_coder1", "bloom_human_coder2",
        "disagreement_flag",
    ])
    for idx, item in enumerate(result.consensus_classifications, start=1):
        uid = item.get("utterance_id", "")
        level = item.get("bloom_level", "")
        openness_raw = item.get("openness", "")
        writer.writerow([
            f"Q{idx:02d}",
            uid,
            item.get("question_text") or content_lookup.get(uid, ""),
            level,
            BLOOM_NAMES.get(level, ""),
            OPENNESS_KR.get(openness_raw, openness_raw),
            item.get("rationale", ""),
            "", "",
            _disagreement_flag(item),
        ])
    return buf.getvalue()


def _now_iso() -> str:
    return datetime.now(_KST).isoformat(timespec="seconds")


def _default_session_id() -> str:
    return datetime.now(_KST).strftime("session_%Y%m%d_%H%M%S")


def build_unified_json(
    flanders_result: AnalysisResult | None,
    bloom_result: AnalysisResult | None,
    refined_transcript: str,
    session_id: str | None = None,
) -> str:
    """사양 6.2 통합 JSON. 두 분석 모두 없어도 동작(빈 결과)."""
    content_lookup = _build_content_lookup(refined_transcript)
    total = len(content_lookup)
    teacher = sum(1 for uid in content_lookup if uid.startswith("T"))
    student = sum(1 for uid in content_lookup if uid.startswith("S"))
    silence = refined_transcript.count("(침묵")

    payload: dict[str, Any] = {
        "session_id": (session_id or "").strip() or _default_session_id(),
        "input_metadata": {
            "total_utterances": total,
            "teacher_utterances": teacher,
            "student_utterances": student,
            "silence_count": silence,
            "transcription_source": "Naver Clova Note + auto refine",
        },
        "flanders_results": flanders_result.consensus_classifications if flanders_result else [],
        "bloom_results": bloom_result.consensus_classifications if bloom_result else [],
        "model_info": {
            "llm": MODEL,
            "prompt_version": PROMPT_VERSION,
            "analyzed_at": _now_iso(),
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
