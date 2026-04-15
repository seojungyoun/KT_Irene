"""KT Irene Studio — FastAPI 메인 애플리케이션

개선사항:
  - 비동기 백그라운드 생성 (generate-all이 UI를 블록하지 않음)
  - /api/projects/{id}/progress  — 생성 진행 상황 폴링
  - /api/projects               — 전체 프로젝트 목록
  - /api/projects/{id}/upload-irene — 아이린 레퍼런스 이미지 업로드
  - render-final에 씬 대본 전달 (템플릿 타이틀 패널용)
  - logo_position / outfit / hair 를 씬 생성에 전달
"""
from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
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
from .services.video import generate_scene_video, IRENE_REF_PATH, ASSETS_DIR, KT_LOGO_PATH
from .services.ai_video import ai_video_status

BASE_DIR   = Path(__file__).resolve().parent.parent
DATA_DIR   = BASE_DIR / "data" / "projects"
DATA_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# 커스텀 배경 저장 경로
BG_UPLOAD_DIR = ASSETS_DIR / "backgrounds"
BG_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 허용 이미지/영상 확장자
_IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}
_VID_EXT = {".mp4", ".mov", ".webm", ".avi"}

PROJECTS: dict[str, Project] = {}

# 백그라운드 잡 상태 추적 { project_id: { "total": n, "done": n, "error": str|None } }
JOBS: dict[str, dict[str, Any]] = {}

APP_BUILD = "2026.04.14-3"

