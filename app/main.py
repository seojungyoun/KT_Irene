from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import Project, Scene, utc_now_iso
from .schemas import (
    GenerateSceneRequest,
    ProjectCreateRequest,
    ProjectResponse,
    ProjectSettingsUpdateRequest,
    SceneUpdateRequest,
)
from .services.renderer import render_final_video
from .services.scene_splitter import recommended_limit_by_seconds, split_script
from .services.video import generate_scene_video

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "projects"
DATA_DIR.mkdir(parents=True, exist_ok=True)

PROJECTS: dict[str, Project] = {}
APP_BUILD = "2026.04.14-2"

app = FastAPI(title="KT Irene Studio", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
app.mount("/data", StaticFiles(directory=BASE_DIR / "data"), name="data")


@app.middleware("http")
async def disable_cache_for_ui(request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.get("/health")
def health():
    return {"status": "ok", "build": APP_BUILD}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "app" / "static" / "index.html")


def _save_project(project: Project) -> None:
    project_dir = DATA_DIR / project.project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "project.json").write_text(
        json.dumps(project.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _get_project(project_id: str) -> Project:
    project = PROJECTS.get(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _resolve_rel_path(rel_path: str | None) -> Path | None:
    if not rel_path:
        return None
    return BASE_DIR / rel_path


def _build_scenes(script: str, target_scene_sec: int) -> list[Scene]:
    max_chars = recommended_limit_by_seconds(target_scene_sec)
    chunks = split_script(script, max_chars=max_chars)
    return [
        Scene(
            scene_id=str(uuid.uuid4()),
            order_index=i,
            script_text=chunk,
            recommended_char_limit=max_chars,
        )
        for i, chunk in enumerate(chunks)
    ]


@app.post("/api/projects", response_model=ProjectResponse)
def create_project(req: ProjectCreateRequest):
    project_id = str(uuid.uuid4())
    scenes = _build_scenes(req.script, req.target_scene_sec)

    project = Project(
        project_id=project_id,
        title=req.title,
        script=req.script,
        template=req.template,
        background=req.background,
        outfit=req.outfit,
        hair=req.hair,
        logo_position=req.logo_position,
        logo_scale=req.logo_scale,
        subtitle_font=req.subtitle_font,
        target_scene_sec=req.target_scene_sec,
        scenes=scenes,
    )
    PROJECTS[project_id] = project
    _save_project(project)
    return ProjectResponse(**project.to_dict())


@app.patch("/api/projects/{project_id}/settings", response_model=ProjectResponse)
def update_project_settings(project_id: str, req: ProjectSettingsUpdateRequest):
    project = _get_project(project_id)
    updates = req.model_dump(exclude_none=True)
    for key, value in updates.items():
        setattr(project, key, value)
    project.touch()
    _save_project(project)
    return ProjectResponse(**project.to_dict())


@app.post("/api/projects/{project_id}/split-scenes", response_model=ProjectResponse)
def resplit_scenes(project_id: str):
    project = _get_project(project_id)
    project.scenes = _build_scenes(project.script, project.target_scene_sec)
    project.status = "draft"
    project.touch()
    _save_project(project)
    return ProjectResponse(**project.to_dict())


@app.patch("/api/projects/{project_id}/scenes/{scene_id}", response_model=ProjectResponse)
def update_scene_script(project_id: str, scene_id: str, req: SceneUpdateRequest):
    project = _get_project(project_id)
    for scene in project.scenes:
        if scene.scene_id == scene_id:
            scene.script_text = req.script
            scene.version += 1
            scene.status = "draft"
            project.touch()
            _save_project(project)
            return ProjectResponse(**project.to_dict())
    raise HTTPException(status_code=404, detail="Scene not found")


def _generate_scene_internal(project: Project, scene: Scene, pronunciation_dict: dict[str, str]) -> None:
    project_dir = DATA_DIR / project.project_id

    prev_last_frame = None
    if scene.order_index > 0:
        prev_scene = project.scenes[scene.order_index - 1]
        if prev_scene.last_frame_url:
            prev_last_frame = BASE_DIR / prev_scene.last_frame_url.lstrip("/")

    scene_dir = project_dir / f"scene_{scene.order_index:03d}_v{scene.version}"
    duration, wav_path, subtitle_path, video_path, last_frame = generate_scene_video(
        scene_script=scene.script_text,
        scene_dir=scene_dir,
        pronunciation_dict=pronunciation_dict,
        init_frame_path=prev_last_frame,
        background=project.background,
    )
    scene.pronunciation_dict = pronunciation_dict
    scene.duration_sec = duration
    scene.tts_audio_path = str(wav_path.relative_to(BASE_DIR))
    scene.subtitle_path = str(subtitle_path.relative_to(BASE_DIR))
    scene.video_path = str(video_path.relative_to(BASE_DIR))
    scene.last_frame_path = str(last_frame.relative_to(BASE_DIR))
    scene.tts_audio_url = f"/api/projects/{project.project_id}/scenes/{scene.scene_id}/audio"
    scene.subtitle_url = f"/api/projects/{project.project_id}/scenes/{scene.scene_id}/subtitle"
    scene.video_url = f"/api/projects/{project.project_id}/scenes/{scene.scene_id}/video"
    scene.last_frame_url = f"/api/projects/{project.project_id}/scenes/{scene.scene_id}/last-frame"
    scene.status = "generated"


@app.post("/api/projects/{project_id}/scenes/{scene_id}/generate", response_model=ProjectResponse)
def generate_scene(project_id: str, scene_id: str, req: GenerateSceneRequest):
    project = _get_project(project_id)

    for scene in project.scenes:
        if scene.scene_id == scene_id:
            _generate_scene_internal(project, scene, req.pronunciation_dict)
            project.status = "generating"
            project.touch()
            _save_project(project)
            return ProjectResponse(**project.to_dict())

    raise HTTPException(status_code=404, detail="Scene not found")


@app.post("/api/projects/{project_id}/generate-all", response_model=ProjectResponse)
def generate_all(project_id: str):
    project = _get_project(project_id)
    for scene in sorted(project.scenes, key=lambda x: x.order_index):
        _generate_scene_internal(project, scene, scene.pronunciation_dict)

    scene_video_paths = [BASE_DIR / s.video_path for s in project.scenes if s.video_path]
    output_path = render_final_video(
        DATA_DIR / project.project_id,
        scene_video_paths,
        template=project.template,
    )
    project.final_video_path = str(output_path.relative_to(BASE_DIR))
    project.final_video_url = f"/api/projects/{project.project_id}/final-video"
    project.status = "rendered"
    project.updated_at = utc_now_iso()
    _save_project(project)
    return ProjectResponse(**project.to_dict())


@app.post("/api/projects/{project_id}/render-final", response_model=ProjectResponse)
def render_final(project_id: str):
    project = _get_project(project_id)
    scene_video_paths = []
    for scene in sorted(project.scenes, key=lambda s: s.order_index):
        if scene.video_url:
            if scene.video_path:
                scene_video_paths.append(BASE_DIR / scene.video_path)

    output_path = render_final_video(
        DATA_DIR / project.project_id,
        scene_video_paths,
        template=project.template,
    )
    project.final_video_path = str(output_path.relative_to(BASE_DIR))
    project.final_video_url = f"/api/projects/{project.project_id}/final-video"
    project.status = "rendered"
    project.updated_at = utc_now_iso()
    _save_project(project)
    return ProjectResponse(**project.to_dict())


@app.get("/api/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str):
    project = _get_project(project_id)
    return ProjectResponse(**project.to_dict())


def _get_scene(project: Project, scene_id: str) -> Scene:
    for scene in project.scenes:
        if scene.scene_id == scene_id:
            return scene
    raise HTTPException(status_code=404, detail="Scene not found")


@app.get("/api/projects/{project_id}/scenes/{scene_id}/video")
def get_scene_video(project_id: str, scene_id: str):
    project = _get_project(project_id)
    scene = _get_scene(project, scene_id)
    path = _resolve_rel_path(scene.video_path)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Scene video not found")
    return FileResponse(path)


@app.get("/api/projects/{project_id}/scenes/{scene_id}/audio")
def get_scene_audio(project_id: str, scene_id: str):
    project = _get_project(project_id)
    scene = _get_scene(project, scene_id)
    path = _resolve_rel_path(scene.tts_audio_path)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Scene audio not found")
    return FileResponse(path, media_type="audio/wav")


@app.get("/api/projects/{project_id}/scenes/{scene_id}/subtitle")
def get_scene_subtitle(project_id: str, scene_id: str):
    project = _get_project(project_id)
    scene = _get_scene(project, scene_id)
    path = _resolve_rel_path(scene.subtitle_path)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Scene subtitle not found")
    return FileResponse(path, media_type="text/plain")


@app.get("/api/projects/{project_id}/scenes/{scene_id}/last-frame")
def get_scene_last_frame(project_id: str, scene_id: str):
    project = _get_project(project_id)
    scene = _get_scene(project, scene_id)
    path = _resolve_rel_path(scene.last_frame_path)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Scene last frame not found")
    return FileResponse(path)


@app.get("/api/projects/{project_id}/final-video")
def get_final_video(project_id: str):
    project = _get_project(project_id)
    path = _resolve_rel_path(project.final_video_path)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Final video not found")
    return FileResponse(path)
