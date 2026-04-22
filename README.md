# KT Irene Studio

KT 사내 AI 아나운서 **아이린(Irene)** 의 영상을 뉴스 대본 한 장으로 자동 제작하는 웹 서비스입니다.

---

## 목차

1. [서비스 개요](#1-서비스-개요)
2. [전체 시스템 구조](#2-전체-시스템-구조)
3. [디렉터리 구조](#3-디렉터리-구조)
4. [실행 환경 요구사항](#4-실행-환경-요구사항)
5. [설치 및 실행](#5-설치-및-실행)
6. [KT 믿음 TTS 연동](#6-kt-믿음-tts-연동)
7. [아이린 이미지 등록](#7-아이린-이미지-등록)
8. [사용 방법 (워크플로우)](#8-사용-방법-워크플로우)
9. [템플릿 A~F 가이드](#9-템플릿-af-가이드)
10. [API 엔드포인트 목록](#10-api-엔드포인트-목록)
11. [환경변수 목록](#11-환경변수-목록)
12. [자주 묻는 질문 / 문제 해결](#12-자주-묻는-질문--문제-해결)

---

## 1. 서비스 개요

```
뉴스 대본 입력
     ↓
씬 자동 분할 (5~10초 단위)
     ↓
씬별 TTS 음성 생성 + 영상 컴포지팅
     ↓
씬 단위 미리보기 / 수정 / 재생성
     ↓
최종 MP4 렌더 (템플릿 A~F 적용 + 전환 효과)
     ↓
다운로드
```

**주요 특징**

| 기능 | 설명 |
|------|------|
| 아이린 얼굴 일관성 | 고정된 마스터 이미지를 모든 씬에 동일하게 사용 |
| TTS 우선순위 | KT 믿음 TTS → edge-tts → 사인파 fallback 자동 전환 |
| 비동기 생성 | 전체 생성 중에도 UI가 멈추지 않고 진행 바로 상태 표시 |
| 씬 단위 재생성 | 마음에 안 드는 씬만 골라 수정 후 재생성 가능 |
| 6가지 레이아웃 | 방송 스타일 템플릿 A~F 즉시 선택 적용 |

---

## 2. 전체 시스템 구조

```
┌─────────────────────────────────────────────────────────┐
│                     브라우저 (UI)                        │
│  index.html + app.js + style.css                        │
│  - 프로젝트 설정 / 씬 편집 / 미리보기 플레이어             │
│  - 생성 진행 바 (2초 폴링)                                │
└───────────────────────┬─────────────────────────────────┘
                        │ HTTP REST
┌───────────────────────▼─────────────────────────────────┐
│                  FastAPI 서버 (app/main.py)              │
│                                                         │
│  POST /api/projects          — 프로젝트 생성             │
│  POST /api/projects/{id}/    — 씬 생성 (동기)            │
│    scenes/{id}/generate                                 │
│  POST /api/projects/{id}/    — 전체 생성 (비동기 스레드)  │
│    generate-all                                         │
│  GET  /api/projects/{id}/    — 진행 상황 폴링            │
│    progress                                             │
│  POST /api/projects/{id}/    — 최종 렌더                 │
│    render-final                                         │
│  POST /api/irene/            — 아이린 이미지 업로드       │
│    upload-reference                                     │
└──────┬────────────────┬────────────────┬────────────────┘
       │                │                │
┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
│  tts.py     │  │  video.py   │  │ renderer.py │
│             │  │             │  │             │
│ ① KT 믿음   │  │ PIL 합성    │  │ 템플릿 A~F  │
│ ② edge-tts │  │ - 배경 그라  │  │ ffmpeg      │
│ ③ sine-wave│  │   디언트     │  │ filtergraph │
│             │  │ - 아이린 이  │  │ + 크로스    │
│ → .wav      │  │   미지 오버  │  │   디졸브    │
│             │  │   레이      │  │             │
│             │  │ - 자막 바   │  │ → final.mp4 │
│             │  │ - KT 로고   │  │             │
│             │  │ → scene.mp4 │  │             │
└─────────────┘  └─────────────┘  └─────────────┘
                        │
                 ┌──────▼──────┐
                 │   ffmpeg    │
                 │  (외부 도구) │
                 └─────────────┘
```

### 데이터 흐름

```
대본 입력
  → scene_splitter.py : 문장 단위 씬 분할 (글자 수 기반)
  → tts.py            : 씬별 음성(.wav) 생성
  → tts.py            : 씬별 자막(.srt) 생성
  → video.py          : PIL 컴포지트 프레임 생성
                         (배경 + 아이린 + 자막 + 로고)
  → ffmpeg            : 정지 이미지 × 오디오 → scene.mp4
  → renderer.py       : 템플릿 레이아웃 적용
  → renderer.py       : 씬 간 크로스디졸브(0.35s) 연결
  → final.mp4         : 다운로드
```

---

## 3. 디렉터리 구조

```
KT_Irene/
│
├── app/                          ← FastAPI 애플리케이션
│   ├── main.py                   ← API 엔드포인트 + 라우터
│   ├── models.py                 ← Project / Scene 데이터 모델
│   ├── schemas.py                ← Pydantic 요청/응답 스키마
│   │
│   ├── services/
│   │   ├── tts.py                ← TTS 엔진 (KT믿음/edge-tts/sine)
│   │   ├── video.py              ← 씬 영상 생성 (PIL + ffmpeg)
│   │   ├── renderer.py           ← 최종 렌더 + 템플릿 A~F
│   │   └── scene_splitter.py     ← 씬 자동 분할 로직
│   │
│   └── static/
│       ├── index.html            ← 메인 UI
│       ├── app.js                ← 프론트엔드 로직
│       └── style.css             ← KT 브랜드 스타일
│
├── data/
│   ├── assets/
│   │   ├── irene_reference.png   ← 아이린 마스터 이미지 (교체 가능)
│   │   └── kt_logo.png           ← KT 로고 (자동 생성)
│   │
│   └── projects/
│       └── {project_id}/
│           ├── project.json      ← 프로젝트 메타데이터
│           ├── scene_000_v1/
│           │   ├── tts.wav       ← 씬 음성
│           │   ├── subtitle.srt  ← 씬 자막
│           │   ├── frame_composite.png ← 합성 프레임
│           │   ├── scene.mp4     ← 씬 영상
│           │   └── last_frame.png← 다음 씬 연속성용 프레임
│           └── final.mp4         ← 최종 완성 영상
│
├── requirements.txt
├── AIRENE_WORKFLOW_PLAN.md
└── README.md
```

---

## 4. 실행 환경 요구사항

| 항목 | 최소 버전 | 설명 |
|------|-----------|------|
| Python | 3.10 이상 | 타입 힌트 문법 사용 |
| ffmpeg | 최신 권장 | 영상 인코딩 핵심 도구 |
| 메모리 | 4GB 이상 | 영상 처리 시 필요 |
| 네트워크 | 인터넷 연결 | edge-tts 사용 시 필요 |

### ffmpeg 설치

**Windows**
```bash
# winget 사용 (권장)
winget install ffmpeg

# 또는 https://ffmpeg.org/download.html 에서 직접 다운로드 후
# 시스템 PATH에 추가
```

**macOS**
```bash
brew install ffmpeg
```

**Ubuntu/Debian**
```bash
sudo apt update && sudo apt install ffmpeg
```

설치 확인:
```bash
ffmpeg -version
```

---

## 5. 설치 및 실행

### ① 저장소 클론

```bash
git clone https://github.com/seojungyoun/KT_Irene.git
cd KT_Irene
```

### ② Python 가상환경 생성 (권장)

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python -m venv .venv
source .venv/bin/activate
```

### ③ 패키지 설치

```bash
pip install -r requirements.txt
```

> `requirements.txt`에 포함된 패키지:
> - `fastapi` — 웹 프레임워크
> - `uvicorn` — ASGI 서버
> - `moviepy` — 영상 편집 (폴백용)
> - `pillow` — 이미지 합성
> - `edge-tts` — 한국어 TTS
> - `httpx` — KT 믿음 TTS HTTP 클라이언트

### ④ 서버 실행

```bash
uvicorn app.main:app --reload --port 8000
```

### ⑤ 브라우저 접속

```
http://localhost:8000
```

서버가 정상 동작하면 우상단에 **서버 정상** 초록색 배지가 표시됩니다.

---

## 6. KT 믿음 TTS 연동

KT 믿음 TTS API 키가 있으면 환경변수 2개를 설정하는 것만으로 자동 연동됩니다.

### 환경변수 설정 방법

**방법 A — 터미널에서 직접 설정 후 실행**

```bash
# Windows (PowerShell)
$env:KT_TTS_API_KEY="발급받은_API_키"
$env:KT_TTS_API_URL="https://aiapi.kt.co.kr/tts/v1/synthesis"
uvicorn app.main:app --reload

# macOS / Linux
export KT_TTS_API_KEY="발급받은_API_키"
export KT_TTS_API_URL="https://aiapi.kt.co.kr/tts/v1/synthesis"
uvicorn app.main:app --reload
```

**방법 B — `.env` 파일 생성**

프로젝트 루트에 `.env` 파일 생성:
```
KT_TTS_API_KEY=발급받은_API_키
KT_TTS_API_URL=https://aiapi.kt.co.kr/tts/v1/synthesis
```

그 후 실행:
```bash
uvicorn app.main:app --reload --env-file .env
```

### TTS 우선순위 동작 방식

```
KT_TTS_API_KEY 설정됨?
  ├─ YES → KT 믿음 TTS API 호출
  │          └─ 실패 시 edge-tts로 폴백
  └─ NO  → edge-tts (ko-KR-SunHiNeural) 사용
              └─ 미설치 시 sine-wave 더미 음성
```

> **edge-tts 음성 변경:** 환경변수 `IRENE_TTS_VOICE`로 다른 음성 지정 가능  
> 예) `IRENE_TTS_VOICE=ko-KR-InJoonNeural` (남성 음성)

---

## 7. 아이린 이미지 등록

아이린 레퍼런스 이미지는 모든 씬의 배경에 합성되는 **핵심 에셋**입니다.

### 방법 A — UI에서 업로드 (권장)

서비스 실행 후 우상단 **📷 아이린 이미지** 버튼 클릭 → PNG/JPG 선택

### 방법 B — 파일 직접 교체

```bash
# 아이린 실제 이미지를 아래 경로에 복사
cp /경로/아이린_이미지.png data/assets/irene_reference.png
```

> **주의:** 이미지가 없으면 서비스 최초 실행 시 PIL로 생성한 플레이스홀더가 자동 사용됩니다.  
> 실제 서비스에서는 반드시 실제 아이린 마스터 이미지로 교체하세요.

### 권장 이미지 스펙

| 항목 | 권장값 |
|------|--------|
| 포맷 | PNG (투명 배경 지원) |
| 해상도 | 640×720 이상 |
| 배경 | 투명(RGBA) 또는 단색 |
| 피사체 | 전신 또는 상반신 정면 |

---

## 8. 사용 방법 (워크플로우)

### Step 1 — 프로젝트 설정

| 항목 | 설명 |
|------|------|
| 제목 | 영상 파일명에 사용됨 |
| 템플릿 | A~F 중 선택 (하단 가이드 참고) |
| 씬 길이 | 씬 1개의 목표 시간 (5~10초) |
| 배경 | KT Studio(다크) / White Room / Red Gradient |
| 의상 | White Mockneck / White Halter |
| 헤어 | Long S-wave 6:4 / Straight 6:4 |
| 로고 위치 | 영상 내 KT 로고 위치 |

### Step 2 — 대본 입력 및 씬 분할

전체 뉴스 대본을 **전체 대본** 란에 붙여넣고 **＋ 새 프로젝트** 클릭.

- 씬 길이(초) × 7자 = 씬당 권장 글자 수
- 문장 부호(`.`, `!`, `?`, `다`) 기준으로 자동 분할
- 글자 수 초과 씬은 경고 표시

### Step 3 — 씬 개별 생성

각 씬 카드에서:
1. 대본 수정 → **대본 저장**
2. 발음 사전 입력 (선택): `{"KT":"케이티", "5G":"파이브지"}`
3. **씬 생성** 클릭 → 완료 후 **▶ 미리보기** 버튼 활성화

### Step 4 — 전체 생성

**▶ 전체 생성** 클릭 → 상단 진행 바에서 실시간 진행률 확인  
모든 씬 생성 완료 후 최종 렌더까지 자동 진행

### Step 5 — 최종 렌더 및 다운로드

- 개별 씬 수정 후 전체 다시 합치려면 **⬇ 최종 렌더** 클릭
- 완료 시 **⬇ 다운로드** 버튼 활성화 → `{제목}_final.mp4` 저장

---

## 9. 템플릿 A~F 가이드

| 코드 | 이름 | 레이아웃 설명 |
|------|------|---------------|
| **A** | 6:4 Split | 앵커 60% 좌측 + 뉴스 타이틀 패널 40% 우측 |
| **B** | PIP | 풀스크린 앵커 + 우하단 소형 창(Picture-in-Picture) |
| **C** | Anchor Full | 앵커 풀스크린 (가장 단순한 기본형) |
| **D** | Side Panel | 뉴스 패널 50% 좌측 + 앵커 50% 우측 |
| **E** | Ticker | 앵커 상단 + 하단 스크롤 티커 바 |
| **F** | Dual Box | 앵커 좌측 박스 + 뉴스 타이틀 우측 박스 |

> 템플릿은 최종 렌더 단계에서 적용됩니다.  
> 씬 개별 미리보기는 항상 기본(앵커 풀) 형태로 표시됩니다.

---

## 10. API 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/health` | 서버 상태 확인 |
| `GET` | `/api/projects` | 전체 프로젝트 목록 |
| `POST` | `/api/projects` | 프로젝트 생성 |
| `GET` | `/api/projects/{id}` | 프로젝트 상세 조회 |
| `PATCH` | `/api/projects/{id}/settings` | 설정 업데이트 |
| `POST` | `/api/projects/{id}/split-scenes` | 씬 재분할 |
| `PATCH` | `/api/projects/{id}/scenes/{id}` | 씬 대본 수정 |
| `POST` | `/api/projects/{id}/scenes/{id}/generate` | 씬 생성 (동기) |
| `POST` | `/api/projects/{id}/generate-all` | 전체 생성 (비동기) |
| `GET` | `/api/projects/{id}/progress` | 생성 진행률 조회 |
| `POST` | `/api/projects/{id}/render-final` | 최종 렌더 |
| `GET` | `/api/projects/{id}/final-video` | 최종 영상 다운로드 |
| `GET` | `/api/projects/{id}/scenes/{id}/video` | 씬 영상 |
| `GET` | `/api/projects/{id}/scenes/{id}/audio` | 씬 음성 |
| `GET` | `/api/projects/{id}/scenes/{id}/subtitle` | 씬 자막 |
| `GET` | `/api/projects/{id}/scenes/{id}/last-frame` | 씬 마지막 프레임 |
| `POST` | `/api/irene/upload-reference` | 아이린 이미지 업로드 |
| `GET` | `/api/irene/reference` | 아이린 이미지 조회 |

---

## 11. 환경변수 목록

| 변수명 | 기본값 | 설명 |
|--------|--------|------|
| `KT_TTS_API_KEY` | (없음) | KT 믿음 TTS API 키 |
| `KT_TTS_API_URL` | (없음) | KT 믿음 TTS 엔드포인트 URL |
| `IRENE_TTS_VOICE` | `ko-KR-SunHiNeural` | edge-tts 음성 ID |

---

## 12. 자주 묻는 질문 / 문제 해결

### Q. 씬 생성 버튼을 눌렀는데 오래 걸립니다

edge-tts는 인터넷을 통해 음성을 생성하므로 네트워크 상태에 따라 10~20초 소요될 수 있습니다.  
KT 사내망에서는 KT 믿음 TTS를 사용하면 더 빠릅니다.

### Q. `ffmpeg: command not found` 오류가 납니다

ffmpeg가 설치되어 있지 않거나 PATH에 없는 경우입니다.  
[4. 실행 환경 요구사항](#4-실행-환경-요구사항)의 ffmpeg 설치 방법을 참고하세요.

### Q. 영상이 생성됐는데 소리가 없습니다

edge-tts 미설치 또는 네트워크 오류로 사인파 더미 음성이 생성된 경우입니다.
```bash
pip install edge-tts
```
설치 후 서버를 재시작하고 해당 씬을 재생성하세요.

### Q. 아이린 이미지가 영상에 안 나옵니다

`data/assets/irene_reference.png` 파일이 없거나 자동 생성 플레이스홀더 상태입니다.  
**📷 아이린 이미지** 버튼으로 실제 이미지를 업로드하세요.

### Q. 서버 재시작 후 프로젝트가 사라집니다

현재 프로젝트는 서버 메모리에 저장됩니다. 파일(`data/projects/*/project.json`)은 남아 있으나 서버 재시작 시 메모리에서 사라집니다.  
서버를 자주 재시작하는 환경이라면 시작 시 `data/projects/`를 자동으로 로드하는 기능 추가가 필요합니다.

### Q. 화면이 이전 버전 그대로입니다

`Ctrl + Shift + R` (Windows) 또는 `Cmd + Shift + R` (Mac) 강력 새로고침.  
`/health` 응답의 `build` 값이 `2026.04.14-3`인지 확인하세요.

### Q. 최종 영상에서 씬 간 전환이 어색합니다

moviepy가 설치되어 있어야 크로스디졸브 효과가 적용됩니다.
```bash
pip install moviepy
```
미설치 시 ffmpeg concat(전환 없음)으로 폴백됩니다.

---

## 기술 스택 요약

| 레이어 | 기술 |
|--------|------|
| 웹 프레임워크 | FastAPI + Uvicorn |
| 이미지 합성 | Pillow (PIL) |
| 영상 처리 | ffmpeg (주) + MoviePy (보조) |
| TTS | KT 믿음 TTS / edge-tts / sine-wave |
| 프론트엔드 | Vanilla HTML/CSS/JS |
| 데이터 저장 | JSON 파일 (메모리 캐시 + 디스크) |
