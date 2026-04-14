# KT Irene Studio

KT 사내에서 사용하는 AI 아나운서(아이린) 영상 제작용 웹 서비스입니다.

## 바로 답변
- **다 됐나?**
  - 핵심 흐름은 완료되었습니다(프로젝트 생성 → 씬 분할 → 씬별 생성/수정 → 최종 렌더).
- **영상 바로 만들 수 있나?**
  - 네. 로컬 실행 후 UI에서 바로 만들 수 있습니다.
  - 단, 현재는 MVP 구조라 실제 KT 믿음 TTS/실제 얼굴 고정 생성 모델은 placeholder 구현입니다.

## 구현된 기능
- 스크립트 입력 + 프로젝트 설정(템플릿 A~F, 배경, 의상, 헤어, 로고 위치/크기, 자막 폰트)
- 씬 자동 분할(5~10초 기준 글자수 제한)
- 씬별 대본 수정 + 발음 사전(JSON) + 개별 재생성
- 전체 씬 자동 생성 + 최종 렌더(원클릭)
- 씬별 음성(wav), 자막(srt), 영상(mp4), last frame, 최종 결과물 저장

## 1분 실행 가이드
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

브라우저: `http://127.0.0.1:8000`

## UI 사용 순서
1. 좌측 설정(템플릿/배경/로고/폰트) + 중앙 대본 입력
2. 상단 `새 프로젝트 생성`
3. 씬별로 `씬 생성/재생성` 또는 상단 `전체 씬 생성 + 최종 렌더`
4. 우측 패널에서 최종 결과 링크 열기

## 파일 저장 위치
- `data/projects/<project_id>/project.json`
- `data/projects/<project_id>/scene_*/tts.wav`
- `data/projects/<project_id>/scene_*/subtitle.srt`
- `data/projects/<project_id>/scene_*/scene.mp4`
- `data/projects/<project_id>/final.mp4`

## 참고
- `moviepy`/`ffmpeg` 환경이 정상일 때 실제 mp4를 생성합니다.
- 렌더링 환경 제약 시 placeholder 파일이 생성될 수 있습니다.
