# KT Irene Studio MVP

아이린 AI 아나운서용 사내 웹 서비스 프로토타입입니다.

## 기능
- 뉴스 대본 입력 + 템플릿(A~F) + 씬 길이(5~10초) 설정
- 권장 글자수 기반 씬 자동 분할
- 씬 단위 생성/재생성 (대본 수정 포함)
- 간이 TTS(wav placeholder) 생성
- 씬별 영상 산출(mp4 가능 시 moviepy, 실패 시 placeholder)
- 최종 합성 렌더링

## 실행
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

브라우저에서 `http://127.0.0.1:8000` 접속.

## 참고
- 실제 KT 믿음 TTS/실제 얼굴 고정 생성 모델 연동 전 MVP 구조입니다.
- `data/projects/<project_id>`에 씬 산출물과 `project.json`이 저장됩니다.
