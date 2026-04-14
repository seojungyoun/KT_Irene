from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    script: str = Field(min_length=1)
    template: Literal["A", "B", "C", "D", "E", "F"] = "A"
    background: str = "studio"
    outfit: str = "white_mockneck"
    hair: str = "long_s_wave_6_4"
    target_scene_sec: int = Field(default=8, ge=5, le=10)


class SceneUpdateRequest(BaseModel):
    script: str = Field(min_length=1)


class GenerateSceneRequest(BaseModel):
    pronunciation_dict: dict[str, str] = Field(default_factory=dict)


class ProjectResponse(BaseModel):
    project_id: str
    title: str
    status: str
    template: str
    created_at: str
    updated_at: str
    scenes: list[dict]
    final_video_url: str | None = None
