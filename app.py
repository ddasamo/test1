"""Gradio 진입점 — 업로드 → 전사 → 이론별 분석."""

import json
import tempfile
import traceback
from pathlib import Path

import gradio as gr

from analysis.claude_client import THEORIES, analyze
from pipeline.refine import refine, render_text
from pipeline.transcribe import transcribe


def handle_transcribe(audio_file: str | None) -> str:
    if audio_file is None:
        return "오디오 파일을 업로드해주세요."
    try:
        utterances = transcribe(audio_file)
        lines = refine(utterances)
        return render_text(lines)
    except Exception:
        return "전사 중 오류가 발생했습니다.\n\n" + traceback.format_exc()


def run_theory(theory_key: str, refined_transcript: str) -> tuple[str, str | None]:
    """이론 분석을 실행하고 (markdown, json_file_path)를 반환."""
    if not refined_transcript or refined_transcript.startswith("오디오") or refined_transcript.startswith("전사 중"):
        return "먼저 전사를 완료해주세요.", None
    try:
        result = analyze(theory_key, refined_transcript)
    except Exception:
        return "분석 중 오류가 발생했습니다.\n\n" + traceback.format_exc(), None

    # JSON export 파일 생성 (인간 코더 결과와 일치도 측정용)
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
        "수업 녹음(mp3)을 업로드하면 자동 전사 후 이론별로 분석합니다."
    )

    with gr.Row():
        audio_in = gr.Audio(label="수업 녹음 파일", type="filepath", sources=["upload"])
        with gr.Column():
            transcribe_btn = gr.Button("1) 전사 + 화자 정제 실행", variant="primary")
            transcript_out = gr.Textbox(label="정제된 전사", lines=20, interactive=False)

    transcribe_btn.click(handle_transcribe, inputs=audio_in, outputs=transcript_out)

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
