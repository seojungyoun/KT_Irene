"""
씬별 AI 이미지 생성 서비스

플로우:
  씬 대본 → 이미지 프롬프트 생성 → DALL-E 3 이미지 생성
  → 품질 평가 → (실패 시 최대 4회 재생성) → 최종 이미지 확정

지원 엔진:
  - DALL-E 3  (OPENAI_API_KEY)
  - fallback: 기존 아이린 레퍼런스 이미지 (정적)
"""
from __future__ import annotations

import logging
import os
import urllib.request
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MAX_RETRIES    = 4   # 품질 미달 시 최대 재생성 횟수

# ── 아이린 기본 프롬프트 (모든 씬에 공통 적용) ──────────────────────────────
_BASE_PROMPT = (
    "Korean female AI news anchor, 25 years old, beautiful, professional, "
    "white sleeveless mockneck dress, long natural black wavy hair, "
    "sitting at a glass news anchor desk, "
    "KT broadcast studio with deep blue and red neon accent lighting, "
    "looking directly into camera, composed and confident expression, "
    "photorealistic, cinematic, 8K, sharp focus, broadcast quality"
)


# ══════════════════════════════════════════════════════════════════════════════
# 프롬프트 생성
# ══════════════════════════════════════════════════════════════════════════════
def _build_prompt(scene_script: str) -> str:
    """씬 대본 내용을 반영한 이미지 생성 프롬프트."""
    # 대본에서 핵심 키워드 추출 (앞 120자)
    context = scene_script.strip()[:120].replace("\n", " ")
    return (
        f"{_BASE_PROMPT}. "
        f"News topic context: {context}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 품질 평가
# ══════════════════════════════════════════════════════════════════════════════
def _quality_ok(image_path: Path) -> bool:
    """
    생성된 이미지 품질 검증.
    - 파일 존재 및 최소 크기 (50KB 이상)
    - PIL로 이미지 로드 가능 여부
    - 해상도 확인 (1280px 이상)
    """
    if not image_path.exists():
        return False
    if image_path.stat().st_size < 50_000:
        log.warning(f"[ImageGen] 파일 너무 작음: {image_path.stat().st_size}B")
        return False
    try:
        from PIL import Image  # type: ignore
        with Image.open(image_path) as img:
            w, h = img.size
            if w < 512 or h < 512:
                log.warning(f"[ImageGen] 해상도 부족: {w}x{h}")
                return False
        return True
    except Exception as e:
        log.warning(f"[ImageGen] 이미지 로드 실패: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# DALL-E 3 생성
# ══════════════════════════════════════════════════════════════════════════════
def _dalle_generate(prompt: str, output_path: Path) -> bool:
    """DALL-E 3로 이미지 1장 생성 → output_path에 저장."""
    if not OPENAI_API_KEY:
        return False
    try:
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=OPENAI_API_KEY)
        resp = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1792x1024",   # 16:9 HD
            quality="hd",
            n=1,
        )
        url = resp.data[0].url
        urllib.request.urlretrieve(url, output_path)
        log.info(f"[DALL-E 3] 이미지 생성 완료: {output_path.name}")
        return True
    except ImportError:
        log.error("[DALL-E 3] openai 미설치: pip install openai")
    except Exception as e:
        log.error(f"[DALL-E 3] 생성 실패: {e}")
    return False


# ══════════════════════════════════════════════════════════════════════════════
# 공개 API
# ══════════════════════════════════════════════════════════════════════════════
def generate_scene_image(
    scene_script: str,
    output_path: Path,
) -> bool:
    """
    씬 대본을 기반으로 AI 이미지 생성.

    플로우 (플로우차트 기준):
      1. 대본 → 이미지 프롬프트 생성
      2. DALL-E 3 이미지 생성
      3. 품질 평가
         - 통과 → 완료
         - 실패 + 재시도 횟수 < 4 → 재생성
         - 실패 + 재시도 횟수 >= 4 → False 반환 (fallback 처리)

    Returns:
        True  → 이미지 생성 및 품질 통과
        False → API 키 없음 또는 4회 모두 실패
    """
    if not OPENAI_API_KEY:
        return False

    prompt = _build_prompt(scene_script)
    log.info(f"[ImageGen] 이미지 생성 시작 (최대 {MAX_RETRIES}회)")

    for attempt in range(1, MAX_RETRIES + 1):
        log.info(f"[ImageGen] 시도 {attempt}/{MAX_RETRIES}")
        tmp = output_path.with_suffix(f".try{attempt}.png")

        if not _dalle_generate(prompt, tmp):
            log.warning(f"[ImageGen] 생성 API 실패 (시도 {attempt})")
            continue

        if _quality_ok(tmp):
            tmp.rename(output_path)
            log.info(f"[ImageGen] ✅ 품질 통과 (시도 {attempt})")
            return True

        log.warning(f"[ImageGen] 품질 미달, 재생성 (시도 {attempt})")
        tmp.unlink(missing_ok=True)

    log.error(f"[ImageGen] {MAX_RETRIES}회 모두 실패 → 레퍼런스 이미지 fallback")
    return False


def image_gen_status() -> dict:
    """이미지 생성 엔진 상태."""
    has_dalle = bool(OPENAI_API_KEY)
    return {
        "engine":  "dalle3" if has_dalle else "static",
        "label":   "DALL-E 3" if has_dalle else "정적 이미지",
        "enabled": has_dalle,
    }
