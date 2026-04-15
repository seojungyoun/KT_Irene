"""
AI 립싱크 영상 생성 서비스

목적: 아이린 이미지 + TTS 오디오 → 아이린이 대본을 실제로 말하는 영상

립싱크 엔진 (이미지 + 오디오 → 말하는 영상):
  1. Kling Lip-Sync  — KLING_ACCESS_KEY + KLING_SECRET_KEY
  2. D-ID            — DID_API_KEY

Veo3 / Hailuo / Runway 등 영상 생성 AI는 이 용도에 맞지 않음:
  → 프롬프트 기반 영상 생성이라 실제 대본과 입모양이 일치하지 않음
"""
from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── 환경 변수 ─────────────────────────────────────────────────────────────────
KLING_ACCESS_KEY = os.getenv("KLING_ACCESS_KEY", "")
KLING_SECRET_KEY = os.getenv("KLING_SECRET_KEY", "")
DID_API_KEY      = os.getenv("DID_API_KEY", "")
SADTALKER_PATH   = os.getenv("SADTALKER_PATH", "")    # SadTalker 클론 경로 (무료)

KLING_BASE = "https://api.klingai.com"
DID_BASE   = "https://api.d-id.com"

# Kling Lip-Sync 단일 호출 최대 길이 (초)
KLING_MAX_CHUNK_SEC = 9


