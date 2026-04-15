"""
SadTalker 자동 설치 스크립트
==============================
실행: python scripts/setup_sadtalker.py

수행 작업:
  1. SadTalker GitHub 클론
  2. Python 의존성 설치
  3. 사전 학습 모델 다운로드 (HuggingFace)
  4. .env 파일에 SADTALKER_PATH 자동 추가

요구 사항:
  - Python 3.8+
  - git
  - ffmpeg
  - CUDA GPU 권장 (CPU도 동작, 느림)
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SADTALKER_DIR = ROOT / "sadtalker"
ENV_FILE = ROOT / ".env"

REPO_URL = "https://github.com/OpenTalker/SadTalker.git"

# HuggingFace 모델 (인터넷 필요)
HF_CHECKPOINTS = "vinthony/SadTalker"
HF_GFPGAN      = "Xinntao/Real-ESRGAN"   # face enhancer


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> int:
    print(f"\n▶ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=cwd, check=False)
    if check and result.returncode != 0:
        print(f"❌ 실패 (code {result.returncode})")
        sys.exit(result.returncode)
    return result.returncode


def step1_clone():
    print("\n" + "="*50)
    print("1단계: SadTalker 클론")
    print("="*50)
    if SADTALKER_DIR.exists():
        print(f"✅ 이미 존재: {SADTALKER_DIR}")
        return
    run(["git", "clone", "--depth=1", REPO_URL, str(SADTALKER_DIR)])
    print(f"✅ 클론 완료: {SADTALKER_DIR}")


def step2_install_deps():
    print("\n" + "="*50)
    print("2단계: Python 의존성 설치")
    print("="*50)
    req = SADTALKER_DIR / "requirements.txt"
    if not req.exists():
        print("❌ requirements.txt 없음")
        sys.exit(1)

    run([sys.executable, "-m", "pip", "install", "-r", str(req)])

    # GFPGAN (얼굴 화질 향상) 추가 설치
    run([sys.executable, "-m", "pip", "install", "gfpgan"], check=False)
    print("✅ 의존성 설치 완료")


def step3_download_models():
    print("\n" + "="*50)
    print("3단계: 사전 학습 모델 다운로드 (HuggingFace)")
    print("="*50)

    checkpoints = SADTALKER_DIR / "checkpoints"
    gfpgan_dir  = SADTALKER_DIR / "gfpgan" / "weights"
    checkpoints.mkdir(parents=True, exist_ok=True)
    gfpgan_dir.mkdir(parents=True, exist_ok=True)

    # huggingface_hub으로 모델 다운로드
    try:
        from huggingface_hub import hf_hub_download  # type: ignore
    except ImportError:
        run([sys.executable, "-m", "pip", "install", "huggingface_hub"])
        from huggingface_hub import hf_hub_download  # type: ignore

    # SadTalker 핵심 모델
    models = [
        ("vinthony/SadTalker", "checkpoints/SadTalker_V0.0.2_256.safetensors"),
        ("vinthony/SadTalker", "checkpoints/SadTalker_V0.0.2_512.safetensors"),
        ("vinthony/SadTalker", "checkpoints/mapping_00109-model.pth.tar"),
        ("vinthony/SadTalker", "checkpoints/mapping_00229-model.pth.tar"),
        ("vinthony/SadTalker", "checkpoints/auido2exp_00300-model.pth.tar"),
        ("vinthony/SadTalker", "checkpoints/auido2pose_00140-model.pth.tar"),
        ("vinthony/SadTalker", "checkpoints/facevid2vid_00189-model.pth.tar"),
        ("vinthony/SadTalker", "checkpoints/shape_predictor_68_face_landmarks.dat"),
        ("vinthony/SadTalker", "checkpoints/epoch_20.pth"),
    ]

    for repo, filename in models:
        dest = SADTALKER_DIR / filename
        if dest.exists():
            print(f"✅ 이미 있음: {filename}")
            continue
        print(f"⬇ 다운로드: {filename}")
        try:
            hf_hub_download(
                repo_id=repo,
                filename=filename.split("/")[-1],
                subfolder=filename.rsplit("/", 1)[0] if "/" in filename else None,
                local_dir=str(SADTALKER_DIR),
            )
        except Exception as e:
            print(f"⚠️ 건너뜀 ({e})")

    # BFM 모델 (얼굴 3D 모델)
    bfm_models = [
        ("vinthony/SadTalker", "BFM_Fitting/01_MorphableModel.mat"),
        ("vinthony/SadTalker", "BFM_Fitting/BFM_model_front.mat"),
        ("vinthony/SadTalker", "BFM_Fitting/Exp_Pca.bin"),
        ("vinthony/SadTalker", "BFM_Fitting/facemodel_info.mat"),
        ("vinthony/SadTalker", "BFM_Fitting/select_vertex_id.mat"),
        ("vinthony/SadTalker", "BFM_Fitting/similarity_Lm3D_all.mat"),
        ("vinthony/SadTalker", "BFM_Fitting/std_exp.txt"),
    ]
    for repo, filename in bfm_models:
        dest = SADTALKER_DIR / filename
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"⬇ 다운로드: {filename}")
        try:
            hf_hub_download(
                repo_id=repo,
                filename=filename.split("/")[-1],
                subfolder=filename.rsplit("/", 1)[0],
                local_dir=str(SADTALKER_DIR),
            )
        except Exception as e:
            print(f"⚠️ 건너뜀 ({e})")

    # GFPGAN 얼굴 복원 모델
    gfpgan_models = [
        ("https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth",
         gfpgan_dir / "GFPGANv1.4.pth"),
    ]
    import urllib.request
    for url, dest in gfpgan_models:
        if dest.exists():
            print(f"✅ 이미 있음: {dest.name}")
            continue
        print(f"⬇ 다운로드: {dest.name}")
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as e:
            print(f"⚠️ 건너뜀 ({e})")

    print("✅ 모델 다운로드 완료")


def step4_update_env():
    print("\n" + "="*50)
    print("4단계: .env 파일에 SADTALKER_PATH 추가")
    print("="*50)

    sadtalker_path = str(SADTALKER_DIR).replace("\\", "/")
    line = f'SADTALKER_PATH="{sadtalker_path}"\n'

    if ENV_FILE.exists():
        content = ENV_FILE.read_text(encoding="utf-8")
        if "SADTALKER_PATH" in content:
            # 기존 값 업데이트
            import re
            content = re.sub(r"SADTALKER_PATH=.*\n", line, content)
            ENV_FILE.write_text(content, encoding="utf-8")
            print(f"✅ .env 업데이트: SADTALKER_PATH")
        else:
            with ENV_FILE.open("a", encoding="utf-8") as f:
                f.write(f"\n# SadTalker 로컬 립싱크 (무료)\n{line}")
            print(f"✅ .env에 추가: SADTALKER_PATH")
    else:
        ENV_FILE.write_text(
            f"# KT Irene Studio 환경변수\n\n# SadTalker 로컬 립싱크 (무료)\n{line}",
            encoding="utf-8",
        )
        print(f"✅ .env 생성")

    print(f"   경로: {sadtalker_path}")


def main():
    print("=" * 50)
    print("  SadTalker 설치 시작")
    print("  무료 로컬 립싱크 영상 생성 엔진")
    print("=" * 50)

    step1_clone()
    step2_install_deps()
    step3_download_models()
    step4_update_env()

    print("\n" + "=" * 50)
    print("✅ SadTalker 설치 완료!")
    print("=" * 50)
    print(f"\n설치 경로: {SADTALKER_DIR}")
    print("\n다음 단계:")
    print("  1. 서버를 재시작하세요: uvicorn app.main:app --reload")
    print("  2. 상단 툴바에서 '🎙 SadTalker (로컬)' 확인")
    print("  3. 씬 생성 시 자동으로 립싱크 영상이 만들어집니다")
    print("\n⚠️  GPU(CUDA)가 없으면 CPU로 동작 — 씬당 5~15분 소요")
    print("⚠️  GPU가 있으면 씬당 약 30초~2분 소요")


if __name__ == "__main__":
    main()
