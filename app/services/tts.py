"""TTS (Text-to-Speech) 서비스 모듈

우선순위:
1. KT 믿음 TTS  — 환경변수 KT_TTS_API_KEY + KT_TTS_API_URL 설정 시
2. edge-tts      — Microsoft Edge TTS (ko-KR-SunHiNeural), 설치 시
3. Sine-wave     — 최후 폴백 (음성 패키지 없는 환경)
"""
from __future__ import annotations

import asyncio
import base64
import math
import os
import re
import struct
import subprocess
import threading
import wave
from pathlib import Path

# ── 환경변수 ────────────────────────────────────────────────────────────────
KT_TTS_API_KEY: str  = os.environ.get("KT_TTS_API_KEY",  "")
KT_TTS_API_URL: str  = os.environ.get("KT_TTS_API_URL",  "")
EDGE_TTS_VOICE: str  = os.environ.get("IRENE_TTS_VOICE", "ko-KR-SunHiNeural")


# ── 발음 사전 적용 ────────────────────────────────────────────────────────────
def apply_pronunciation(script: str, pronunciation_dict: dict[str, str]) -> str:
    rendered = script
    for src, target in pronunciation_dict.items():
        rendered = rendered.replace(src, target)
    return rendered


# ══════════════════════════════════════════════════════════════════════════════
# 1순위 — KT 믿음 TTS
# ══════════════════════════════════════════════════════════════════════════════
def _kt_tts(text: str, output_path: Path) -> float | None:
    """
    KT 믿음 TTS API 호출.
    성공 시 재생 시간(초) 반환, 실패/미설정 시 None 반환.

    API 스펙 (환경변수로 주입):
      KT_TTS_API_URL  — ex) https://aiapi.kt.co.kr/tts/v1/synthesis
      KT_TTS_API_KEY  — Bearer 토큰 or API-Key
    """
    if not (KT_TTS_API_KEY and KT_TTS_API_URL):
        return None

    try:
        import httpx  # type: ignore

        headers = {
            "Authorization": f"Bearer {KT_TTS_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "voice": "mideum",          # KT 믿음 기본 보이스 ID
            "speed": 1.0,
            "pitch": 0,
            "format": "wav",
        }

        with httpx.Client(timeout=30) as client:
            resp = client.post(KT_TTS_API_URL, json=payload, headers=headers)
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")

        # ── 응답이 JSON { "audio": "<base64>" } 형식인 경우 ──────────────
        if "application/json" in content_type:
            data = resp.json()
            audio_bytes = base64.b64decode(data.get("audio") or data.get("data") or "")
        else:
            # 바이너리 WAV/MP3 직접 반환
            audio_bytes = resp.content

        if not audio_bytes:
            return None

        # 확장자 추정
        if audio_bytes[:3] == b"ID3" or audio_bytes[:2] == b"\xff\xfb":
            tmp_path = output_path.with_suffix(".tmp.mp3")
            tmp_path.write_bytes(audio_bytes)
            ok = _mp3_to_wav(tmp_path, output_path)
            try:
                tmp_path.unlink()
            except Exception:
                pass
            if not ok:
                output_path.write_bytes(audio_bytes)
        else:
            output_path.write_bytes(audio_bytes)

        return _get_wav_duration(output_path) if output_path.suffix == ".wav" else max(
            1.0, len(audio_bytes) / 20000
        )

    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 2순위 — edge-tts (Microsoft Edge TTS)
# ══════════════════════════════════════════════════════════════════════════════
def _run_edge_tts(text: str, output_mp3: Path, voice: str = EDGE_TTS_VOICE) -> None:
    """edge-tts를 별도 이벤트 루프에서 실행 (스레드 안전)."""
    import edge_tts  # type: ignore

    async def _go() -> None:
        communicate = edge_tts.Communicate(text=text, voice=voice)
        await communicate.save(str(output_mp3))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_go())
    finally:
        loop.close()


