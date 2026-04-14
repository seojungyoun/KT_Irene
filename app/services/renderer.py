from __future__ import annotations

from pathlib import Path

TEMPLATE_LABEL = {
    "A": "6:4 Split",
    "B": "PIP",
    "C": "Anchor Full",
    "D": "Side Panel",
    "E": "Ticker",
    "F": "Dual Box",
}


def render_final_video(
    project_dir: Path,
    scene_video_paths: list[Path],
    template: str,
    transition_sec: float = 0.35,
) -> Path:
    output = project_dir / "final.mp4"

    valid_scene_paths = [path for path in scene_video_paths if path.exists()]
    if not valid_scene_paths:
        output.write_text("No scene videos were generated.", encoding="utf-8")
        return output

    try:
        from moviepy import VideoFileClip, concatenate_videoclips

        clips = [VideoFileClip(str(path)) for path in valid_scene_paths]
        if len(clips) > 1:
            transitioned = [clips[0]]
            for c in clips[1:]:
                transitioned.append(c.with_start(transitioned[-1].end - transition_sec).crossfadein(transition_sec))
            final = concatenate_videoclips(transitioned, method="compose", padding=-transition_sec)
        else:
            final = clips[0]

        final.write_videofile(str(output), fps=24, codec="libx264", audio_codec="aac", logger=None)
        for clip in clips:
            clip.close()
        final.close()
    except Exception as exc:
        output.write_text(
            "Final render placeholder\n"
            f"template: {TEMPLATE_LABEL.get(template, template)}\n"
            f"moviepy concat failed: {exc}\n"
            f"scenes: {[str(p.name) for p in valid_scene_paths]}\n",
            encoding="utf-8",
        )

    return output
