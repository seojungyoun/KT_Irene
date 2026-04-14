# KT Irene Studio

KT 사내에서 사용하는 AI 아나운서(아이린) 영상 제작용 웹 서비스입니다.

## 지금 상태
- 프로젝트 생성 → 씬 생성/수정 → 최종 렌더까지 **한 화면에서 동작**합니다.
- UI는 요청하신 편집기 레이아웃(상단 툴바 + 좌측 미리보기 + 우측 편집 영역) 형태로 구성했습니다.
- 씬 생성 시 `moviepy` 우선, 실패 시 `ffmpeg` 폴백으로 MP4 생성을 시도합니다.

## 실행
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

브라우저: `http://127.0.0.1:8000`

## 사용 순서
1. 상단 `새로 만들기` 클릭
2. 씬 카드에서 `씬 생성`
3. 전체 자동 처리하려면 `영상 추가하기` 클릭
4. 최종 내보내기만 하려면 `내보내기 렌더`

## 404(Not Found) 발생 시
- 대부분은 이전 JS 캐시가 남아 생깁니다.
- 브라우저 강력 새로고침(Ctrl+Shift+R) 후 다시 시도해 주세요.
- 서버 `http://127.0.0.1:8000/health` 가 `{"status":"ok"}` 인지 확인하세요.

## 저장 위치
- `data/projects/<project_id>/scene_*/scene.mp4`
- `data/projects/<project_id>/scene_*/tts.wav`
- `data/projects/<project_id>/scene_*/subtitle.srt`
- `data/projects/<project_id>/final.mp4`
