# KT 사내용 AI 아나운서 "아이린" 영상 생성 워크플로우 설계안

## 0) 목표
본 문서는 **고정된 아이린 페이스 아이덴티티**를 유지하면서, 뉴스 대본 입력부터 장면별 재생성, 최종 합성/다운로드까지 가능한 사내용 제작 파이프라인의 기준 설계를 제공합니다.

---

## 1) 제품 요구사항 요약 (사용자 플로우)

1. 사용자가 웹 UI에서 뉴스 대본을 입력한다.
2. 의상/헤어/배경/레이아웃 템플릿(A~F)을 선택한다.
3. 시스템이 대본을 씬 단위로 자동 분할하고 글자 수를 제한한다.
4. 씬별로 TTS 및 영상을 생성하고 즉시 미리보기를 제공한다.
5. 마음에 들지 않는 씬만 수정(대본, 발음, 표정/타이밍) 후 재생성한다.
6. 최종 합성 단계에서 자막/서체/로고/전환 효과를 적용한다.
7. MP4 최종본을 검수 후 다운로드한다.

---

## 2) 전체 아키텍처 (권장)

- **Frontend (React/Next.js)**
  - 스크립트 입력기, 템플릿 선택기, 씬 타임라인, 씬 단위 재생성 버튼
- **API Gateway (FastAPI 권장)**
  - 인증/권한, Job 생성, 상태 조회, 다운로드 URL 발급
- **Orchestrator (Celery/RQ/Temporal 중 1개)**
  - 장면 단위 비동기 작업 관리, 재시도, 종속성 처리
- **Media Services**
  - Script Splitter
  - KT 믿음 TTS 변환
  - Talking-head/Video Generator (아이린 얼굴 고정)
  - Continuity Engine (이전 씬 마지막 프레임 연결)
  - MoviePy Composer (합성/자막/로고/전환)
- **Storage**
  - Object Storage(S3 호환): 오디오/프레임/씬 영상/최종본
  - DB(PostgreSQL): 프로젝트, 씬, 버전, 로그, 품질 점수

---

## 3) 핵심 데이터 모델 (최소)

### Project
- project_id
- owner_id
- title
- status (draft / generating / review / rendered)
- selected_template (A~F)
- branding_profile_id

### Scene
- scene_id
- project_id
- order_index
- script_text
- tts_audio_url
- video_url
- last_frame_url
- duration_sec
- version
- qc_status (pass / warning / fail)

### IdentityProfile (아이린 고정)
- profile_id
- master_face_image_url
- face_embedding_hash
- locked_prompt_version
- allowed_style_set (의상/헤어 프리셋)

### RenderJob
- job_id
- project_id
- job_type (scene_generate / scene_regen / final_render)
- status
- error_log
- created_at / updated_at

---

## 4) 씬 분할 및 글자수 제한 로직

영상 길이 제약(보통 5~10초)을 고려하여 다음 정책을 권장합니다.

- 기본 기준: **1씬 6~8초 목표**
- 한국어 뉴스 톤 발화속도: 약 **초당 6~8자**(띄어쓰기 포함 대략치)
- 권장 글자수:
  - 5초 씬: 30~40자
  - 8초 씬: 48~64자
  - 10초 씬: 60~80자

### 분할 규칙
1. 문장부호(.,?!,다.) 우선 분할
2. 숫자/고유명사는 같은 씬에 묶어 발음 안정성 확보
3. 80자 초과 시 강제 분할
4. 앵커 호흡(쉼표) 기준으로 재조정

### UI 가이드
- 입력창 하단에 `현재 씬 글자수 / 권장 글자수` 표시
- 초과 시 경고(노랑), 제한 초과 시 생성 버튼 비활성화(빨강)

---

## 5) 얼굴 일관성 전략 (가장 중요)

아이린은 고정 인물로 관리하며, 모델 자유생성 대신 **Identity Lock** 파이프라인을 적용합니다.

1. **마스터 이미지 고정**
   - 기준 해상도 정면/45도 레퍼런스 세트 보관
2. **Face Embedding 검사**
   - 씬 산출물의 키프레임 임베딩을 기준값과 비교
   - 임계치 이하(유사도 낮음)면 자동 재생성
3. **Prompt Lock + Style Preset**
   - 얼굴 구조 관련 프롬프트는 수정 금지
   - 의상/헤어/배경만 화이트리스트 기반 선택
4. **Seed 고정 전략**
   - 프로젝트 단위 기본 seed 유지
   - 씬별 seed 파생(`base_seed + scene_index`)으로 재현성 확보
