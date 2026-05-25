"""Gradio 진입점.

Phase A: STT + 화자분할 + 정제까지 연결.
Phase B: Claude 분석은 다음 단계에서 연결 예정.
"""

import traceback

import gradio as gr

from analysis.claude_client import THEORIES
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


def run_theory(theory_key: str, refined_transcript: str) -> str:
    if not refined_transcript:
        return "먼저 전사를 완료해주세요."
    return f"[{THEORIES[theory_key]}] — Phase B에서 Claude Opus 호출 연결 예정"


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
                analyze_btn = gr.Button(f"{label} 실행")
                analysis_out = gr.Markdown()
                analyze_btn.click(
                    fn=lambda t, k=key: run_theory(k, t),
                    inputs=transcript_out,
                    outputs=analysis_out,
                )


if __name__ == "__main__":
    demo.launch()
