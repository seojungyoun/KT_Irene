from __future__ import annotations

import subprocess
from pathlib import Path

from .tts import apply_pronunciation, synthesize_wav, write_srt

BACKGROUND_COLOR_MAP = {
    "kt_studio": "1c1c1e",
    "white_room": "efefef",
    "red_gradient": "9b1420",
}


def _write_placeholder_video(path: Path, message: str) -> None:
    path.write_text(
        "Placeholder video artifact.\n"
        f"{message}\n"
        "Install moviepy or ffmpeg for real mp4 rendering.\n",
        encoding="utf-8",
    )


def _write_last_frame(path: Path) -> None:
    try:
        from PIL import Image, ImageDraw

        path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (1280, 720), color=(24, 24, 24))
        draw = ImageDraw.Draw(img)
        draw.rectangle((40, 40, 1240, 680), outline=(216, 30, 49), width=6)
        draw.text((70, 70), "IRENE LAST FRAME", fill=(255, 255, 255))
        img.save(path)
    except Exception:
        path.write_text("last frame placeholder", encoding="utf-8")


def _try_generate_with_ffmpeg(video_path: Path, wav_path: Path, duration_sec: float, bg_hex: str) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=#{bg_hex}:s=1280x720:d={duration_sec}",
        "-i",
        str(wav_path),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(video_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def generate_scene_video(
    scene_script: str,
    scene_dir: Path,
    pronunciation_dict: dict[str, str] | None = None,
    init_frame_path: Path | None = None,
    background: str = "kt_studio",
) -> tuple[float, Path, Path, Path, Path]:
    scene_dir.mkdir(parents=True, exist_ok=True)

    pronunciation_dict = pronunciation_dict or {}
    spoken_script = apply_pronunciation(scene_script, pronunciation_dict)

    wav_path = scene_dir / "tts.wav"
    duration_sec = synthesize_wav(spoken_script, wav_path)

    subtitle_path = scene_dir / "subtitle.srt"
    write_srt(scene_script, duration_sec, subtitle_path)

    video_path = scene_dir / "scene.mp4"
    last_frame_path = scene_dir / "last_frame.png"
    bg_hex = BACKGROUND_COLOR_MAP.get(background, BACKGROUND_COLOR_MAP["kt_studio"])

    try:
        from moviepy import AudioFileClip, ColorClip

        clip = ColorClip(size=(1280, 720), color=tuple(int(bg_hex[i : i + 2], 16) for i in (0, 2, 4)), duration=duration_sec)
        audio_clip = AudioFileClip(str(wav_path))
        clip = clip.with_audio(audio_clip)
        clip.write_videofile(
            str(video_path),
            fps=24,
            codec="libx264",
            audio_codec="aac",
            logger=None,
        )
    except Exception:
        try:
            _try_generate_with_ffmpeg(video_path, wav_path, duration_sec, bg_hex)
        except Exception as exc:
            _write_placeholder_video(video_path, f"generation error: {exc}")

    _write_last_frame(last_frame_path)

    if init_frame_path and init_frame_path.exists():
        (scene_dir / "continuity.txt").write_text(
            f"Initialized from {init_frame_path.name}", encoding="utf-8"
        )

    return duration_sec, wav_path, subtitle_path, video_path, last_frame_path
