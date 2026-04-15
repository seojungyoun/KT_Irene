"""
AI 영상 생성 서비스  — 대본대로 말하는 AI 앵커 영상

엔진별 역할:
  - Kling Lip-Sync : TTS 오디오 → 실제 립싱크 (입 모양이 대본과 일치)
                     9초 제한을 청킹(chunking)으로 극복, 어떤 길이도 처리
  - Veo 3          : 이미지 + 프롬프트 → "말하는 동작" 영상 생성
                     TTS 오디오를 위에 overlay (립싱크 아님, 동작만 자연스러움)
  - Hailuo/MiniMax : Veo 3와 동일한 방식
  - PIL static     : API 키 없을 때의 무음 정지화면 fallback

엔진 선택 기준: 어떤 API 키가 .env에 설정돼 있는가 (자동 cascade 없음)
  KLING_ACCESS_KEY + KLING_SECRET_KEY → Kling
  GOOGLE_API_KEY                      → Veo 3
  MINIMAX_API_KEY + MINIMAX_GROUP_ID  → Hailuo
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
GOOGLE_API_KEY   = os.getenv("GOOGLE_API_KEY", "")
MINIMAX_API_KEY  = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_GROUP_ID = os.getenv("MINIMAX_GROUP_ID", "")

KLING_BASE   = "https://api.klingai.com"
MINIMAX_BASE = "https://api.minimax.io"

# Kling Lip-Sync 단일 API 호출 최대 길이 (초)
KLING_MAX_CHUNK_SEC = 9

ANCHOR_PROMPT = (
    "Korean female news anchor speaking to camera, "
    "subtle natural lip and head movement, professional broadcast studio, "
    "cinematic lighting, high quality 1080p"
)


# ══════════════════════════════════════════════════════════════════════════════
# 오디오 유틸
# ══════════════════════════════════════════════════════════════════════════════
def _audio_duration(audio_path: Path) -> float:
    """ffprobe로 오디오 길이(초) 반환."""
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                str(audio_path),
            ],
            capture_output=True, text=True,
        )
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def _split_audio(audio_path: Path, chunk_sec: float, tmp_dir: Path) -> list[Path]:
    """오디오를 chunk_sec 단위로 분할하여 WAV 파일 목록 반환."""
    total = _audio_duration(audio_path)
    if total <= 0:
        return [audio_path]

    chunks: list[Path] = []
    start = 0.0
    idx = 0
    while start < total:
        out = tmp_dir / f"chunk_{idx:03d}.wav"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(audio_path),
                "-ss", f"{start:.3f}",
                "-t",  f"{chunk_sec:.3f}",
                "-ar", "24000",          # Kling 권장 샘플레이트
                "-ac", "1",              # 모노
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
    """ffmpeg concat demuxer로 여러 영상 이어 붙이기."""
    if len(video_paths) == 1:
        import shutil
        shutil.copy2(video_paths[0], output_path)
        return True
    tmp_list = output_path.with_suffix(".concat_list.txt")
    try:
        tmp_list.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in video_paths),
            encoding="utf-8",
        )
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(tmp_list),
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
        tmp_list.unlink(missing_ok=True)


def _mux_audio(video_path: Path, audio_path: Path, duration: float, output_path: Path) -> bool:
    """무음 영상 + 오디오 mux."""
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(video_path),
                "-i", str(audio_path),
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "128k",
                "-t", str(duration),
                "-shortest",
                str(output_path),
            ],
            check=True, capture_output=True,
        )
        return output_path.exists()
    except Exception as e:
        log.error(f"[mux] 실패: {e}")
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
    ext  = path.suffix.lower()
    mime = "image/png" if ext == ".png" else "image/jpeg"
    return f"data:{mime};base64,{_b64(path)}"


def _extract_last_frame(video_path: Path, output_path: Path) -> bool:
    """영상 마지막 프레임을 PNG로 추출 (청크 연속성용)."""
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-sseof", "-0.5",
                "-i", str(video_path),
                "-vframes", "1",
                str(output_path),
            ],
            check=True, capture_output=True,
        )
        return output_path.exists()
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# Kling AI — JWT 인증
# ══════════════════════════════════════════════════════════════════════════════
def _kling_jwt() -> Optional[str]:
    if not KLING_ACCESS_KEY or not KLING_SECRET_KEY:
        return None
    try:
        import jwt
        return jwt.encode(
            {
                "iss": KLING_ACCESS_KEY,
                "exp": int(time.time()) + 1800,
                "nbf": int(time.time()) - 5,
            },
            KLING_SECRET_KEY,
            algorithm="HS256",
        )
    except ImportError:
        log.error("[Kling] PyJWT 미설치: pip install PyJWT")
    except Exception as e:
        log.error(f"[Kling] JWT 오류: {e}")
    return None


def _kling_poll(task_id: str, endpoint: str, token: str, timeout: int = 300) -> Optional[str]:
    """Kling 작업 완료까지 폴링 → 영상 URL."""
    import httpx
    headers  = {"Authorization": f"Bearer {token}"}
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(5)
        try:
            r    = httpx.get(f"{KLING_BASE}{endpoint}/{task_id}", headers=headers, timeout=30)
            data = r.json().get("data", {})
            st   = data.get("task_status", "")
            log.debug(f"[Kling] {task_id} → {st}")
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


# ══════════════════════════════════════════════════════════════════════════════
# Kling Lip-Sync  (립싱크 핵심 — 대본과 입모양 일치)
# ══════════════════════════════════════════════════════════════════════════════
def _kling_lip_sync_single(
    image_path: Path,
    audio_path: Path,
    output_path: Path,
    token: str,
) -> bool:
    """단일 청크 립싱크 API 호출."""
    import httpx
    payload = {
        "input": {
            "mode": "audio2video",
            "audio_type": "file",
            "audio_file": _b64(audio_path),
            "image_url": _data_uri(image_path),
        }
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        r    = httpx.post(f"{KLING_BASE}/v1/videos/lip-sync", json=payload, headers=headers, timeout=60)
        resp = r.json()
        if resp.get("code") != 0:
            log.error(f"[Kling] 립싱크 API 오류: {resp}")
            return False
        task_id = resp["data"]["task_id"]
        url = _kling_poll(task_id, "/v1/videos/lip-sync", token)
        return _download(url, output_path) if url else False
    except Exception as e:
        log.error(f"[Kling] 립싱크 요청 예외: {e}")
        return False


def kling_lip_sync(image_path: Path, audio_path: Path, output_path: Path) -> bool:
    """
    Kling Lip-Sync: 어떤 길이의 오디오도 청킹으로 처리.

    - 9초 이하: 단일 API 호출
    - 9초 초과: 9초 단위로 분할 → 각 청크 립싱크 → 마지막 프레임을 다음 청크 입력 이미지로 사용
                (얼굴 일관성 유지) → ffmpeg concat
    """
    token = _kling_jwt()
    if not token:
        return False

    duration = _audio_duration(audio_path)
    log.info(f"[Kling] 오디오 길이: {duration:.1f}s")

    if duration <= KLING_MAX_CHUNK_SEC:
        log.info("[Kling] 단일 립싱크 호출")
        return _kling_lip_sync_single(image_path, audio_path, output_path, token)

    # 청킹 처리
    log.info(f"[Kling] 청킹 모드: {KLING_MAX_CHUNK_SEC}s 단위로 분할")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir  = Path(tmp)
        chunks   = _split_audio(audio_path, KLING_MAX_CHUNK_SEC, tmp_dir)
        log.info(f"[Kling] {len(chunks)}개 청크 생성")

        chunk_videos: list[Path] = []
        current_image = image_path  # 첫 청크는 원본 레퍼런스 이미지

        for i, chunk_audio in enumerate(chunks):
            chunk_video = tmp_dir / f"lip_{i:03d}.mp4"
            log.info(f"[Kling] 청크 {i+1}/{len(chunks)} 립싱크 중...")
            ok = _kling_lip_sync_single(current_image, chunk_audio, chunk_video, token)
            if not ok:
                log.error(f"[Kling] 청크 {i+1} 실패")
                return False
            chunk_videos.append(chunk_video)

            # 다음 청크의 입력 이미지 = 현재 청크의 마지막 프레임 (얼굴 연속성)
            last_frame = tmp_dir / f"last_{i:03d}.png"
            if _extract_last_frame(chunk_video, last_frame):
                current_image = last_frame

        log.info("[Kling] 청크 영상 이어붙이기...")
        return _concat_videos(chunk_videos, output_path)


# ══════════════════════════════════════════════════════════════════════════════
# Veo 3  (말하는 동작 영상 + TTS 오디오 overlay)
# ══════════════════════════════════════════════════════════════════════════════
def veo3_generate(image_path: Path, audio_path: Path, output_path: Path) -> bool:
    """
    Veo 3: 이미지 → '말하는 동작' 영상 생성 후 TTS 오디오 overlay.
    ※ 실제 립싱크(입모양 일치)는 아님. 자연스러운 앵커 동작 영상.
    """
    if not GOOGLE_API_KEY:
        return False
    try:
        from google import genai       # type: ignore
        from google.genai import types # type: ignore

        client    = genai.Client(api_key=GOOGLE_API_KEY)
        duration  = _audio_duration(audio_path)
        clip_sec  = min(max(int(duration), 5), 8)  # Veo 3 최대 8초

        log.info(f"[Veo3] 영상 생성 요청 (목표 {clip_sec}s)...")
        operation = client.models.generate_video(
            model="veo-2.0-generate-001",
            prompt=ANCHOR_PROMPT,
            image=types.Image(
                image_bytes=image_path.read_bytes(),
                mime_type="image/png" if image_path.suffix == ".png" else "image/jpeg",
            ),
            config=types.GenerateVideoConfig(
                duration_seconds=clip_sec,
                fps=24,
                aspect_ratio="16:9",
                person_generation="allow_adult",
            ),
        )
        deadline = time.time() + 600
        while not operation.done and time.time() < deadline:
            time.sleep(10)
            operation = client.operations.get(operation)
            log.debug(f"[Veo3] 생성 중... done={operation.done}")

        if not (operation.done and operation.response):
            log.error("[Veo3] 타임아웃 또는 실패")
            return False

        vids = operation.response.generated_videos
        if not (vids and vids[0].video and vids[0].video.video_bytes):
            log.error("[Veo3] 영상 데이터 없음")
            return False

        raw = output_path.with_suffix(".veo_raw.mp4")
        raw.write_bytes(vids[0].video.video_bytes)

        # 짧은 클립을 오디오 길이에 맞게 루프 + TTS 오디오 mux
        return _loop_and_mux(raw, audio_path, duration, output_path)

    except ImportError:
        log.error("[Veo3] google-genai 미설치: pip install google-genai")
    except Exception as e:
        log.error(f"[Veo3] 예외: {e}")
    return False


# ══════════════════════════════════════════════════════════════════════════════
# Hailuo / MiniMax  (말하는 동작 영상 + TTS 오디오 overlay)
# ══════════════════════════════════════════════════════════════════════════════
def hailuo_generate(image_path: Path, audio_path: Path, output_path: Path) -> bool:
    """
    Hailuo(MiniMax): 이미지 → '말하는 동작' 영상 생성 후 TTS 오디오 overlay.
    ※ Veo 3와 동일하게 실제 립싱크 아님.
    """
    if not MINIMAX_API_KEY or not MINIMAX_GROUP_ID:
        return False
    try:
        import httpx
        duration = _audio_duration(audio_path)
        headers  = {
            "Authorization": f"Bearer {MINIMAX_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "video-01",
            "prompt": ANCHOR_PROMPT,
            "first_frame_image": _data_uri(image_path),
        }
        log.info("[Hailuo] 영상 생성 요청...")
        r       = httpx.post(
            f"{MINIMAX_BASE}/v1/video_generation?GroupId={MINIMAX_GROUP_ID}",
            json=payload, headers=headers, timeout=60,
        )
        task_id = r.json().get("task_id")
        if not task_id:
            log.error(f"[Hailuo] task_id 없음: {r.text}")
            return False

        # 폴링
        deadline = time.time() + 400
        while time.time() < deadline:
            time.sleep(8)
            pr = httpx.get(
                f"{MINIMAX_BASE}/v1/query/video_generation"
                f"?task_id={task_id}&GroupId={MINIMAX_GROUP_ID}",
                headers=headers, timeout=30,
            )
            pd     = pr.json()
            status = pd.get("status", "")
            log.debug(f"[Hailuo] status={status}")
            if status == "Success":
                url = pd.get("video_url") or pd.get("file_id", "")
                if url.startswith("http"):
                    raw = output_path.with_suffix(".hl_raw.mp4")
                    if _download(url, raw):
                        return _loop_and_mux(raw, audio_path, duration, output_path)
                log.error(f"[Hailuo] URL 파싱 실패: {pd}")
                return False
            if status in ("Fail", "Unknown"):
                log.error(f"[Hailuo] 실패: {pd}")
                return False
        log.error("[Hailuo] 타임아웃")
    except Exception as e:
        log.error(f"[Hailuo] 예외: {e}")
    return False


def _loop_and_mux(video_path: Path, audio_path: Path, duration: float, output_path: Path) -> bool:
    """짧은 영상을 필요한 길이만큼 루프한 뒤 TTS 오디오를 mux."""
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-stream_loop", "-1",    # 무한 루프
                "-i", str(video_path),
                "-i", str(audio_path),
                "-c:v", "libx264",
                "-c:a", "aac", "-b:a", "128k",
                "-t", str(duration),
                "-shortest",
                str(output_path),
            ],
            check=True, capture_output=True,
        )
        return output_path.exists()
    except Exception as e:
        log.error(f"[loop_mux] 실패: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# 상태 조회
# ══════════════════════════════════════════════════════════════════════════════
def ai_video_status() -> dict:
    has_kling  = bool(KLING_ACCESS_KEY and KLING_SECRET_KEY)
    has_veo3   = bool(GOOGLE_API_KEY)
    has_hailuo = bool(MINIMAX_API_KEY and MINIMAX_GROUP_ID)

    if has_kling:
        engine, label, lip_sync = "kling",  "Kling AI (립싱크)", True
    elif has_veo3:
        engine, label, lip_sync = "veo3",   "Veo 3",             False
    elif has_hailuo:
        engine, label, lip_sync = "hailuo", "Hailuo",            False
    else:
        engine, label, lip_sync = "static", "정적 프레임 (PIL)", False

    return {
        "engine":     engine,
        "label":      label,
        "lip_sync":   lip_sync,   # 실제 립싱크 여부
        "ai_enabled": engine != "static",
        "kling":      has_kling,
        "veo3":       has_veo3,
        "hailuo":     has_hailuo,
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
    설정된 엔진 하나만 사용. 실패 시 False → 호출자가 PIL fallback.
    다른 유료 API로 자동 전환하지 않음.
    """
    if not image_path.exists():
        return False

    status = ai_video_status()
    engine = status["engine"]

    if engine == "kling":
        # 실제 립싱크: TTS 오디오 기반으로 입 모양 생성
        return kling_lip_sync(image_path, audio_path, output_path)

    if engine == "veo3":
        # 말하는 동작 영상 + TTS 오디오 overlay
        return veo3_generate(image_path, audio_path, output_path)

    if engine == "hailuo":
        # 말하는 동작 영상 + TTS 오디오 overlay
        return hailuo_generate(image_path, audio_path, output_path)

    return False  # static: PIL fallback
