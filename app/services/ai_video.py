"""
AI 영상 생성 서비스

아이린 레퍼런스 이미지 + TTS 오디오 → 실제로 말하는 AI 영상

우선순위:
  1. Kling Lip-Sync  (KLING_ACCESS_KEY + KLING_SECRET_KEY)
  2. Kling Image-to-Video  (동일 키, 립싱크 실패 시)
  3. Veo 3 via Google AI  (GOOGLE_API_KEY)
  4. Hailuo / MiniMax  (MINIMAX_API_KEY + MINIMAX_GROUP_ID)
  5. None 반환 → 호출자가 PIL 정적 프레임 fallback 사용
"""
from __future__ import annotations

import base64
import logging
import os
import time
import urllib.request
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── 환경 변수 ─────────────────────────────────────────────────────────────────
KLING_ACCESS_KEY  = os.getenv("KLING_ACCESS_KEY", "")
KLING_SECRET_KEY  = os.getenv("KLING_SECRET_KEY", "")
GOOGLE_API_KEY    = os.getenv("GOOGLE_API_KEY", "")
MINIMAX_API_KEY   = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_GROUP_ID  = os.getenv("MINIMAX_GROUP_ID", "")

KLING_BASE        = "https://api.klingai.com"
MINIMAX_BASE      = "https://api.minimax.io"

ANCHOR_PROMPT = (
    "Korean female news anchor delivering news, "
    "facing camera directly, subtle natural head movements, "
    "professional broadcast studio lighting, cinematic quality"
)


# ══════════════════════════════════════════════════════════════════════════════
# 공통 유틸
# ══════════════════════════════════════════════════════════════════════════════
def _b64file(path: Path) -> str:
    """파일을 base64 문자열로 인코딩."""
    return base64.b64encode(path.read_bytes()).decode()


def _data_uri(path: Path) -> str:
    """파일을 data URI로 변환 (image/png 또는 image/jpeg 자동 감지)."""
    ext = path.suffix.lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    return f"data:{mime};base64,{_b64file(path)}"


