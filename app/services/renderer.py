from __future__ import annotations

from pathlib import Path


def render_final_video(project_dir: Path, scene_video_paths: list[Path]) -> Path:
    output = project_dir / "final.mp4"

    valid_scene_paths = [path for path in scene_video_paths if path.exists()]
    if not valid_scene_paths:
        output.write_text("No scene videos were generated.", encoding="utf-8")
        return output

    try:
        from moviepy import VideoFileClip, concatenate_videoclips

        clips = [VideoFileClip(str(path)) for path in valid_scene_paths]
        final = concatenate_videoclips(clips, method="compose")
        final.write_videofile(str(output), fps=24, codec="libx264", audio_codec="aac", logger=None)
        for clip in clips:
            clip.close()
        final.close()
    except Exception as exc:
        output.write_text(
            "Final render placeholder\n"
            f"moviepy concat failed: {exc}\n"
            f"scenes: {[str(p.name) for p in valid_scene_paths]}\n",
            encoding="utf-8",
        )

    return output