5. **QC 자동 점검 항목**
   - 눈/코/입 상대 좌표 편차
   - 턱선/어깨선 대칭성
   - 헤어 파트(6:4) 유지 여부

---

## 6) 연속성(씬 연결) 처리

### 목표
씬을 분리 생성하더라도 움직임이 끊기지 않도록 연결합니다.

### 방식
1. 씬 N 렌더링 완료 후 마지막 프레임 추출(`frame_N_end.png`)
2. 씬 N+1 생성 시 `init_frame=frame_N_end.png`로 조건 주입
3. 시작 0.3~0.5초는 모션 완화(velocity smoothing)
4. 장면 경계에 6~12프레임 크로스디졸브 적용

---

## 7) 장면별 검토/수정 UX

- 씬 카드에 다음 기능 제공:
  - 재생
  - 대본 수정
  - 발음 사전(사용자 발음 표기) 편집
  - 재생성
  - 버전 비교(A/B)
- 전체 재렌더 없이 **해당 씬만 교체** 가능
- 타임라인 자동 리플로우(길이 변경 시 뒤 씬 타임스탬프 재계산)

---

## 8) MoviePy 기반 최종 렌더링 자동화

### 8.1 템플릿 합성
- 템플릿 A~F를 JSON 레이아웃으로 분리 정의
- 예: A(6:4 split), B(PIP) 등

### 8.2 자막
- 씬별 대본에서 문장 단위 SRT 자동 생성
- 기본 폰트: KT 전용 서체
- 옵션: 폰트/크기/자간/행간/배경박스

### 8.3 로고
- 프리셋 위치: top-left, top-right, bottom-left, bottom-right
- 크기: short side 기준 %
- 안전 여백(safe margin) 강제

### 8.4 전환 효과
- 기본: `crossfadein/crossfadeout`
- easy-and-easy 프리셋(디졸브 + 오디오 equal-power fade)

---

## 9) 백엔드 API 예시

- `POST /projects` : 프로젝트 생성
- `POST /projects/{id}/scenes:auto-split` : 씬 자동 분할
- `POST /scenes/{id}/generate` : 씬 생성
- `POST /scenes/{id}/regenerate` : 씬 재생성
- `POST /projects/{id}/render-final` : 최종 렌더
- `GET /projects/{id}` : 상태/결과 조회
- `GET /assets/{id}/download` : 파일 다운로드

---

## 10) 운영/품질 지표 (KPI)

- 씬 재생성률(낮을수록 좋음)
- 얼굴 일관성 실패율
- 평균 최종 렌더 시간
- 사용자 수동 수정 횟수(발음/자막)
- 프로젝트 완료율

---

## 11) 보안/거버넌스 (사내 필수)

- SSO/사내 계정 연동
- 프로젝트 접근권한(팀/부서 ACL)
- 로고/브랜딩 에셋 버전 관리
- 생성 이력(누가/언제/무엇을 수정했는지) 감사 로그
- 데이터 보관 주기 및 자동 삭제 정책

---

## 12) 단계별 구축 로드맵

### Phase 1 (MVP, 4~6주)
- 대본 입력 → 씬 자동 분할 → TTS → 단일 템플릿 합성 → MP4 다운로드
- 씬별 재생성 기능 포함

### Phase 2 (고도화, 4주)
- 템플릿 A~F, 로고 옵션, 자막 고급 옵션
- 얼굴 일관성 QC 자동 점검 + 실패 자동 재시도

### Phase 3 (운영 안정화, 3~4주)
- 대시보드/KPI, 사용량 모니터링, 큐 튜닝
- 품질 기준선 및 프리셋 추천 자동화

---

## 13) 아이린 고정 프롬프트 운용 가이드

사용자가 제공한 아이린 프롬프트는 **버전 고정(immutable)** 으로 저장하고, 운영 중에는 아래만 허용합니다.

- 허용 수정: 배경, 레이아웃, 자막, 로고, 장면 길이
- 제한 수정: 얼굴 구조(눈/코/입/턱), 헤어 파트 비율, 체형 비율
- 정책: 얼굴 정의 블록 변경 시 관리자 승인 필요

이렇게 하면 "창의성"은 유지하면서도 "아이린 동일인성"을 안정적으로 유지할 수 있습니다.

---

## 14) 즉시 실행 체크리스트

- [ ] 아이린 마스터 이미지/임베딩 등록
- [ ] 씬 글자수 정책(5~10초) UI 반영
- [ ] KT 믿음 TTS API 연동
- [ ] 씬별 재생성 워크플로우 구현
- [ ] MoviePy 템플릿 A/B 우선 구현
- [ ] 자막 + 로고 + 디졸브 자동화
- [ ] 최종본 검수/다운로드 페이지 배포