# ══════════════════════════════════════════════════════════════════════════════
# 오디오 / 영상 유틸
# ══════════════════════════════════════════════════════════════════════════════
def _audio_duration(audio_path: Path) -> float:
    """ffprobe로 오디오 길이(초) 반환."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", str(audio_path)],
            capture_output=True, text=True,
        )
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def _split_audio(audio_path: Path, chunk_sec: float, tmp_dir: Path) -> list[Path]:
    """오디오를 chunk_sec 단위로 분할 → WAV 파일 목록."""
    total = _audio_duration(audio_path)
    if total <= 0:
        return [audio_path]

    chunks, start, idx = [], 0.0, 0
    while start < total:
        out = tmp_dir / f"chunk_{idx:03d}.wav"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(audio_path),
                "-ss", f"{start:.3f}",
                "-t",  f"{chunk_sec:.3f}",
                "-ar", "24000", "-ac", "1",   # Kling 권장: 24kHz 모노
                str(out),
            ],
            capture_output=True,
        )
        if out.exists() and out.stat().st_size > 0:
            chunks.append(out)
        start += chunk_sec
        idx   += 1
    return chunks or [audio_path]


def _concat_videos(video_paths: list[Path], output_path: Path) -> bool:
    """ffmpeg concat demuxer로 영상 이어붙이기."""
    if len(video_paths) == 1:
        import shutil
        shutil.copy2(video_paths[0], output_path)
        return True
    list_file = output_path.with_suffix(".concat.txt")
    try:
        list_file.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in video_paths),
            encoding="utf-8",
        )
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(list_file),
                "-c", "copy",
                str(output_path),
            ],
            check=True, capture_output=True,
        )
        return output_path.exists()
    except Exception as e:
        log.error(f"[concat] 실패: {e}")
        return False
    finally:
        list_file.unlink(missing_ok=True)


def _extract_last_frame(video_path: Path, out_path: Path) -> bool:
    """마지막 프레임 PNG 추출 (청크 간 얼굴 연속성용)."""
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-sseof", "-0.5", "-i", str(video_path),
             "-vframes", "1", str(out_path)],
            check=True, capture_output=True,
        )
        return out_path.exists()
    except Exception:
        return False


def _download(url: str, dest: Path) -> bool:
    try:
        urllib.request.urlretrieve(url, dest)
        return dest.exists() and dest.stat().st_size > 0
    except Exception as e:
        log.error(f"[download] 실패: {e}")
        return False


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def _data_uri(path: Path) -> str:
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return f"data:{mime};base64,{_b64(path)}"


# ══════════════════════════════════════════════════════════════════════════════
# 엔진 1 — Kling Lip-Sync
# ══════════════════════════════════════════════════════════════════════════════
def _kling_jwt() -> Optional[str]:
    if not KLING_ACCESS_KEY or not KLING_SECRET_KEY:
        return None
    try:
        import jwt
        return jwt.encode(
            {"iss": KLING_ACCESS_KEY,
             "exp": int(time.time()) + 1800,
             "nbf": int(time.time()) - 5},
            KLING_SECRET_KEY, algorithm="HS256",
        )
    except ImportError:
        log.error("[Kling] PyJWT 미설치: pip install PyJWT")
    except Exception as e:
        log.error(f"[Kling] JWT 오류: {e}")
    return None


def _kling_poll(task_id: str, endpoint: str, token: str, timeout: int = 300) -> Optional[str]:
    import httpx
    headers  = {"Authorization": f"Bearer {token}"}
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(5)
        try:
            r    = httpx.get(f"{KLING_BASE}{endpoint}/{task_id}", headers=headers, timeout=30)
            data = r.json().get("data", {})
            st   = data.get("task_status", "")
            log.debug(f"[Kling] {task_id[:8]}… → {st}")
            if st == "succeed":
                vids = data.get("task_result", {}).get("videos", [])
                return vids[0]["url"] if vids else None
            if st in ("failed", "cancelled"):
                log.error(f"[Kling] 실패: {data.get('task_status_msg', '')}")
                return None
        except Exception as e:
            log.warning(f"[Kling] 폴링 오류: {e}")
    log.error("[Kling] 타임아웃")
    return None


def _kling_single(image_path: Path, audio_path: Path, output_path: Path, token: str) -> bool:
    """Kling Lip-Sync 단일 청크 호출."""
    import httpx
    payload = {
        "input": {
            "mode":       "audio2video",
            "audio_type": "file",
            "audio_file": _b64(audio_path),
            "image_url":  _data_uri(image_path),
        }
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        r    = httpx.post(f"{KLING_BASE}/v1/videos/lip-sync", json=payload, headers=headers, timeout=60)
        resp = r.json()
        if resp.get("code") != 0:
            log.error(f"[Kling] API 오류: code={resp.get('code')} msg={resp.get('message')}")
            return False
        task_id = resp["data"]["task_id"]
        url = _kling_poll(task_id, "/v1/videos/lip-sync", token)
        return _download(url, output_path) if url else False
    except Exception as e:
        log.error(f"[Kling] 요청 예외: {e}")
        return False


def _kling_lip_sync(image_path: Path, audio_path: Path, output_path: Path) -> bool:
    """
    Kling Lip-Sync: 어떤 길이의 오디오도 처리.
    - 9초 이하 → 단일 호출
    - 9초 초과 → 9초 단위 청킹 → 각 청크 생성 → concat
    청크 간 마지막 프레임을 다음 청크의 입력 이미지로 사용해 얼굴 연속성 유지.
    """
    token = _kling_jwt()
    if not token:
        return False

    duration = _audio_duration(audio_path)
    log.info(f"[Kling] 오디오 {duration:.1f}s")

    if duration <= KLING_MAX_CHUNK_SEC:
        return _kling_single(image_path, audio_path, output_path, token)

    # 청킹 처리
    log.info(f"[Kling] {KLING_MAX_CHUNK_SEC}s 단위 청킹 시작")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir      = Path(tmp)
        chunks       = _split_audio(audio_path, KLING_MAX_CHUNK_SEC, tmp_dir)
        log.info(f"[Kling] {len(chunks)}개 청크")
        chunk_videos = []
        cur_image    = image_path   # 첫 청크는 원본 이미지

        for i, chunk_audio in enumerate(chunks):
            chunk_video = tmp_dir / f"lip_{i:03d}.mp4"
            log.info(f"[Kling] 청크 {i+1}/{len(chunks)} 립싱크 중…")
            if not _kling_single(cur_image, chunk_audio, chunk_video, token):
                log.error(f"[Kling] 청크 {i+1} 실패")
                return False
            chunk_videos.append(chunk_video)

            # 다음 청크 입력 이미지 = 현재 청크 마지막 프레임
            last = tmp_dir / f"last_{i:03d}.png"
            if _extract_last_frame(chunk_video, last):
                cur_image = last

        log.info("[Kling] 청크 concat 중…")
        return _concat_videos(chunk_videos, output_path)


# ══════════════════════════════════════════════════════════════════════════════
# 엔진 2 — D-ID
# ══════════════════════════════════════════════════════════════════════════════
def _did_lip_sync(image_path: Path, audio_path: Path, output_path: Path) -> bool:
    """
    D-ID: 이미지 + 오디오 → 말하는 영상.
    1. 오디오 업로드 → audio URL 획득
    2. 이미지 + audio URL → talk 생성
    3. 폴링 → 영상 다운로드
    """
    if not DID_API_KEY:
        return False

    import httpx

    # D-ID Basic Auth: base64("key:")
    auth_header = "Basic " + base64.b64encode(f"{DID_API_KEY}:".encode()).decode()
    headers     = {"Authorization": auth_header}

    try:
        # ① 오디오 업로드
        log.info("[D-ID] 오디오 업로드 중…")
        with audio_path.open("rb") as f:
            upload_r = httpx.post(
                f"{DID_BASE}/audios",
                headers=headers,
                files={"audio": (audio_path.name, f, "audio/wav")},
                timeout=60,
            )
        audio_url = upload_r.json().get("url")
        if not audio_url:
            log.error(f"[D-ID] 오디오 업로드 실패: {upload_r.text}")
            return False
        log.info(f"[D-ID] 오디오 업로드 완료: {audio_url}")

        # ② talk 생성 (이미지 + 오디오)
        log.info("[D-ID] 립싱크 영상 생성 요청…")
        talk_r = httpx.post(
            f"{DID_BASE}/talks",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "source_url": _data_uri(image_path),
                "script": {
                    "type":      "audio",
                    "audio_url": audio_url,
                    "subtitles": False,
                },
                "config": {
                    "fluent":    True,
                    "stitch":    True,     # 얼굴 영역만 교체 후 원본 배경 복원
                    "pad_audio": 0.0,
                },
            },
            timeout=60,
        )
        talk_id = talk_r.json().get("id")
        if not talk_id:
            log.error(f"[D-ID] talk 생성 실패: {talk_r.text}")
            return False
        log.info(f"[D-ID] talk_id={talk_id}")

        # ③ 폴링
        deadline = time.time() + 300
        while time.time() < deadline:
            time.sleep(5)
            poll_r  = httpx.get(f"{DID_BASE}/talks/{talk_id}", headers=headers, timeout=30)
            poll_d  = poll_r.json()
            status  = poll_d.get("status", "")
            log.debug(f"[D-ID] status={status}")
            if status == "done":
                video_url = poll_d.get("result_url")
                if video_url:
                    log.info("[D-ID] 영상 다운로드 중…")
                    return _download(video_url, output_path)
                log.error("[D-ID] result_url 없음")
                return False
            if status == "error":
                log.error(f"[D-ID] 오류: {poll_d.get('error')}")
                return False
        log.error("[D-ID] 타임아웃")
    except Exception as e:
        log.error(f"[D-ID] 예외: {e}")
    return False


# ══════════════════════════════════════════════════════════════════════════════
# 상태 조회
# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
# 엔진 3 — SadTalker (무료, 로컬 GPU)
# ══════════════════════════════════════════════════════════════════════════════
def _sadtalker_generate(image_path: Path, audio_path: Path, output_path: Path) -> bool:
    """
    SadTalker: 이미지 + 오디오 → 실제로 움직이며 말하는 영상 (무료, 로컬 실행).

    필요 조건:
      - SADTALKER_PATH 환경변수에 SadTalker 클론 경로 지정
      - Python + PyTorch (GPU 권장, CPU도 동작하나 느림)
      - 사전 학습 모델 다운로드 완료 (scripts/setup_sadtalker.py 실행)
    """
    if not SADTALKER_PATH:
        return False

    sadtalker_dir = Path(SADTALKER_PATH)
    if not (sadtalker_dir / "inference.py").exists():
        log.error(f"[SadTalker] inference.py 없음: {SADTALKER_PATH}")
        log.error("[SadTalker] scripts/setup_sadtalker.py 를 먼저 실행하세요")
        return False

    result_dir = output_path.parent / "sadtalker_out"
    result_dir.mkdir(exist_ok=True)

    # 오디오를 SadTalker 권장 포맷으로 변환 (16kHz mono WAV)
    prepped_audio = output_path.parent / "st_audio.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(audio_path),
         "-ar", "16000", "-ac", "1", str(prepped_audio)],
        capture_output=True,
    )
    audio_in = prepped_audio if prepped_audio.exists() else audio_path

    try:
        log.info("[SadTalker] 영상 생성 시작 (GPU 없으면 수 분 소요)…")
        subprocess.run(
            [
                "python", "inference.py",
                "--driven_audio",  str(audio_in),
                "--source_image",  str(image_path),
                "--result_dir",    str(result_dir),
                "--still",                 # 앵커 스타일: 고개 움직임 최소화
                "--preprocess",    "full", # 전신 포함 처리
                "--enhancer",      "gfpgan",  # 얼굴 화질 향상 (설치 시)
            ],
            check=True,
            cwd=str(sadtalker_dir),
            timeout=900,  # 15분 타임아웃
        )

        # 가장 최근 생성된 mp4 찾기
        import shutil
        videos = sorted(result_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
        if not videos:
            log.error("[SadTalker] 결과 mp4 없음")
            return False
        shutil.copy2(videos[-1], output_path)
        log.info(f"[SadTalker] ✅ 완료: {output_path.name}")
        return True

    except subprocess.TimeoutExpired:
        log.error("[SadTalker] 타임아웃 (15분 초과)")
    except subprocess.CalledProcessError as e:
        # GFPGAN 없을 때 enhancer 없이 재시도
        log.warning("[SadTalker] GFPGAN 오류, enhancer 없이 재시도…")
        try:
            subprocess.run(
                [
                    "python", "inference.py",
                    "--driven_audio",  str(audio_in),
                    "--source_image",  str(image_path),
                    "--result_dir",    str(result_dir),
                    "--still",
                    "--preprocess",    "full",
                ],
                check=True,
                cwd=str(sadtalker_dir),
                timeout=900,
            )
            import shutil
            videos = sorted(result_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
            if videos:
                shutil.copy2(videos[-1], output_path)
                log.info(f"[SadTalker] ✅ 완료 (enhancer 미적용): {output_path.name}")
                return True
        except Exception as e2:
            log.error(f"[SadTalker] 재시도 실패: {e2}")
    except Exception as e:
        log.error(f"[SadTalker] 예외: {e}")
    return False


# ══════════════════════════════════════════════════════════════════════════════
# 상태 조회 / 메인 진입점
# ══════════════════════════════════════════════════════════════════════════════
def ai_video_status() -> dict:
    has_kling      = bool(KLING_ACCESS_KEY and KLING_SECRET_KEY)
    has_did        = bool(DID_API_KEY)
    has_sadtalker  = bool(
        SADTALKER_PATH and
        Path(SADTALKER_PATH, "inference.py").exists()
    )

    if has_kling:
        engine, label, free = "kling",      "Kling Lip-Sync",  False
    elif has_did:
        engine, label, free = "did",        "D-ID",             False
    elif has_sadtalker:
        engine, label, free = "sadtalker",  "SadTalker (로컬)", True
    else:
        engine, label, free = "static",     "정적 프레임 (PIL)", True

    return {
        "engine":     engine,
        "label":      label,
        "lip_sync":   engine != "static",
        "ai_enabled": engine != "static",
        "free":       free,
        "kling":      has_kling,
        "did":        has_did,
        "sadtalker":  has_sadtalker,
    }


def generate_ai_video(
    image_path: Path,
    audio_path: Path,
    duration: int,
    output_path: Path,
) -> bool:
    """설정된 립싱크 엔진으로 영상 생성. 실패 시 False → PIL fallback."""
    if not image_path.exists():
        log.warning("[AI-Video] 레퍼런스 이미지 없음")
        return False

    engine = ai_video_status()["engine"]

    if engine == "kling":
        log.info("[AI-Video] 엔진: Kling Lip-Sync")
        return _kling_lip_sync(image_path, audio_path, output_path)

    if engine == "did":
        log.info("[AI-Video] 엔진: D-ID")
        return _did_lip_sync(image_path, audio_path, output_path)

    if engine == "sadtalker":
        log.info("[AI-Video] 엔진: SadTalker (로컬 무료)")
        return _sadtalker_generate(image_path, audio_path, output_path)

    return False
