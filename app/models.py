from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Scene:
    scene_id: str
    order_index: int
    script_text: str
    recommended_char_limit: int
    duration_sec: float = 0.0
    version: int = 1
    status: str = "draft"
    tts_audio_url: str | None = None
    video_url: str | None = None
    last_frame_url: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Project:
    project_id: str
    title: str
    script: str
    template: str
    background: str
    outfit: str
    hair: str
    target_scene_sec: int
    status: str = "draft"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    scenes: list[Scene] = field(default_factory=list)
    final_video_url: str | None = None

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["scenes"] = [scene.to_dict() for scene in self.scenes]
        return payload
