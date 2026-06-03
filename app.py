"""Gradio 진입점 — CLOVA Note 전사 텍스트 붙여넣기 → 정제 → 이론별 분석 + κ Export."""

import json
import tempfile
import traceback
from pathlib import Path

import gradio as gr

from analysis.boundary import boundary_to_csv, filter_boundary_cases
from analysis.claude_client import THEORIES, analyze
from analysis.export import (
    bloom_to_csv,
    build_unified_json,
    flanders_to_csv,
)
from config import FLANDERS_ENABLED
from pipeline.parse_clova import parse_clova_text
from pipeline.refine import refine, render_text

CLOVA_PLACEHOLDER = """CLOVA Note 다운로드 텍스트를 그대로 붙여넣으세요.

예시:

참석자 1 00:03
안녕하세요 여러분, 오늘 수업을 시작할게요.

참석자 2 00:12
네 선생님 안녕하세요.

참석자 1 00:18
자, 그러면 지난 시간에 배운 내용을 복습해볼까요?
...

⚠️ 첫 발화부터 '참석자 N MM:SS' 헤더가 있어야 인식됩니다.
헤더가 없는 맨 앞 텍스트는 무시되므로, 필요하면 수동으로 헤더를 추가해주세요.
"""

TMP_DIR = Path(tempfile.gettempdir())


def handle_paste(clova_text: str) -> str:
    if not clova_text or not clova_text.strip():
        return "CLOVA Note 전사 텍스트를 붙여넣어주세요."
    try:
        utterances = parse_clova_text(clova_text)
        if not utterances:
            return (
                "전사 텍스트에서 화자/시간 형식을 인식하지 못했습니다.\n"
                "각 발화는 '참석자 N MM:SS' (또는 '화자 N MM:SS') 헤더로 시작해야 합니다.\n"
                "예: '참석자 2 47:46' 다음 줄에 발화 내용."
            )
        return render_text(refine(utterances))
    except Exception:
        return "정제 중 오류가 발생했습니다.\n\n" + traceback.format_exc()


def _is_error_transcript(text: str) -> bool:
    return (
        not text
        or text.startswith("CLOVA")
        or text.startswith("전사 텍스트")
        or text.startswith("정제 중")
    )


