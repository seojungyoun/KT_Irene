"""씬 비디오 생성 서비스

파이프라인:
  1. TTS 음성 생성 (KT 믿음 → edge-tts → sine-wave)
  2. SRT 자막 생성
  3. PIL 컴포지트 프레임 생성
     - 배경(KT Studio / White Room / Red Gradient)
     - 아이린 레퍼런스 이미지 오버레이 (data/assets/irene_reference.png)
     - 하단 자막 바
     - KT 로고
  4. ffmpeg: 정지 이미지 × 오디오 → scene.mp4
  5. 마지막 프레임 추출
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .tts import apply_pronunciation, synthesize_wav, write_srt

# ── 경로 설정 ────────────────────────────────────────────────────────────────
_BASE_DIR   = Path(__file__).resolve().parent.parent.parent
ASSETS_DIR  = _BASE_DIR / "data" / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

IRENE_REF_PATH  = ASSETS_DIR / "irene_reference.png"
KT_LOGO_PATH    = ASSETS_DIR / "kt_logo.png"

# ── 배경 색상 매핑 ────────────────────────────────────────────────────────────
BG_COLORS = {
    "kt_studio":    [(20, 20, 30),   (10, 10, 20)],    # 딥 다크 블루
    "white_room":   [(240, 242, 246),(220, 225, 235)],  # 밝은 화이트
    "red_gradient": [(180, 20, 40),  (80, 10, 20)],     # KT 레드
}
DEFAULT_BG = "kt_studio"

# 로고 위치 오프셋 (margin)
LOGO_MARGIN = 24


# ══════════════════════════════════════════════════════════════════════════════
# 에셋 생성 (최초 실행 시 1회)
# ══════════════════════════════════════════════════════════════════════════════
def _ensure_assets() -> None:
    if not IRENE_REF_PATH.exists():
        _create_irene_placeholder(IRENE_REF_PATH)
    if not KT_LOGO_PATH.exists():
        _create_kt_logo(KT_LOGO_PATH)


def _create_irene_placeholder(path: Path) -> None:
    """아이린 레퍼런스 이미지가 없을 때 사용되는 플레이스홀더 생성.
    실제 운영 시 data/assets/irene_reference.png 를 실제 아이린 이미지로 교체하세요."""
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore

        W, H = 480, 720
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # 앵커 영역 배경 (반투명 어두운 그라디언트)
        for y in range(H):
            alpha = int(200 * (1 - y / H * 0.3))
            draw.line([(0, y), (W, y)], fill=(15, 15, 25, alpha))

        # ─ 인체 비율 (167cm / 8등신 기준) ────────────────────────────
        cx = W // 2
        unit = H // 8          # 1등신 = H/8

        # 머리
        head_r = int(unit * 0.48)
        head_cy = int(unit * 0.9)
        draw.ellipse(
            [cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r],
            fill=(253, 235, 210, 255),
        )

        # 넥
        neck_w = int(head_r * 0.38)
        neck_top = head_cy + head_r - 4
        neck_bot = head_cy + head_r + int(unit * 0.28)
        draw.rectangle([cx - neck_w, neck_top, cx + neck_w, neck_bot],
                       fill=(245, 220, 200, 255))

        # 어깨 / 몸통
        sh_w   = int(unit * 1.55)          # 어깨 너비
        body_h = int(unit * 2.6)
        body_top = neck_bot
        body_bot = body_top + body_h
        # 어깨 사다리꼴
        draw.polygon(
            [
                (cx - sh_w, body_top + int(unit * 0.18)),
                (cx + sh_w, body_top + int(unit * 0.18)),
                (cx + int(sh_w * 0.72), body_bot),
                (cx - int(sh_w * 0.72), body_bot),
            ],
            fill=(248, 248, 248, 255),
        )
        # 목 커버
        draw.rectangle([cx - neck_w, neck_top, cx + neck_w, body_top + int(unit * 0.2)],
                       fill=(248, 248, 248, 255))

        # 스커트
        sk_top = body_bot
        sk_bot = sk_top + int(unit * 2.1)
        sk_tw  = int(sh_w * 0.72)
        sk_bw  = int(sh_w * 0.6)
        draw.polygon(
            [
                (cx - sk_tw, sk_top),
                (cx + sk_tw, sk_top),
                (cx + sk_bw, sk_bot),
                (cx - sk_bw, sk_bot),
            ],
            fill=(248, 248, 248, 255),
        )

        # 다리
        leg_w = int(unit * 0.22)
        leg_top = sk_bot
        leg_bot = leg_top + int(unit * 1.2)
        draw.rectangle([cx - sk_bw + 2,         leg_top, cx - sk_bw + leg_w * 2, leg_bot],
                       fill=(245, 220, 200, 255))
        draw.rectangle([cx + sk_bw - leg_w * 2, leg_top, cx + sk_bw - 2,         leg_bot],
                       fill=(245, 220, 200, 255))

        # 하이힐
        heel_h = int(unit * 0.16)
        draw.rectangle([cx - sk_bw + 2,          leg_bot, cx - sk_bw + leg_w * 2, leg_bot + heel_h],
                       fill=(230, 230, 230, 255))
        draw.rectangle([cx + sk_bw - leg_w * 2,  leg_bot, cx + sk_bw - 2,         leg_bot + heel_h],
                       fill=(230, 230, 230, 255))

        # 헤어 (S컬 웨이브, 어두운 갈색)
        hair_color = (15, 10, 10, 255)
        hw = int(head_r * 1.15)
        # 상단 헤어
        draw.ellipse(
            [cx - hw, head_cy - head_r - int(unit * 0.12),
             cx + hw, head_cy + int(head_r * 0.3)],
            fill=hair_color,
        )
        # 얼굴 오버레이 (피부)
        draw.ellipse(
            [cx - head_r + 6, head_cy - head_r + 12,
             cx + head_r - 6, head_cy + head_r - 4],
            fill=(253, 235, 210, 255),
        )
        # 긴 웨이브 헤어 (양옆)
        draw.ellipse([cx - hw - 8, head_cy - int(head_r * 0.4),
                      cx - int(head_r * 0.5), body_top + int(unit * 1.2)],
                     fill=hair_color)
        draw.ellipse([cx + int(head_r * 0.3), head_cy - int(head_r * 0.2),
                      cx + hw + 4, body_top + int(unit * 0.9)],
                     fill=hair_color)

        # 눈
        eye_y = head_cy - int(head_r * 0.08)
        for ex in [cx - int(head_r * 0.33), cx + int(head_r * 0.33)]:
            draw.ellipse([ex - 9, eye_y - 5, ex + 9, eye_y + 5], fill=(20, 15, 15, 255))
            draw.ellipse([ex - 3, eye_y - 2, ex + 3, eye_y + 2], fill=(255, 255, 255, 200))

        # 입
        lip_y = head_cy + int(head_r * 0.42)
        draw.arc([cx - 11, lip_y - 4, cx + 11, lip_y + 6], start=10, end=170,
                 fill=(220, 100, 100, 255), width=3)

        # 하단 이름 배지
        badge_y = H - 60
        draw.rectangle([20, badge_y, W - 20, H - 16], fill=(230, 0, 45, 200))
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 22)
        except Exception:
            font = ImageFont.load_default()
        draw.text((W // 2, badge_y + 18), "AI 아나운서  아이린",
                  fill=(255, 255, 255, 255), font=font, anchor="mm")

        img.save(path, "PNG")
    except Exception:
        # PIL 미설치 — 빈 PNG 저장
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)


def _create_kt_logo(path: Path) -> None:
    """KT 로고 PNG 생성."""
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore

        W, H = 120, 50
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([0, 0, W - 1, H - 1], radius=8, fill=(230, 0, 45, 220))
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 30)
        except Exception:
            font = ImageFont.load_default()
        draw.text((W // 2, H // 2), "KT", fill=(255, 255, 255, 255),
                  font=font, anchor="mm")
        img.save(path, "PNG")
    except Exception:
        path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)


# ══════════════════════════════════════════════════════════════════════════════
# 프레임 컴포지트 (PIL)
# ══════════════════════════════════════════════════════════════════════════════
def _make_composite_frame(
    subtitle: str,
    background: str,
    logo_position: str,
    outfit: str,
    output_path: Path,
    W: int = 1280,
    H: int = 720,
) -> None:
    """배경 + 아이린 + 자막 + 로고를 합성한 프레임 이미지를 생성합니다."""
    from PIL import Image, ImageDraw, ImageFont  # type: ignore

    # ── 배경 그라디언트 ─────────────────────────────────────────────────────
    colors = BG_COLORS.get(background, BG_COLORS[DEFAULT_BG])
    c1, c2 = colors[0], colors[1]
    frame = Image.new("RGB", (W, H))
    draw  = ImageDraw.Draw(frame)
    for y in range(H):
        r = int(c1[0] + (c2[0] - c1[0]) * y / H)
        g = int(c1[1] + (c2[1] - c1[1]) * y / H)
        b = int(c1[2] + (c2[2] - c1[2]) * y / H)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # ── 앵커 데스크 효과 (하단 수평선) ──────────────────────────────────────
    desk_y = H - 140
    draw.rectangle([0, desk_y, W, desk_y + 3], fill=(230, 0, 45))
    draw.rectangle([0, desk_y + 4, W, H], fill=_darken(c2, 20))

    # ── 아이린 이미지 오버레이 ───────────────────────────────────────────────
    if IRENE_REF_PATH.exists():
        try:
            irene = Image.open(IRENE_REF_PATH).convert("RGBA")
            target_h = desk_y + 10
            ratio    = target_h / irene.height
            target_w = int(irene.width * ratio)
            irene    = irene.resize((target_w, target_h), Image.LANCZOS)
            ix       = int(W * 0.12)
            iy       = H - target_h - 10
            frame.paste(irene, (ix, iy), irene)
        except Exception:
            pass

    # ── 로고 ────────────────────────────────────────────────────────────────
    if KT_LOGO_PATH.exists():
        try:
            logo = Image.open(KT_LOGO_PATH).convert("RGBA")
            lw, lh = logo.size
            lx, ly = _logo_pos(logo_position, W, H, lw, lh)
            frame.paste(logo, (lx, ly), logo)
        except Exception:
            pass

    # ── 자막 바 (alpha overlay) ───────────────────────────────────────────────
    if subtitle:
        frame = _draw_subtitle(frame, subtitle, W, H)

    frame.save(output_path, "PNG")


def _lighten(color: tuple, amount: int) -> tuple:
    return tuple(min(255, c + amount) for c in color)  # type: ignore


def _darken(color: tuple, amount: int) -> tuple:
    return tuple(max(0, c - amount) for c in color)  # type: ignore


def _logo_pos(position: str, W: int, H: int, lw: int, lh: int) -> tuple[int, int]:
    m = LOGO_MARGIN
    return {
        "top-left":     (m,          m),
        "top-right":    (W - lw - m, m),
        "bottom-left":  (m,          H - lh - m),
        "bottom-right": (W - lw - m, H - lh - m),
    }.get(position, (W - lw - m, m))


def _draw_subtitle(frame: "Image.Image", text: str, W: int, H: int) -> "Image.Image":
    """하단 자막 바를 frame 위에 합성하여 새 이미지를 반환합니다."""
    from PIL import Image, ImageDraw, ImageFont  # type: ignore

    # 긴 텍스트 줄바꿈
    max_chars = 38
    if len(text) > max_chars:
        mid = len(text) // 2
        for i in range(mid, min(mid + 14, len(text))):
            if text[i] in " ,":
                text = text[:i] + "\n" + text[i + 1:]
                break
        else:
            text = text[:max_chars] + "\n" + text[max_chars:]

    lines  = text.split("\n")
    line_h = 38
    bar_h  = line_h * len(lines) + 28
    bar_y  = H - bar_h - 20

    # 반투명 오버레이 생성
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw   = ImageDraw.Draw(overlay)
    odraw.rounded_rectangle(
        [W // 6, bar_y, W * 5 // 6, bar_y + bar_h],
        radius=8,
        fill=(0, 0, 0, 180),
    )

    # 폰트
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 28)
    except Exception:
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc", 28
            )
        except Exception:
            font = ImageFont.load_default()

    for i, line in enumerate(lines):
        ty = bar_y + 14 + i * line_h
        odraw.text((W // 2, ty), line, fill=(255, 255, 255, 255), font=font, anchor="mt")

    # 합성
    base = frame.convert("RGBA")
    merged = Image.alpha_composite(base, overlay)
    return merged.convert("RGB")


# ══════════════════════════════════════════════════════════════════════════════
# ffmpeg 비디오 생성
# ══════════════════════════════════════════════════════════════════════════════
def _ffmpeg_image_to_video(
    frame_path: Path,
    audio_path: Path,
    duration: float,
    output_path: Path,
) -> bool:
    """정지 이미지 + 오디오 → mp4."""
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-loop", "1",
                "-framerate", "24",
                "-i", str(frame_path),
                "-i", str(audio_path),
                "-c:v", "libx264",
                "-tune", "stillimage",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "128k",
                "-t", str(duration),
                "-shortest",
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )
        return True
    except Exception:
        return False


def _moviepy_fallback(frame_path: Path, audio_path: Path, duration: float, output_path: Path) -> bool:
    try:
        from moviepy import AudioFileClip, ImageClip  # type: ignore

        clip  = ImageClip(str(frame_path), duration=duration)
        audio = AudioFileClip(str(audio_path))
        clip  = clip.with_audio(audio)
        clip.write_videofile(str(output_path), fps=24, codec="libx264",
                             audio_codec="aac", logger=None)
        clip.close()
        audio.close()
        return True
    except Exception:
        return False


def _extract_last_frame(video_path: Path, output_path: Path) -> None:
    """영상의 마지막 프레임을 PNG로 추출합니다."""
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-sseof", "-0.1",
                "-i", str(video_path),
                "-vframes", "1",
                "-q:v", "2",
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )
        if output_path.exists():
            return
    except Exception:
        pass
    # fallback: 컴포지트 프레임을 그대로 복사
    frame_path = video_path.parent / "frame_composite.png"
    if frame_path.exists():
        output_path.write_bytes(frame_path.read_bytes())


# ══════════════════════════════════════════════════════════════════════════════
# 공개 API
# ══════════════════════════════════════════════════════════════════════════════
def generate_scene_video(
    scene_script: str,
    scene_dir: Path,
    pronunciation_dict: dict[str, str] | None = None,
    init_frame_path: Path | None = None,
    background: str = "kt_studio",
    logo_position: str = "top-right",
    outfit: str = "white_mockneck",
    hair: str = "long_s_wave_6_4",
) -> tuple[float, Path, Path, Path, Path]:
    """
    씬 비디오를 완전히 생성합니다.

    Returns:
        (duration_sec, wav_path, subtitle_path, video_path, last_frame_path)
    """
    scene_dir.mkdir(parents=True, exist_ok=True)
    _ensure_assets()

    pronunciation_dict = pronunciation_dict or {}
    spoken = apply_pronunciation(scene_script, pronunciation_dict)

    # ① TTS
    wav_path = scene_dir / "tts.wav"
    duration = synthesize_wav(spoken, wav_path)

    # ② 자막 SRT
    subtitle_path = scene_dir / "subtitle.srt"
    write_srt(scene_script, duration, subtitle_path)

    # ③ 컴포지트 프레임 (PIL)
    frame_path = scene_dir / "frame_composite.png"
    _make_composite_frame(
        subtitle=scene_script,
        background=background,
        logo_position=logo_position,
        outfit=outfit,
        output_path=frame_path,
    )

    # ④ 비디오 생성 (ffmpeg → moviepy → placeholder)
    video_path = scene_dir / "scene.mp4"
    if not _ffmpeg_image_to_video(frame_path, wav_path, duration, video_path):
        if not _moviepy_fallback(frame_path, wav_path, duration, video_path):
            video_path.write_text(
                "비디오 생성 실패: ffmpeg와 moviepy 모두 사용 불가\n", encoding="utf-8"
            )

    # ⑤ 마지막 프레임 추출
    last_frame_path = scene_dir / "last_frame.png"
    _extract_last_frame(video_path, last_frame_path)

    # ⑥ 연속성 메타
    if init_frame_path and init_frame_path.exists():
        (scene_dir / "continuity.txt").write_text(
            f"Initialized from: {init_frame_path.name}\n", encoding="utf-8"
        )

    return duration, wav_path, subtitle_path, video_path, last_frame_path
