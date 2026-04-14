# KT Irene Studio

KT 사내에서 사용하는 AI 아나운서(아이린) 영상 제작용 웹 서비스입니다.

## 지금 상태
- 상단 툴바 + 좌측 미리보기 + 우측 씬 편집 형태의 UI로 동작합니다.
- 씬 생성/최종 렌더 결과 파일은 **정적 경로가 아닌 API 다운로드 경로**로 제공되어 404 가능성을 줄였습니다.
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
1. `새로 만들기`
2. 씬 카드에서 `씬 생성`
3. `영상 추가하기`로 전체 씬 + 최종 렌더
4. 생성된 `씬 영상/최종 결과` 링크 확인

## 점검 엔드포인트
- `GET /health`
- `GET /api/projects/{project_id}/scenes/{scene_id}/video`
- `GET /api/projects/{project_id}/final-video`

## 계속 같은 화면/오류가 보일 때
- 서버를 완전히 재시작한 뒤 접속하세요.
- 브라우저에서 `Ctrl + Shift + R`(강력 새로고침)을 하세요.
- `/health` 응답의 `build` 값이 `2026.04.14-2` 인지 확인하세요.