app = FastAPI(title="KT Irene Studio", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
app.mount("/data",   StaticFiles(directory=BASE_DIR / "data"),           name="data")


@app.middleware("http")
async def no_cache_ui(request, call_next):
    response = await call_next(request)
    if request.url.path in ("/", ) or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"]        = "no-cache"
        response.headers["Expires"]       = "0"
    return response


# ── 헬스 ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "build": APP_BUILD}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(BASE_DIR / "app" / "static" / "index.html")


# ── 내부 헬퍼 ───────────────────────────────────────────────────────────────
def _save_project(project: Project) -> None:
    d = DATA_DIR / project.project_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "project.json").write_text(
        json.dumps(project.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _get_project(project_id: str) -> Project:
    p = PROJECTS.get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


def _get_scene(project: Project, scene_id: str) -> Scene:
    for s in project.scenes:
        if s.scene_id == scene_id:
            return s
    raise HTTPException(status_code=404, detail="Scene not found")


def _resolve(rel: str | None) -> Path | None:
    return (BASE_DIR / rel) if rel else None


def _build_scenes(script: str, target_sec: int) -> list[Scene]:
    limit  = recommended_limit_by_seconds(target_sec)
    chunks = split_script(script, max_chars=limit)
    return [
        Scene(scene_id=str(uuid.uuid4()), order_index=i,
              script_text=chunk, recommended_char_limit=limit)
        for i, chunk in enumerate(chunks)
    ]


def _generate_scene_internal(project: Project, scene: Scene,
                              pronunciation_dict: dict[str, str]) -> None:
    project_dir = DATA_DIR / project.project_id

    prev_last_frame: Path | None = None
    if scene.order_index > 0:
        prev = project.scenes[scene.order_index - 1]
        if prev.last_frame_path:
            prev_last_frame = BASE_DIR / prev.last_frame_path

    scene_dir = project_dir / f"scene_{scene.order_index:03d}_v{scene.version}"
    dur, wav, sub, vid, lf = generate_scene_video(
        scene_script=scene.script_text,
        scene_dir=scene_dir,
        pronunciation_dict=pronunciation_dict,
        init_frame_path=prev_last_frame,
        background=project.background,
        logo_position=project.logo_position,
        outfit=project.outfit,
        hair=project.hair,
    )

    pid, sid = project.project_id, scene.scene_id
    scene.pronunciation_dict = pronunciation_dict
    scene.duration_sec       = dur
    scene.tts_audio_path     = str(wav.relative_to(BASE_DIR))
    scene.subtitle_path      = str(sub.relative_to(BASE_DIR))
    scene.video_path         = str(vid.relative_to(BASE_DIR))
    scene.last_frame_path    = str(lf.relative_to(BASE_DIR))
    scene.tts_audio_url      = f"/api/projects/{pid}/scenes/{sid}/audio"
    scene.subtitle_url       = f"/api/projects/{pid}/scenes/{sid}/subtitle"
    scene.video_url          = f"/api/projects/{pid}/scenes/{sid}/video"
    scene.last_frame_url     = f"/api/projects/{pid}/scenes/{sid}/last-frame"
    scene.status             = "generated"


# ══════════════════════════════════════════════════════════════════════════════
# 프로젝트 엔드포인트
# ══════════════════════════════════════════════════════════════════════════════
@app.get("/api/projects")
def list_projects():
    """전체 프로젝트 목록 반환 (최신순)."""
    items = sorted(PROJECTS.values(), key=lambda p: p.updated_at, reverse=True)
    return [
        {
            "project_id": p.project_id,
            "title":      p.title,
            "status":     p.status,
            "template":   p.template,
            "scenes":     len(p.scenes),
            "updated_at": p.updated_at,
        }
        for p in items
    ]


@app.post("/api/projects", response_model=ProjectResponse)
def create_project(req: ProjectCreateRequest):
    pid    = str(uuid.uuid4())
    scenes = _build_scenes(req.script, req.target_scene_sec)
    project = Project(
        project_id=pid, title=req.title, script=req.script,
        template=req.template, background=req.background,
        outfit=req.outfit, hair=req.hair,
        logo_position=req.logo_position, logo_scale=req.logo_scale,
        subtitle_font=req.subtitle_font, target_scene_sec=req.target_scene_sec,
        scenes=scenes,
    )
    PROJECTS[pid] = project
    _save_project(project)
    return ProjectResponse(**project.to_dict())


@app.get("/api/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str):
    return ProjectResponse(**_get_project(project_id).to_dict())


@app.patch("/api/projects/{project_id}/settings", response_model=ProjectResponse)
def update_settings(project_id: str, req: ProjectSettingsUpdateRequest):
    project = _get_project(project_id)
    for k, v in req.model_dump(exclude_none=True).items():
        setattr(project, k, v)
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


# ── 씬 편집 ─────────────────────────────────────────────────────────────────
@app.patch("/api/projects/{project_id}/scenes/{scene_id}", response_model=ProjectResponse)
def update_scene(project_id: str, scene_id: str, req: SceneUpdateRequest):
    project = _get_project(project_id)
    scene   = _get_scene(project, scene_id)
    scene.script_text = req.script
    scene.version    += 1
    scene.status      = "draft"
    project.touch()
    _save_project(project)
    return ProjectResponse(**project.to_dict())


# ── 씬 생성 (동기) ───────────────────────────────────────────────────────────
@app.post("/api/projects/{project_id}/scenes/{scene_id}/generate",
          response_model=ProjectResponse)
def generate_scene(project_id: str, scene_id: str, req: GenerateSceneRequest):
    project = _get_project(project_id)
    scene   = _get_scene(project, scene_id)
    _generate_scene_internal(project, scene, req.pronunciation_dict)
    project.status = "generating"
    project.touch()
    _save_project(project)
    return ProjectResponse(**project.to_dict())


# ── 전체 생성 (비동기 백그라운드) ─────────────────────────────────────────────
def _generate_all_worker(project_id: str) -> None:
    """백그라운드 스레드에서 실행 — 씬 순서대로 생성 후 최종 렌더."""
    project = PROJECTS.get(project_id)
    if not project:
        return

    scenes  = sorted(project.scenes, key=lambda s: s.order_index)
    total   = len(scenes)
    JOBS[project_id] = {"total": total, "done": 0, "error": None}

    try:
        for scene in scenes:
            _generate_scene_internal(project, scene, scene.pronunciation_dict)
            project.touch()
            _save_project(project)
            JOBS[project_id]["done"] += 1

        # 최종 렌더
        scene_paths   = [BASE_DIR / s.video_path for s in project.scenes if s.video_path]
        scene_scripts = [s.script_text for s in project.scenes if s.video_path]
        out = render_final_video(
            DATA_DIR / project_id,
            scene_paths,
            template=project.template,
            scene_scripts=scene_scripts,
        )
        project.final_video_path = str(out.relative_to(BASE_DIR))
        project.final_video_url  = f"/api/projects/{project_id}/final-video"
        project.status           = "rendered"
        project.updated_at       = utc_now_iso()
        _save_project(project)
        JOBS[project_id]["done"] = total + 1   # +1 = 렌더 완료

    except Exception as exc:
        JOBS[project_id]["error"] = str(exc)
        project.status = "error"
        _save_project(project)


@app.post("/api/projects/{project_id}/generate-all")
def generate_all(project_id: str):
    project = _get_project(project_id)
    if JOBS.get(project_id, {}).get("done", -1) >= 0 and \
       JOBS[project_id].get("done", 0) < JOBS[project_id].get("total", 0) + 1:
        return JSONResponse({"message": "이미 생성 중입니다."}, status_code=409)

    project.status = "generating"
    project.touch()
    _save_project(project)

    t = threading.Thread(target=_generate_all_worker, args=(project_id,), daemon=True)
    t.start()
    return {"message": "생성 시작", "project_id": project_id}


@app.get("/api/projects/{project_id}/progress")
def get_progress(project_id: str):
    """전체 생성 진행 상황 폴링 엔드포인트."""
    _get_project(project_id)   # 404 체크
    job   = JOBS.get(project_id, {})
    total = job.get("total", 0)
    done  = job.get("done",  0)
    pct   = int(done / (total + 1) * 100) if total > 0 else 0
    return {
        "total":   total,
        "done":    done,
        "percent": pct,
        "error":   job.get("error"),
        "status":  PROJECTS[project_id].status,
        "final_video_url": PROJECTS[project_id].final_video_url,
    }


# ── 최종 렌더 (동기) ─────────────────────────────────────────────────────────
@app.post("/api/projects/{project_id}/render-final", response_model=ProjectResponse)
def render_final(project_id: str):
    project = _get_project(project_id)
    paths   = [BASE_DIR / s.video_path for s in sorted(project.scenes, key=lambda s: s.order_index)
               if s.video_path]
    scripts = [s.script_text for s in sorted(project.scenes, key=lambda s: s.order_index)
               if s.video_path]
    out = render_final_video(
        DATA_DIR / project_id, paths,
        template=project.template, scene_scripts=scripts,
    )
    project.final_video_path = str(out.relative_to(BASE_DIR))
    project.final_video_url  = f"/api/projects/{project_id}/final-video"
    project.status           = "rendered"
    project.updated_at       = utc_now_iso()
    _save_project(project)
    return ProjectResponse(**project.to_dict())


# ══════════════════════════════════════════════════════════════════════════════
# 에셋 관리 API
# ══════════════════════════════════════════════════════════════════════════════

def _check_image(file: UploadFile) -> None:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="이미지 파일(PNG/JPG)만 업로드 가능합니다.")

def _check_media(file: UploadFile) -> None:
    ct = file.content_type or ""
    if not (ct.startswith("image/") or ct.startswith("video/")):
        raise HTTPException(status_code=400, detail="이미지 또는 동영상 파일만 업로드 가능합니다.")

# ── 아이린 레퍼런스 이미지 ──────────────────────────────────────────────────
@app.post("/api/assets/irene")
async def upload_irene(file: UploadFile = File(...)):
    """아이린 마스터 이미지 등록 (PNG/JPG)."""
    _check_image(file)
    content = await file.read()
    IRENE_REF_PATH.write_bytes(content)
    return {"message": "아이린 이미지가 등록되었습니다.", "size": len(content),
            "url": "/api/assets/irene"}

@app.get("/api/assets/irene")
def get_irene():
    if not IRENE_REF_PATH.exists():
        raise HTTPException(status_code=404, detail="등록된 아이린 이미지가 없습니다.")
    return FileResponse(IRENE_REF_PATH)

# 하위 호환 경로 유지
@app.post("/api/irene/upload-reference")
async def upload_irene_reference(file: UploadFile = File(...)):
    return await upload_irene(file)

@app.get("/api/irene/reference")
def get_irene_reference():
    return get_irene()

# ── KT 로고 ────────────────────────────────────────────────────────────────
@app.post("/api/assets/logo")
async def upload_logo(file: UploadFile = File(...)):
    """KT 로고 이미지 교체 (PNG 권장, 투명 배경)."""
    _check_image(file)
    content = await file.read()
    KT_LOGO_PATH.write_bytes(content)
    # 소형 버전도 갱신
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(content)).convert("RGBA")
        img.thumbnail((150, 112), Image.LANCZOS)
        img.save(str(KT_LOGO_PATH.parent / "kt_logo_sm.png"), "PNG")
    except Exception:
        pass
    return {"message": "KT 로고가 등록되었습니다.", "size": len(content),
            "url": "/api/assets/logo"}

@app.get("/api/assets/logo")
def get_logo():
    if not KT_LOGO_PATH.exists():
        raise HTTPException(status_code=404, detail="등록된 로고가 없습니다.")
    return FileResponse(KT_LOGO_PATH)

# ── 배경 이미지 / 동영상 ─────────────────────────────────────────────────────
@app.post("/api/assets/backgrounds")
async def upload_background(file: UploadFile = File(...)):
    """배경 이미지 또는 동영상 업로드."""
    _check_media(file)
    suffix = Path(file.filename or "bg.png").suffix.lower()
    if suffix not in _IMG_EXT | _VID_EXT:
        raise HTTPException(status_code=400,
                            detail=f"지원 형식: {sorted(_IMG_EXT | _VID_EXT)}")
    safe_name = f"{uuid.uuid4().hex[:8]}{suffix}"
    dest = BG_UPLOAD_DIR / safe_name
    dest.write_bytes(await file.read())

    # 이미지이면 썸네일 생성
    thumb_url = None
    if suffix in _IMG_EXT:
        thumb_path = BG_UPLOAD_DIR / f"{dest.stem}_thumb.jpg"
        try:
            from PIL import Image
            img = Image.open(dest).convert("RGB")
            img.thumbnail((320, 180), Image.LANCZOS)
            img.save(thumb_path, "JPEG", quality=80)
            thumb_url = f"/api/assets/backgrounds/{thumb_path.name}"
        except Exception:
            pass

    return {
        "name": safe_name,
        "original": file.filename,
        "url": f"/api/assets/backgrounds/{safe_name}",
        "thumb_url": thumb_url,
        "type": "video" if suffix in _VID_EXT else "image",
    }

@app.get("/api/assets/backgrounds")
def list_backgrounds():
    """업로드된 배경 파일 목록."""
    items = []
    for f in sorted(BG_UPLOAD_DIR.iterdir()):
        if f.suffix.lower() in _IMG_EXT | _VID_EXT and "_thumb" not in f.stem:
            thumb = BG_UPLOAD_DIR / f"{f.stem}_thumb.jpg"
            items.append({
                "name": f.name,
                "url": f"/api/assets/backgrounds/{f.name}",
                "thumb_url": f"/api/assets/backgrounds/{thumb.name}" if thumb.exists() else None,
                "type": "video" if f.suffix.lower() in _VID_EXT else "image",
                "size": f.stat().st_size,
            })
    return items

@app.get("/api/assets/backgrounds/{filename}")
def get_background_file(filename: str):
    p = BG_UPLOAD_DIR / filename
    if not p.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return FileResponse(p)

@app.delete("/api/assets/backgrounds/{filename}")
def delete_background(filename: str):
    p = BG_UPLOAD_DIR / filename
    if p.exists():
        p.unlink()
    thumb = BG_UPLOAD_DIR / f"{Path(filename).stem}_thumb.jpg"
    if thumb.exists():
        thumb.unlink()
    return {"message": "삭제되었습니다."}

# ── 에셋 전체 상태 ─────────────────────────────────────────────────────────
@app.get("/api/assets/status")
def get_asset_status():
    """등록된 에셋 현황 한 번에 조회."""
    bgs = []
    for f in sorted(BG_UPLOAD_DIR.iterdir()):
        if f.suffix.lower() in _IMG_EXT | _VID_EXT and "_thumb" not in f.stem:
            thumb = BG_UPLOAD_DIR / f"{f.stem}_thumb.jpg"
            bgs.append({
                "name": f.name,
                "url": f"/api/assets/backgrounds/{f.name}",
                "thumb_url": f"/api/assets/backgrounds/{thumb.name}" if thumb.exists() else None,
                "type": "video" if f.suffix.lower() in _VID_EXT else "image",
            })
    return {
        "irene": {"registered": IRENE_REF_PATH.exists(), "url": "/api/assets/irene"},
        "logo":  {"registered": KT_LOGO_PATH.exists(),   "url": "/api/assets/logo"},
        "backgrounds": bgs,
    }


@app.get("/api/ai-video/status")
def get_ai_video_status():
    """현재 설정된 AI 영상 생성 엔진 상태 반환."""
    return ai_video_status()


# ── 파일 다운로드 ────────────────────────────────────────────────────────────
@app.get("/api/projects/{project_id}/scenes/{scene_id}/video")
def get_scene_video(project_id: str, scene_id: str):
    scene = _get_scene(_get_project(project_id), scene_id)
    p = _resolve(scene.video_path)
    if not p or not p.exists():
        raise HTTPException(status_code=404, detail="씬 영상 없음")
    return FileResponse(p, media_type="video/mp4")


@app.get("/api/projects/{project_id}/scenes/{scene_id}/audio")
def get_scene_audio(project_id: str, scene_id: str):
    scene = _get_scene(_get_project(project_id), scene_id)
    p = _resolve(scene.tts_audio_path)
    if not p or not p.exists():
        raise HTTPException(status_code=404, detail="씬 오디오 없음")
    return FileResponse(p, media_type="audio/wav")


@app.get("/api/projects/{project_id}/scenes/{scene_id}/subtitle")
def get_scene_subtitle(project_id: str, scene_id: str):
    scene = _get_scene(_get_project(project_id), scene_id)
    p = _resolve(scene.subtitle_path)
    if not p or not p.exists():
        raise HTTPException(status_code=404, detail="자막 없음")
    return FileResponse(p, media_type="text/plain; charset=utf-8")


@app.get("/api/projects/{project_id}/scenes/{scene_id}/last-frame")
def get_last_frame(project_id: str, scene_id: str):
    scene = _get_scene(_get_project(project_id), scene_id)
    p = _resolve(scene.last_frame_path)
    if not p or not p.exists():
        raise HTTPException(status_code=404, detail="마지막 프레임 없음")
    return FileResponse(p)


@app.get("/api/projects/{project_id}/final-video")
def get_final_video(project_id: str):
    project = _get_project(project_id)
    p = _resolve(project.final_video_path)
    if not p or not p.exists():
        raise HTTPException(status_code=404, detail="최종 영상 없음")
    return FileResponse(p, media_type="video/mp4",
                        headers={"Content-Disposition": f'attachment; filename="{project.title}_final.mp4"'})
