"""Gradio 진입점 — CLOVA Note 전사 텍스트 붙여넣기 → 정제 → 이론별 분석."""

import json
import tempfile
import traceback
from pathlib import Path

import gradio as gr

from analysis.claude_client import THEORIES, analyze
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
        lines = refine(utterances)
        return render_text(lines)
    except Exception:
        return "정제 중 오류가 발생했습니다.\n\n" + traceback.format_exc()


def run_theory(theory_key: str, refined_transcript: str) -> tuple[str, str | None]:
    """이론 분석을 실행하고 (markdown, json_file_path)를 반환."""
    if (
        not refined_transcript
        or refined_transcript.startswith("CLOVA")
        or refined_transcript.startswith("전사 텍스트")
        or refined_transcript.startswith("정제 중")
    ):
        return "먼저 전사 정제를 완료해주세요.", None
    try:
        result = analyze(theory_key, refined_transcript)
    except Exception:
        return "분석 중 오류가 발생했습니다.\n\n" + traceback.format_exc(), None

    tmp_dir = Path(tempfile.gettempdir())
    json_path = tmp_dir / f"analysis_{theory_key}.json"
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

    header = ""
    if result.cache_hit:
        header += "_(캐시된 결과)_\n\n"
    else:
        u = result.usage
        header += (
            f"_(분석 완료 — 입력 {u['input_tokens']:,} / 출력 {u['output_tokens']:,} 토큰, "
            f"캐시 읽기 {u['cache_read_input_tokens']:,})_\n\n"
        )

    return header + result.markdown, str(json_path)


with gr.Blocks(title="수업 발화 분석기") as demo:
    gr.Markdown(
        "# 🎓 수업 발화 분석기\n"
        "**CLOVA Note**에서 받은 시간 표기 전사 텍스트를 붙여넣으면, "
        "교사/학생 화자를 자동 매핑하고 이론별로 분석합니다."
    )

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
                json_file = gr.File(label="분석 결과 JSON (다운로드)", visible=True)
                analyze_btn.click(
                    fn=lambda t, k=key: run_theory(k, t),
                    inputs=transcript_out,
                    outputs=[analysis_md, json_file],
                )


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, show_api=False)
