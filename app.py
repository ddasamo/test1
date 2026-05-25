"""Gradio 진입점 — Phase 4에서 전체 UI 완성 예정."""

import gradio as gr

from analysis.claude_client import THEORIES


def handle_upload(audio_file):
    if audio_file is None:
        return "오디오 파일을 업로드해주세요."
    return (
        f"업로드 완료: {audio_file}\n"
        "Phase 1(STT+화자분할), Phase 2(정제) 구현 후 결과가 여기에 표시됩니다."
    )


def run_theory(theory_key: str, refined_transcript: str):
    if not refined_transcript:
        return "먼저 전사를 완료해주세요."
    return f"[{THEORIES[theory_key]}] — Phase 3에서 Claude Opus 호출 연결 예정"


with gr.Blocks(title="수업 발화 분석기") as demo:
    gr.Markdown("# 🎓 수업 발화 분석기\n수업 녹음(mp3)을 업로드하면 자동 전사 후 5가지 이론으로 분석합니다.")

    with gr.Row():
        audio_in = gr.Audio(label="수업 녹음 파일", type="filepath", sources=["upload"])
        with gr.Column():
            transcribe_btn = gr.Button("1) 전사 + 화자 정제 실행", variant="primary")
            transcript_out = gr.Textbox(label="정제된 전사", lines=20, interactive=False)

    transcribe_btn.click(handle_upload, inputs=audio_in, outputs=transcript_out)

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