def _edge_tts(text: str, output_path: Path, sample_rate: int = 22050) -> float | None:
    """edge-tts 래퍼. 성공 시 재생 시간(초) 반환, 실패 시 None."""
    try:
        mp3_path = output_path.with_suffix(".mp3")
        t = threading.Thread(target=_run_edge_tts, args=(text, mp3_path))
        t.start()
        t.join(timeout=30)

        if not (mp3_path.exists() and mp3_path.stat().st_size > 500):
            return None

        if _mp3_to_wav(mp3_path, output_path, sample_rate):
            duration = _get_wav_duration(output_path)
        else:
            output_path.write_bytes(mp3_path.read_bytes())
            duration = max(1.0, mp3_path.stat().st_size / 20000)

        try:
            mp3_path.unlink()
        except Exception:
            pass

        return duration

    except ImportError:
        return None
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 3순위 — Sine-wave fallback
# ══════════════════════════════════════════════════════════════════════════════
def _synth_sine(script: str, output_path: Path, sample_rate: int = 22050) -> float:
    duration_sec = max(1.5, min(10.0, len(script) / 7.0))
    n_samples = int(duration_sec * sample_rate)

    with wave.open(str(output_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        freq, amp = 220.0, 4000
        frames = bytearray()
        for i in range(n_samples):
            envelope = min(1.0, i / max(1, sample_rate * 0.05)) * min(
                1.0, (n_samples - i) / max(1, sample_rate * 0.05)
            )
            v = int(
                amp * envelope
                * (1.0 + 0.15 * math.sin(2 * math.pi * 2.0 * i / sample_rate))
                * math.sin(2 * math.pi * freq * i / sample_rate)
            )
            frames.extend(struct.pack("<h", max(-32768, min(32767, v))))
        wf.writeframes(bytes(frames))
    return duration_sec


# ══════════════════════════════════════════════════════════════════════════════
# 공통 유틸
# ══════════════════════════════════════════════════════════════════════════════
def _mp3_to_wav(mp3_path: Path, wav_path: Path, sample_rate: int = 22050) -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(mp3_path),
             "-ar", str(sample_rate), "-ac", "1", "-sample_fmt", "s16", str(wav_path)],
            check=True, capture_output=True,
        )
        return True
    except Exception:
        return False


def _get_wav_duration(wav_path: Path) -> float:
    try:
        with wave.open(str(wav_path), "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return 3.0


# ══════════════════════════════════════════════════════════════════════════════
# 공개 API
# ══════════════════════════════════════════════════════════════════════════════
def synthesize_wav(script: str, output_path: Path, sample_rate: int = 22050) -> float:
    """
    한국어 TTS를 생성하고 WAV 파일로 저장합니다.
    우선순위: KT 믿음 TTS → edge-tts → sine-wave fallback

    Returns:
        float: 음성 길이(초)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1) KT 믿음 TTS
    dur = _kt_tts(script, output_path)
    if dur is not None:
        return dur

    # 2) edge-tts
    dur = _edge_tts(script, output_path, sample_rate)
    if dur is not None:
        return dur

    # 3) sine-wave fallback
    return _synth_sine(script, output_path, sample_rate)


def write_srt(script: str, duration_sec: float, output_path: Path) -> None:
    """씬 자막 SRT 파일 생성 (문장별 분할)."""
    segments = _split_srt_segments(script, duration_sec)
    entries = []
    for idx, (start, end, text) in enumerate(segments, 1):
        entries.append(f"{idx}\n{_fmt_srt(start)} --> {_fmt_srt(end)}\n{text}\n")
    output_path.write_text("\n".join(entries), encoding="utf-8")


def _split_srt_segments(script: str, duration_sec: float) -> list[tuple[float, float, str]]:
    sentences = re.split(r"(?<=[.!?다요죠습니다])\s+", script.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return [(0.0, duration_sec, script)]
    total = max(1, sum(len(s) for s in sentences))
    segs: list[tuple[float, float, str]] = []
    t = 0.0
    for s in sentences:
        d = len(s) / total * duration_sec
        segs.append((t, t + d, s))
        t += d
    return segs


def _fmt_srt(sec: float) -> str:
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    ms = int((sec % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
