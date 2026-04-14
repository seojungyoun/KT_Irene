from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import Project, Scene, utc_now_iso
from .schemas import GenerateSceneRequest, ProjectCreateRequest, ProjectResponse, SceneUpdateRequest
from .services.renderer import render_final_video
from .services.scene_splitter import recommended_limit_by_seconds, split_script
from .services.video import generate_scene_video

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "projects"
DATA_DIR.mkdir(parents=True, exist_ok=True)

PROJECTS: dict[str, Project] = {}

app = FastAPI(title="KT Irene Studio", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")


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


@app.post("/api/projects", response_model=ProjectResponse)
def create_project(req: ProjectCreateRequest):
    project_id = str(uuid.uuid4())
    max_chars = recommended_limit_by_seconds(req.target_scene_sec)
    chunks = split_script(req.script, max_chars=max_chars)

    scenes = [
        Scene(
            scene_id=str(uuid.uuid4()),
            order_index=i,
            script_text=chunk,
            recommended_char_limit=max_chars,
        )
        for i, chunk in enumerate(chunks)
    ]

    project = Project(
        project_id=project_id,
        title=req.title,
        script=req.script,
        template=req.template,
        background=req.background,
        outfit=req.outfit,
        hair=req.hair,
        target_scene_sec=req.target_scene_sec,
        scenes=scenes,
    )
    PROJECTS[project_id] = project
    _save_project(project)
    return ProjectResponse(**project.to_dict())


@app.post("/api/projects/{project_id}/split-scenes", response_model=ProjectResponse)
def resplit_scenes(project_id: str):
    project = _get_project(project_id)
    max_chars = recommended_limit_by_seconds(project.target_scene_sec)
    chunks = split_script(project.script, max_chars=max_chars)
    project.scenes = [
        Scene(
            scene_id=str(uuid.uuid4()),
            order_index=i,
            script_text=chunk,
            recommended_char_limit=max_chars,
        )
        for i, chunk in enumerate(chunks)
    ]
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


@app.post("/api/projects/{project_id}/scenes/{scene_id}/generate", response_model=ProjectResponse)
def generate_scene(project_id: str, scene_id: str, req: GenerateSceneRequest):
    project = _get_project(project_id)
    project_dir = DATA_DIR / project_id

    for scene in project.scenes:
        if scene.scene_id == scene_id:
            prev_last_frame = None
            if scene.order_index > 0:
                prev_scene = project.scenes[scene.order_index - 1]
                if prev_scene.last_frame_url:
                    prev_last_frame = BASE_DIR / prev_scene.last_frame_url.lstrip("/")

            scene_dir = project_dir / f"scene_{scene.order_index:03d}_v{scene.version}"
            duration, wav_path, video_path, last_frame = generate_scene_video(
                scene_script=scene.script_text,
                scene_dir=scene_dir,
                pronunciation_dict=req.pronunciation_dict,
                init_frame_path=prev_last_frame,
            )
            scene.duration_sec = duration
            scene.tts_audio_url = "/" + str(wav_path.relative_to(BASE_DIR))
            scene.video_url = "/" + str(video_path.relative_to(BASE_DIR))
            scene.last_frame_url = "/" + str(last_frame.relative_to(BASE_DIR))
            scene.status = "generated"
            project.status = "generating"
            project.touch()
            _save_project(project)
            return ProjectResponse(**project.to_dict())

    raise HTTPException(status_code=404, detail="Scene not found")


@app.post("/api/projects/{project_id}/render-final", response_model=ProjectResponse)
def render_final(project_id: str):
    project = _get_project(project_id)
    project_dir = DATA_DIR / project_id
    scene_video_paths = []
    for scene in sorted(project.scenes, key=lambda s: s.order_index):
        if scene.video_url:
            scene_video_paths.append(BASE_DIR / scene.video_url.lstrip("/"))

    output_path = render_final_video(project_dir, scene_video_paths)
    project.final_video_url = "/" + str(output_path.relative_to(BASE_DIR))
    project.status = "rendered"
    project.updated_at = utc_now_iso()
    _save_project(project)
    return ProjectResponse(**project.to_dict())


@app.get("/api/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str):
    project = _get_project(project_id)
    return ProjectResponse(**project.to_dict())
