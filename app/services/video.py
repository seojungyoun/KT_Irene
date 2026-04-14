from __future__ import annotations

from pathlib import Path

from .tts import synthesize_wav


def _write_placeholder_video(path: Path, message: str) -> None:
    path.write_text(
        "Placeholder video artifact.\n"
        f"{message}\n"
        "Install moviepy+ffmpeg for real mp4 rendering.\n",
        encoding="utf-8",
    )


def _write_last_frame(path: Path) -> None:
    try:
        from PIL import Image, ImageDraw

        path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (1280, 720), color=(58, 62, 72))
        draw = ImageDraw.Draw(img)
        draw.rectangle((50, 50, 1230, 670), outline=(230, 230, 235), width=5)
        draw.text((80, 80), "IRENE LAST FRAME", fill=(240, 240, 240))
        img.save(path)
    except Exception:
        path.write_text("last frame placeholder", encoding="utf-8")


def generate_scene_video(
    scene_script: str,
    scene_dir: Path,
    pronunciation_dict: dict[str, str] | None = None,
    init_frame_path: Path | None = None,
) -> tuple[float, Path, Path, Path]:
    pronunciation_dict = pronunciation_dict or {}
    scene_dir.mkdir(parents=True, exist_ok=True)

    wav_path = scene_dir / "tts.wav"
    duration_sec = synthesize_wav(scene_script, wav_path)
    video_path = scene_dir / "scene.mp4"
    last_frame_path = scene_dir / "last_frame.png"

    try:
        from moviepy import AudioFileClip, ColorClip

        clip = ColorClip(size=(1280, 720), color=(39, 42, 49), duration=duration_sec)
        audio_clip = AudioFileClip(str(wav_path))
        clip = clip.with_audio(audio_clip)
        clip.write_videofile(
            str(video_path),
            fps=24,
            codec="libx264",
            audio_codec="aac",
            logger=None,
        )
        _write_last_frame(last_frame_path)
        if init_frame_path and init_frame_path.exists():
            # Continuity metadata
            (scene_dir / "continuity.txt").write_text(
                f"Initialized from {init_frame_path.name}", encoding="utf-8"
            )
    except Exception as exc:
        _write_placeholder_video(video_path, f"generation error: {exc}")
        _write_last_frame(last_frame_path)

    return duration_sec, wav_path, video_path, last_frame_path
