# KT Irene Studio

KT 사내에서 사용하는 AI 아나운서(아이린) 영상 제작용 웹 서비스입니다.

## 구현 상태
현재 버전은 **실행 가능한 통합 서비스(MVP+)** 입니다.

### 연결된 기능
- 스크립트 입력 + 프로젝트 설정(템플릿 A~F, 배경, 의상, 헤어, 로고 위치/크기, 자막 폰트)
- 씬 자동 분할(5~10초 기준 글자수 제한)
- 씬별 대본 수정 + 발음 사전(JSON) + 개별 재생성
- 전체 씬 자동 생성 + 최종 렌더(원클릭)
- 씬별 음성(wav), 자막(srt), 영상(mp4), last frame, 최종 결과물 저장

## 로컬 실행
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

브라우저 접속: `http://127.0.0.1:8000`

## 사용 방법
1. 좌측 패널에서 프로젝트 옵션을 설정하고 중앙에 대본 입력
2. 상단 `새 프로젝트 생성`
3. 씬별 대본 수정/발음 사전 입력 후 `씬 생성/재생성`
4. 상단 `전체 씬 생성 + 최종 렌더` 또는 `최종 렌더만 실행`
5. 우측 패널에서 최종 결과 링크 확인

## 저장 경로
- `data/projects/<project_id>/project.json`
- `data/projects/<project_id>/scene_*/tts.wav`
- `data/projects/<project_id>/scene_*/subtitle.srt`
- `data/projects/<project_id>/scene_*/scene.mp4`
- `data/projects/<project_id>/final.mp4`

## 참고
- `moviepy`/`ffmpeg`가 정상 동작하면 실제 mp4를 생성합니다.
- 렌더링 환경 제약 시 placeholder 파일이 생성될 수 있습니다.
