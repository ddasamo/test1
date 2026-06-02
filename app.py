"""Gradio 진입점 — CLOVA Note 전사 텍스트 붙여넣기 → 정제 → 이론별 분석 + κ Export."""

import json
import tempfile
import traceback
from pathlib import Path

import gradio as gr

from analysis.claude_client import THEORIES, analyze
from analysis.export import (
    bloom_to_csv,
    build_unified_json,
    flanders_to_csv,
)
from pipeline.parse_clova import parse_clova_text
from pipeline.refine import refine, render_text

CLOVA_PLACEHOLDER = """예시 (CLOVA Note 다운로드 형식):

화자1 00:00:03
안녕하세요 여러분, 오늘 수업을 시작할게요.

화자2 00:00:12
네 선생님 안녕하세요.

화자1 00:00:18
자, 그러면 지난 시간에 배운 내용을 복습해볼까요?
...
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
                "각 발화 줄에 '화자N HH:MM:SS' 또는 '화자N MM:SS' 헤더가 있어야 합니다."
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
