# Study Result Saver (DOCX 템플릿 유지 + OneDrive 업로드)

연구회 스터디 결과를 앱/시스템에서 입력받아 날짜별 DOCX에 누적 저장하고,
원하면 OneDrive에 업로드 후 공유 링크까지 생성하는 도구입니다.

## 핵심 기능
- 템플릿 DOCX 복사 후 날짜별 파일 생성
- 문서 머릿말/스타일 유지
- 지정한 표에 새 행 추가
- (옵션) Microsoft Graph API로 OneDrive 업로드
- (옵션) 공유 링크 자동 생성

## 설치
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 1) 로컬 저장만
```bash
python app.py \
  --template ./template.docx \
  --output-dir ./outputs \
  --date 2026-05-01 \
  --row "2026-05-01,홍길동,발표주제,피드백"
```

## 2) OneDrive 업로드 + 링크 생성
```bash
python app.py \
  --template ./template.docx \
  --output-dir ./outputs \
  --date 2026-05-01 \
  --row "2026-05-01,홍길동,발표주제,피드백" \
  --upload-onedrive \
  --access-token "<GRAPH_ACCESS_TOKEN>" \
  --drive-id "<DRIVE_ID>" \
  --folder-path "study-results" \
  --link-scope organization \
  --link-type view
```

## 사전 준비 (Graph API)
- Azure 앱 등록
- 권한: `Files.ReadWrite`, `Sites.ReadWrite.All` (정책에 따라 조정)
- OAuth2 Access Token 발급
- 업로드 대상 Drive ID 확인

## 주의사항
- `--row` 컬럼 수는 대상 표 컬럼 수와 같아야 합니다.
- 본 스크립트는 기본적으로 첫 번째 표(`--table-index 0`)에 입력합니다.