def run_theory(
    theory_key: str,
    refined_transcript: str,
) -> tuple[str, str | None, str | None, object | None]:
    """이론 분석 → (markdown, json_path, csv_path, result_state)."""
    if _is_error_transcript(refined_transcript):
        return "먼저 전사 정제를 완료해주세요.", None, None, None
    try:
        result = analyze(theory_key, refined_transcript)
    except Exception:
        return "분석 중 오류가 발생했습니다.\n\n" + traceback.format_exc(), None, None, None

    json_path = TMP_DIR / f"analysis_{theory_key}.json"
    json_path.write_text(
        json.dumps(
            {
                "theory": result.theory,
                "consensus_classifications": result.consensus_classifications,
                "usage": result.usage,
                "cache_hit": result.cache_hit,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    if theory_key == "flanders":
        csv_text = flanders_to_csv(result, refined_transcript)
    elif theory_key == "bloom":
        csv_text = bloom_to_csv(result, refined_transcript)
    else:
        csv_text = ""
    csv_path = TMP_DIR / f"{theory_key}_coding.csv"
    csv_path.write_text(csv_text, encoding="utf-8-sig")  # BOM → 엑셀 한글 정상 표시

    if result.cache_hit:
        header = "_(캐시된 결과)_\n\n"
    else:
        u = result.usage
        header = (
            f"_(분석 완료 — 입력 {u['input_tokens']:,} / 출력 {u['output_tokens']:,} 토큰, "
            f"캐시 읽기 {u['cache_read_input_tokens']:,})_\n\n"
        )

    return header + result.markdown, str(json_path), str(csv_path), result


def run_boundary(bloom_result: object | None, refined_transcript: str) -> tuple[str, str | None]:
    """Bloom 결과에서 L2/L4 경계 사례만 추출 → (요약 markdown, CSV 경로)."""
    if bloom_result is None:
        return "먼저 **Bloom 분석**을 실행해주세요.", None
    if _is_error_transcript(refined_transcript):
        return "전사문이 비어 있습니다.", None

    cases = filter_boundary_cases(bloom_result)  # type: ignore[arg-type]
    total = len(bloom_result.consensus_classifications)  # type: ignore[union-attr]
    if total == 0:
        return "Bloom 분석 결과가 비어 있습니다.", None

    ratio = len(cases) / total * 100
    lines = [
        f"### L2/L4 경계 사례 추출 결과",
        f"총 발문 **{total}건** 중 경계 사례 **{len(cases)}건** ({ratio:.1f}%)",
        "",
    ]
    for case in cases[:10]:
        qid = case.get("question_id", "?")
        lvl = case.get("bloom_level", "?")
        cf = case.get("confidence", "?")
        text = (case.get("question_text") or "")[:80]
        lines.append(f"- **{qid}** [{lvl} / confidence={cf}]: {text}")
    if len(cases) > 10:
        lines.append(f"\n_… 외 {len(cases) - 10}건 더 (CSV에 전체 포함)_")

    csv_text = boundary_to_csv(bloom_result, refined_transcript)  # type: ignore[arg-type]
    path = TMP_DIR / "boundary_cases.csv"
    path.write_text(csv_text, encoding="utf-8-sig")
    return "\n".join(lines), str(path)


def export_unified(
    flanders_result: object | None,
    bloom_result: object | None,
    refined_transcript: str,
    session_id: str,
) -> str | None:
    """저장된 두 분석 결과 + 전사문 + session_id → 통합 JSON 파일."""
    if _is_error_transcript(refined_transcript):
        return None
    if flanders_result is None and bloom_result is None:
        return None
    payload = build_unified_json(
        flanders_result=flanders_result,  # type: ignore[arg-type]
        bloom_result=bloom_result,  # type: ignore[arg-type]
        refined_transcript=refined_transcript,
        session_id=session_id,
    )
    path = TMP_DIR / "unified.json"
    path.write_text(payload, encoding="utf-8")
    return str(path)


with gr.Blocks(title="수업 발화 분석기") as demo:
    gr.Markdown(
        "# 🎓 수업 발화 분석기\n"
        "**CLOVA Note** 전사 텍스트를 붙여넣으면 교사/학생 화자 매핑 + 이론별 분석을 수행하고, "
        "**Cohen's κ 측정용 CSV**와 통합 JSON을 제공합니다."
    )

    flanders_state = gr.State()
    bloom_state = gr.State()
    states = {"flanders": flanders_state, "bloom": bloom_state}

    with gr.Row():
        clova_in = gr.Textbox(
            label="CLOVA Note 전사 텍스트 붙여넣기",
            placeholder=CLOVA_PLACEHOLDER,
            lines=18,
        )
        with gr.Column():
            refine_btn = gr.Button("1) 화자 정제 실행", variant="primary")
            transcript_out = gr.Textbox(label="정제된 전사", lines=18, interactive=False)

    refine_btn.click(handle_paste, inputs=clova_in, outputs=transcript_out)

    gr.Markdown("## 2) 이론별 분석")
    with gr.Tabs():
        for key, label in THEORIES.items():
            if key == "flanders" and not FLANDERS_ENABLED:
                continue
            with gr.Tab(label):
                analyze_btn = gr.Button(f"{label} 실행", variant="primary")
                analysis_md = gr.Markdown()
                with gr.Row():
                    json_file = gr.File(label="분석 결과 JSON")
                    csv_file = gr.File(label="κ 측정용 CSV (인간 코더 컬럼 빈 칸)")
                analyze_btn.click(
                    fn=lambda t, k=key: run_theory(k, t),
                    inputs=transcript_out,
                    outputs=[analysis_md, json_file, csv_file, states[key]],
                )

        with gr.Tab("L2/L4 경계 사례 (v3 핵심)"):
            gr.Markdown(
                "Bloom 분석에서 **AI가 is_boundary_case=true로 지정**했거나, "
                "**confidence가 '중/하'** 인 발문, 또는 **3단 질문 답이 분류와 모순**인 발문만 "
                "별도 추출합니다. 본 연구 학술적 차별성의 핵심 데이터입니다."
            )
            boundary_btn = gr.Button("L2/L4 경계 사례 추출", variant="primary")
            boundary_summary = gr.Markdown()
            boundary_csv = gr.File(label="boundary_cases.csv")
            boundary_btn.click(
                run_boundary,
                inputs=[bloom_state, transcript_out],
                outputs=[boundary_summary, boundary_csv],
            )

    gr.Markdown(
        "## 3) 통합 Export — 재현가능성용\n"
        "Flanders + Bloom 결과를 하나의 JSON으로 묶고, session_id / prompt_version / "
        "model / 분석 시각 메타데이터를 함께 기록합니다."
    )
    with gr.Row():
        session_id_in = gr.Textbox(
            label="Session ID (선택)",
            placeholder="예: 20260603_class01 (비우면 자동 생성)",
        )
        unified_btn = gr.Button("통합 JSON 생성", variant="secondary")
    unified_file = gr.File(label="통합 JSON 다운로드")
    unified_btn.click(
        export_unified,
        inputs=[flanders_state, bloom_state, transcript_out, session_id_in],
        outputs=unified_file,
    )


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, show_api=False)
