# KT Irene Studio

KT 사내에서 사용하는 AI 아나운서(아이린) 영상 제작용 웹 서비스입니다.

## 지금 상태
- 상단 툴바 + 좌측 미리보기 + 우측 씬 편집 형태의 UI로 동작합니다.
- 씬 생성/최종 렌더 결과 파일은 **정적 경로가 아닌 API 다운로드 경로**로 제공되어 404 가능성을 줄였습니다.
- 씬 생성 시 `moviepy` 우선, 실패 시 `ffmpeg` 폴백으로 MP4 생성을 시도합니다.

## MVP 기능
- 뉴스 대본 입력 + 템플릿(A~F) + 씬 길이(5~10초) 설정
- 권장 글자수 기반 씬 자동 분할
- 씬 단위 생성/재생성 (대본 수정 포함)
- 간이 TTS(wav placeholder) 생성
- 씬별 영상 산출(mp4 가능 시 moviepy/ffmpeg, 실패 시 placeholder)
- 최종 합성 렌더링

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

## 참고
- 실제 KT 믿음 TTS/실제 얼굴 고정 생성 모델 연동 전 MVP 구조입니다.
- `data/projects/<project_id>`에 씬 산출물과 `project.json`이 저장됩니다.

## 충돌 해결 가이드 (README)
머지 충돌이 날 때는 아래 순서로 해결하세요.

```bash
git status
# README.md 열어서 <<<<<<<, =======, >>>>>>> 구간을 수동 정리
git add README.md
git commit -m "Resolve README merge conflict"
```

충돌 마커는 최종 파일에 절대 남기지 않습니다.

## 여러 파일 충돌 한 번에 해결하기
아래 스크립트는 현재 브랜치 기준으로 충돌 파일을 점검/해결할 때 사용합니다.

```bash
# 충돌 마커 점검
./scripts/check_conflicts.sh

# 현재 브랜치(ours) 기준으로 충돌 해결 + add
./scripts/resolve_conflicts_ours.sh
```

그 다음:
```bash
git status
git commit -m "Resolve merge conflicts"
```
