---
title: Classroom Discourse Analyzer
emoji: 🎓
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
license: mit
---

# 수업 발화 분석기 (Classroom Discourse Analyzer)

교사의 수업 녹음 파일(mp3)을 업로드하면, 자동 전사·화자 분할 후
5가지 교실담화 이론에 따라 발화를 분석합니다.

## 분석 파이프라인

1. **STT + 화자분할**: Whisper-large-v3 + pyannote.audio 3.x
2. **전사 정제**: 화자 라벨을 T(교사) / S1, S2, …(학생) / SS(다수)로 매핑,
   3초 이상 침묵 자동 삽입
3. **5가지 이론 분석** (Claude Opus 4.7):
   - Flanders 언어상호작용분석 (FIACS, 1959)
   - Sinclair & Coulthard IRF + Wells(1993) 연쇄 확장
   - Rowe(1974) Wait Time 1 / Wait Time 2
   - Bloom 신교육목표분류학 (Anderson & Krathwohl, 2001) + Alexander 대화적 교수법
   - MET Project(2013) 피드백 9유형 (EV / FW / EL)

## 폴더 구조

```
.
├── app.py                  # Gradio UI 진입점
├── pipeline/
│   ├── transcribe.py       # Whisper + pyannote 결합
│   └── refine.py           # 화자 매핑·침묵 검출
├── analysis/
│   └── claude_client.py    # Claude API 호출
├── prompts/
│   ├── refine.md           # 전사 정제 프롬프트(보조)
│   ├── flanders.md
│   ├── irf.md
│   ├── wait_time.md
│   ├── bloom.md
│   └── feedback.md
└── requirements.txt
```

## 환경 변수 (HF Space Secrets)

| 변수 | 용도 |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API 호출 |
| `HF_TOKEN` | pyannote.audio 모델 다운로드 (HF Hub 게이트 모델) |