def _download(url: str, dest: Path) -> bool:
    """URL에서 파일 다운로드."""
    try:
        urllib.request.urlretrieve(url, dest)
        return dest.exists() and dest.stat().st_size > 0
    except Exception as e:
        log.error(f"[AI-Video] 다운로드 실패 {url}: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Kling AI
# ══════════════════════════════════════════════════════════════════════════════
def _kling_jwt() -> Optional[str]:
    """Kling API 인증 JWT 생성 (HS256)."""
    if not KLING_ACCESS_KEY or not KLING_SECRET_KEY:
        return None
    try:
        import jwt  # PyJWT
        payload = {
            "iss": KLING_ACCESS_KEY,
            "exp": int(time.time()) + 1800,
            "nbf": int(time.time()) - 5,
        }
        return jwt.encode(payload, KLING_SECRET_KEY, algorithm="HS256")
    except ImportError:
        log.warning("[Kling] PyJWT 미설치. pip install PyJWT")
    except Exception as e:
        log.error(f"[Kling] JWT 생성 실패: {e}")
    return None


def _kling_poll(task_id: str, endpoint: str, token: str, timeout: int = 300) -> Optional[str]:
    """Kling 작업 완료까지 폴링 → 영상 URL 반환."""
    import httpx
    headers = {"Authorization": f"Bearer {token}"}
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(6)
        try:
            r = httpx.get(f"{KLING_BASE}{endpoint}/{task_id}", headers=headers, timeout=30)
            data = r.json().get("data", {})
            status = data.get("task_status", "")
            log.info(f"[Kling] task={task_id} status={status}")
            if status == "succeed":
                videos = data.get("task_result", {}).get("videos", [])
                return videos[0]["url"] if videos else None
            if status in ("failed", "cancelled"):
                log.error(f"[Kling] 작업 실패: {data.get('task_status_msg', '')}")
                return None
        except Exception as e:
            log.warning(f"[Kling] 폴링 오류: {e}")
    log.error("[Kling] 타임아웃")
    return None


def kling_lip_sync(image_path: Path, audio_path: Path, output_path: Path) -> bool:
    """
    Kling Lip-Sync: 레퍼런스 이미지 + TTS 오디오 → 말하는 영상.
    가장 자연스러운 앵커 영상 생성.
    """
    token = _kling_jwt()
    if not token:
        return False
    try:
        import httpx
        payload = {
            "input": {
                "mode": "audio2video",
                "audio_type": "file",
                "audio_file": _b64file(audio_path),
                "image_url": _data_uri(image_path),
            }
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        log.info("[Kling] Lip-Sync 요청 중...")
        r = httpx.post(
            f"{KLING_BASE}/v1/videos/lip-sync",
            json=payload, headers=headers, timeout=60
        )
        resp = r.json()
        if resp.get("code") != 0:
            log.error(f"[Kling] Lip-Sync 오류: {resp}")
            return False
        task_id = resp["data"]["task_id"]
        url = _kling_poll(task_id, "/v1/videos/lip-sync", token)
        return _download(url, output_path) if url else False
    except Exception as e:
        log.error(f"[Kling] Lip-Sync 예외: {e}")
        return False


def kling_image2video(
    image_path: Path,
    duration: int,
    output_path: Path,
    prompt: str = ANCHOR_PROMPT,
) -> bool:
    """
    Kling Image-to-Video: 레퍼런스 이미지 → 자연스럽게 움직이는 앵커 영상.
    Lip-Sync API 실패 시 fallback.
    """
    token = _kling_jwt()
    if not token:
        return False
    try:
        import httpx
        payload = {
            "model_name": "kling-v1-6",
            "image": _data_uri(image_path),
            "prompt": prompt,
            "duration": str(min(max(duration, 5), 10)),
            "cfg_scale": 0.5,
            "mode": "std",
            "aspect_ratio": "16:9",
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        log.info("[Kling] Image2Video 요청 중...")
        r = httpx.post(
            f"{KLING_BASE}/v1/videos/image2video",
            json=payload, headers=headers, timeout=60
        )
        resp = r.json()
        if resp.get("code") != 0:
            log.error(f"[Kling] Image2Video 오류: {resp}")
            return False
        task_id = resp["data"]["task_id"]
        url = _kling_poll(task_id, "/v1/videos/image2video", token, timeout=400)
        if not url:
            return False
        # 오디오는 별도 mux (Image2Video는 오디오 없음)
        raw = output_path.with_suffix(".raw.mp4")
        if not _download(url, raw):
            return False
        return True  # 오디오 mux는 video.py에서 처리
    except Exception as e:
        log.error(f"[Kling] Image2Video 예외: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Veo 3 (Google AI Studio / Vertex AI)
# ══════════════════════════════════════════════════════════════════════════════
def veo3_generate(image_path: Path, duration: int, output_path: Path) -> bool:
    """Veo 3: 이미지 + 프롬프트 → 영상 생성."""
    if not GOOGLE_API_KEY:
        return False
    try:
        from google import genai  # type: ignore
        from google.genai import types  # type: ignore

        client = genai.Client(api_key=GOOGLE_API_KEY)
        img_bytes = image_path.read_bytes()

        log.info("[Veo3] 영상 생성 요청 중...")
        operation = client.models.generate_video(
            model="veo-2.0-generate-001",
            prompt=ANCHOR_PROMPT,
            image=types.Image(
                image_bytes=img_bytes,
                mime_type="image/png" if image_path.suffix == ".png" else "image/jpeg",
            ),
            config=types.GenerateVideoConfig(
                duration_seconds=min(duration, 8),
                fps=24,
                aspect_ratio="16:9",
                person_generation="allow_adult",
            ),
        )
        # 완료까지 폴링
        deadline = time.time() + 600
        while not operation.done and time.time() < deadline:
            time.sleep(10)
            operation = client.operations.get(operation)
            log.info(f"[Veo3] 진행 중... done={operation.done}")

        if operation.done and operation.response:
            vids = operation.response.generated_videos
            if vids and vids[0].video and vids[0].video.video_bytes:
                output_path.write_bytes(vids[0].video.video_bytes)
                log.info("[Veo3] 영상 생성 완료")
                return True
        log.error("[Veo3] 생성 실패 또는 타임아웃")
    except ImportError:
        log.warning("[Veo3] google-genai 미설치. pip install google-genai")
    except Exception as e:
        log.error(f"[Veo3] 예외: {e}")
    return False


# ══════════════════════════════════════════════════════════════════════════════
# Hailuo / MiniMax
# ══════════════════════════════════════════════════════════════════════════════
def hailuo_generate(image_path: Path, duration: int, output_path: Path) -> bool:
    """Hailuo(MiniMax): 이미지 + 프롬프트 → 영상 생성."""
    if not MINIMAX_API_KEY or not MINIMAX_GROUP_ID:
        return False
    try:
        import httpx

        headers = {
            "Authorization": f"Bearer {MINIMAX_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "video-01",
            "prompt": ANCHOR_PROMPT,
            "first_frame_image": _data_uri(image_path),
        }
        log.info("[Hailuo] 영상 생성 요청 중...")
        r = httpx.post(
            f"{MINIMAX_BASE}/v1/video_generation?GroupId={MINIMAX_GROUP_ID}",
            json=payload, headers=headers, timeout=60
        )
        resp = r.json()
        task_id = resp.get("task_id")
        if not task_id:
            log.error(f"[Hailuo] task_id 없음: {resp}")
            return False

        # 폴링
        deadline = time.time() + 400
        while time.time() < deadline:
            time.sleep(8)
            pr = httpx.get(
                f"{MINIMAX_BASE}/v1/query/video_generation?task_id={task_id}&GroupId={MINIMAX_GROUP_ID}",
                headers=headers, timeout=30
            )
            pd = pr.json()
            status = pd.get("status", "")
            log.info(f"[Hailuo] status={status}")
            if status == "Success":
                url = pd.get("file_id") or pd.get("video_url")
                # file_id가 있으면 별도 다운로드 API 필요할 수 있음
                if url and url.startswith("http"):
                    return _download(url, output_path)
                log.error(f"[Hailuo] URL 파싱 실패: {pd}")
                return False
            if status in ("Fail", "Unknown"):
                log.error(f"[Hailuo] 생성 실패: {pd}")
                return False
        log.error("[Hailuo] 타임아웃")
    except ImportError:
        log.warning("[Hailuo] httpx 미설치")
    except Exception as e:
        log.error(f"[Hailuo] 예외: {e}")
    return False


# ══════════════════════════════════════════════════════════════════════════════
# 상태 확인
# ══════════════════════════════════════════════════════════════════════════════
def ai_video_status() -> dict:
    """현재 설정된 AI 영상 엔진 상태 반환."""
    has_kling    = bool(KLING_ACCESS_KEY and KLING_SECRET_KEY)
    has_veo3     = bool(GOOGLE_API_KEY)
    has_hailuo   = bool(MINIMAX_API_KEY and MINIMAX_GROUP_ID)

    if has_kling:
        engine, label = "kling", "Kling AI"
    elif has_veo3:
        engine, label = "veo3", "Veo 3"
    elif has_hailuo:
        engine, label = "hailuo", "Hailuo"
    else:
        engine, label = "static", "정적 프레임 (PIL)"

    return {
        "engine": engine,
        "label": label,
        "kling": has_kling,
        "veo3": has_veo3,
        "hailuo": has_hailuo,
        "ai_enabled": engine != "static",
    }


# ══════════════════════════════════════════════════════════════════════════════
# 메인 진입점
# ══════════════════════════════════════════════════════════════════════════════
def generate_ai_video(
    image_path: Path,
    audio_path: Path,
    duration: int,
    output_path: Path,
) -> bool:
    """
    우선순위대로 AI 영상 생성 시도.

    Args:
        image_path:  아이린 레퍼런스 이미지 (PNG/JPG)
        audio_path:  TTS 오디오 (WAV/MP3)
        duration:    목표 씬 길이 (초)
        output_path: 저장할 영상 경로

    Returns:
        True  → AI 영상 생성 성공 (output_path에 저장됨)
        False → 모두 실패 → 호출자가 PIL 정적 프레임 사용
    """
    if not image_path.exists():
        log.warning("[AI-Video] 레퍼런스 이미지 없음 → PIL fallback")
        return False

    # 1. Kling Lip-Sync (최고 품질 — 실제 립싱크)
    if KLING_ACCESS_KEY and KLING_SECRET_KEY:
        log.info("[AI-Video] 1단계: Kling Lip-Sync 시도")
        if kling_lip_sync(image_path, audio_path, output_path):
            log.info("[AI-Video] ✅ Kling Lip-Sync 성공")
            return True

        # 2. Kling Image-to-Video (립싱크 실패 시)
        log.info("[AI-Video] 2단계: Kling Image2Video 시도")
        raw_path = output_path.with_suffix(".raw.mp4")
        if kling_image2video(image_path, duration, raw_path):
            # 생성된 영상에 오디오 mux
            if _mux_audio(raw_path, audio_path, duration, output_path):
                log.info("[AI-Video] ✅ Kling Image2Video + 오디오 mux 성공")
                return True

    # 3. Veo 3
    if GOOGLE_API_KEY:
        log.info("[AI-Video] 3단계: Veo 3 시도")
        veo_path = output_path.with_suffix(".veo.mp4")
        if veo3_generate(image_path, duration, veo_path):
            if _mux_audio(veo_path, audio_path, duration, output_path):
                log.info("[AI-Video] ✅ Veo 3 성공")
                return True

    # 4. Hailuo / MiniMax
    if MINIMAX_API_KEY and MINIMAX_GROUP_ID:
        log.info("[AI-Video] 4단계: Hailuo 시도")
        hl_path = output_path.with_suffix(".hl.mp4")
        if hailuo_generate(image_path, duration, hl_path):
            if _mux_audio(hl_path, audio_path, duration, output_path):
                log.info("[AI-Video] ✅ Hailuo 성공")
                return True

    log.info("[AI-Video] 모든 AI 엔진 실패 → PIL 정적 프레임 사용")
    return False


def _mux_audio(video_path: Path, audio_path: Path, duration: float, output_path: Path) -> bool:
    """무음 영상 + 오디오 → 최종 영상 mux (ffmpeg)."""
    import subprocess
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "128k",
                "-t", str(duration),
                "-shortest",
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )
        return output_path.exists()
    except Exception as e:
        log.error(f"[AI-Video] 오디오 mux 실패: {e}")
        return False
