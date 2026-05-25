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
3. **이론별 분석** (Claude Opus 4.7):
   - **Flanders 언어상호작용분석** (FIACS, 1959) — 발화량 구조 + 영향력 방향
   - **Bloom 신교육목표분류학** (Anderson & Krathwohl, 2001) + Alexander 대화적 교수법 — 발문 인지수준
   - *향후 확장*: IRF(Sinclair & Coulthard 1975 / Wells 1993), Rowe Wait Time, MET 피드백 9유형

## 연구 목적

본 도구는 **AI 분석과 인간 분석자의 일치도 검증** 및
**교사 수업변화 추적**을 위한 KCI 논문 연구의 분석 인프라다.
각 이론별 출력에는 인간 코더 결과와 비교 가능한 JSON 블록이 포함된다.

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
│   ├── flanders.md         # 현재 활성
│   └── bloom.md            # 현재 활성
├── docs/
│   ├── methodology_decisions.md   # 논문 Methods 인용용 의사결정 기록
│   ├── coding_manual_flanders.md  # 인간 코더용 Flanders 분류 매뉴얼
│   └── coding_manual_bloom.md     # 인간 코더용 Bloom 분류 매뉴얼
└── requirements.txt
```

## 환경 변수 (HF Space Secrets)

| 변수 | 용도 |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API 호출 |
| `HF_TOKEN` | pyannote.audio 모델 다운로드 (HF Hub 게이트 모델) |
