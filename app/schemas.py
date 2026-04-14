from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


TemplateType = Literal["A", "B", "C", "D", "E", "F"]
LogoPosition = Literal["top-left", "top-right", "bottom-left", "bottom-right"]


class ProjectCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    script: str = Field(min_length=1)
    template: TemplateType = "A"
    background: str = "kt_studio"
    outfit: str = "white_mockneck"
    hair: str = "long_s_wave_6_4"
    logo_position: LogoPosition = "top-right"
    logo_scale: int = Field(default=12, ge=5, le=30)
    subtitle_font: str = "Pretendard"
    target_scene_sec: int = Field(default=8, ge=5, le=10)


class ProjectSettingsUpdateRequest(BaseModel):
    template: TemplateType | None = None
    background: str | None = None
    outfit: str | None = None
    hair: str | None = None
    logo_position: LogoPosition | None = None
    logo_scale: int | None = Field(default=None, ge=5, le=30)
    subtitle_font: str | None = None


class SceneUpdateRequest(BaseModel):
    script: str = Field(min_length=1)


class GenerateSceneRequest(BaseModel):
    pronunciation_dict: dict[str, str] = Field(default_factory=dict)


class ProjectResponse(BaseModel):
    project_id: str
    title: str
    status: str
    template: TemplateType
    background: str
    outfit: str
    hair: str
    logo_position: LogoPosition
    logo_scale: int
    subtitle_font: str
    created_at: str
    updated_at: str
    scenes: list[dict]
    final_video_url: str | None = None
