"""
SadTalker 자동 설치 스크립트 (Windows 호환)
=============================================
실행: python scripts/setup_sadtalker.py

수행 작업:
  1. SadTalker GitHub 클론
  2. Python 의존성 설치 (Windows 빌드 오류 패키지 개별 처리)
  3. 사전 학습 모델 다운로드 (HuggingFace)
  4. .env 파일에 SADTALKER_PATH 자동 추가
"""
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT         = Path(__file__).resolve().parent.parent
SADTALKER_DIR = ROOT / "sadtalker"
ENV_FILE     = ROOT / ".env"
REPO_URL     = "https://github.com/OpenTalker/SadTalker.git"

PY = sys.executable


def pip(*args, check=True):
    """pip 명령 실행."""
    cmd = [PY, "-m", "pip", "install", "--quiet", *args]
    print(f"  pip install {' '.join(args)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ⚠️  오류:\n{r.stderr[-500:]}")
        if check:
            sys.exit(r.returncode)
        return False
    return True


def run(cmd, cwd=None, check=True):
    print(f"\n▶ {' '.join(str(c) for c in cmd)}")
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-800:])
        if check:
            sys.exit(r.returncode)
    return r.returncode == 0


# ─────────────────────────────────────────────────────────────────────────────
def step1_clone():
    print("\n" + "="*55)
    print("1단계: SadTalker 클론")
    print("="*55)
    if (SADTALKER_DIR / "inference.py").exists():
        print(f"✅ 이미 존재: {SADTALKER_DIR}")
        return
    run(["git", "clone", "--depth=1", REPO_URL, str(SADTALKER_DIR)])
    print(f"✅ 클론 완료")


def step2_install_deps():
    print("\n" + "="*55)
    print("2단계: Python 의존성 설치")
    print("="*55)

    # ① cmake (dlib 빌드에 필수)
    print("\n[1/6] cmake 설치...")
    pip("cmake")

    # ② torch — CUDA 있으면 GPU 버전, 없으면 CPU
    print("\n[2/6] PyTorch 설치...")
    try:
        import torch  # type: ignore
        print(f"  ✅ 이미 설치됨 (CUDA: {torch.cuda.is_available()})")
    except ImportError:
        has_cuda = _detect_cuda()
        if has_cuda:
            print(f"  CUDA {has_cuda} 감지 → GPU 버전 설치")
            cuda_tag = "cu121" if has_cuda >= "12" else "cu118"
            pip(
                "torch", "torchvision",
                "--index-url", f"https://download.pytorch.org/whl/{cuda_tag}",
            )
        else:
            print("  CUDA 없음 → CPU 버전 설치 (생성 느림)")
            pip("torch", "torchvision", "--index-url",
                "https://download.pytorch.org/whl/cpu")

    # ③ dlib (cmake 필요; 빌드 실패 시 conda로 안내)
    print("\n[3/6] dlib 설치...")
    try:
        import dlib  # type: ignore
        print("  ✅ 이미 설치됨")
    except ImportError:
        ok = pip("dlib", check=False)
        if not ok:
            print("\n  ❌ dlib 빌드 실패 — Visual Studio Build Tools 필요")
            print("  해결 방법 (하나 선택):")
            print("  A) https://visualstudio.microsoft.com/visual-cpp-build-tools/")
            print("     → 'Desktop development with C++' 설치 후 다시 실행")
            print("  B) Conda 사용:")
            print("     conda install -c conda-forge dlib")
            print("     conda run python scripts/setup_sadtalker.py")
            sys.exit(1)

    # ④ face-alignment, basicsr 등 핵심 패키지
    print("\n[4/6] face-alignment, basicsr 설치...")
    pip("face-alignment==1.3.5", check=False) or pip("face-alignment", check=False)
    pip("basicsr", check=False)
    pip("facexlib", check=False)

    # ⑤ 나머지 requirements.txt (실패 허용)
    print("\n[5/6] requirements.txt 나머지 패키지...")
    req = SADTALKER_DIR / "requirements.txt"
    if req.exists():
        lines = req.read_text().splitlines()
        skip = {"torch", "torchvision", "dlib", "face-alignment", "basicsr", "facexlib"}
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            pkg = re.split(r"[>=<!=]", line)[0].lower().replace("-", "_")
            if any(s in pkg for s in skip):
                continue
            pip(line, check=False)

    # ⑥ GFPGAN (얼굴 화질 향상 — 선택)
    print("\n[6/6] GFPGAN 설치 (선택적)...")
    pip("gfpgan", check=False)
    print("✅ 의존성 설치 완료")


def step3_download_models():
    print("\n" + "="*55)
    print("3단계: 사전 학습 모델 다운로드 (HuggingFace)")
    print("="*55)

    pip("huggingface_hub", check=False)
    try:
        from huggingface_hub import hf_hub_download  # type: ignore
    except ImportError:
        print("❌ huggingface_hub 설치 실패")
        sys.exit(1)

    checkpoints = SADTALKER_DIR / "checkpoints"
    bfm_dir     = SADTALKER_DIR / "checkpoints" / "BFM_Fitting"
    gfpgan_dir  = SADTALKER_DIR / "gfpgan" / "weights"
    for d in [checkpoints, bfm_dir, gfpgan_dir]:
        d.mkdir(parents=True, exist_ok=True)

    def dl(repo, filename, local_dir):
        dest = Path(local_dir) / Path(filename).name
        if dest.exists() and dest.stat().st_size > 1000:
            print(f"  ✅ 이미 있음: {dest.name}")
            return
        print(f"  ⬇ {dest.name} ...")
        try:
            hf_hub_download(
                repo_id=repo,
                filename=filename,
                local_dir=str(local_dir),
                local_dir_use_symlinks=False,
            )
        except Exception as e:
            print(f"  ⚠️  건너뜀: {e}")

    # SadTalker 핵심 체크포인트
    ckpt_files = [
        "SadTalker_V0.0.2_256.safetensors",
        "SadTalker_V0.0.2_512.safetensors",
        "mapping_00109-model.pth.tar",
        "mapping_00229-model.pth.tar",
        "auido2exp_00300-model.pth.tar",
        "auido2pose_00140-model.pth.tar",
        "facevid2vid_00189-model.pth.tar",
        "shape_predictor_68_face_landmarks.dat",
        "epoch_20.pth",
    ]
    print("\n[체크포인트]")
    for f in ckpt_files:
        dl("vinthony/SadTalker", f"checkpoints/{f}", checkpoints)

    # BFM (3D 얼굴 모델)
    bfm_files = [
        "01_MorphableModel.mat",
        "BFM_model_front.mat",
        "Exp_Pca.bin",
        "facemodel_info.mat",
        "select_vertex_id.mat",
        "similarity_Lm3D_all.mat",
        "std_exp.txt",
    ]
    print("\n[BFM 모델]")
    for f in bfm_files:
        dl("vinthony/SadTalker", f"checkpoints/BFM_Fitting/{f}", bfm_dir)

    # GFPGAN 얼굴 복원 가중치
    print("\n[GFPGAN]")
    gfpgan_url = (
        "https://github.com/TencentARC/GFPGAN/releases/download/"
        "v1.3.0/GFPGANv1.4.pth"
    )
    dest = gfpgan_dir / "GFPGANv1.4.pth"
    if dest.exists() and dest.stat().st_size > 100_000:
        print(f"  ✅ 이미 있음: {dest.name}")
    else:
        print(f"  ⬇ GFPGANv1.4.pth ...")
        try:
            urllib.request.urlretrieve(gfpgan_url, dest)
        except Exception as e:
            print(f"  ⚠️  건너뜀: {e}")

    print("\n✅ 모델 다운로드 완료")


def step4_update_env():
    print("\n" + "="*55)
    print("4단계: .env 파일 업데이트")
    print("="*55)

    path_str = str(SADTALKER_DIR).replace("\\", "/")
    new_line  = f'SADTALKER_PATH="{path_str}"'

    if ENV_FILE.exists():
        content = ENV_FILE.read_text(encoding="utf-8")
        if "SADTALKER_PATH" in content:
            content = re.sub(r'SADTALKER_PATH=.*', new_line, content)
        else:
            content += f"\n\n# SadTalker 로컬 립싱크 (무료)\n{new_line}\n"
        ENV_FILE.write_text(content, encoding="utf-8")
    else:
        ENV_FILE.write_text(
            f"# KT Irene Studio\n\n# SadTalker 로컬 립싱크 (무료)\n{new_line}\n",
            encoding="utf-8",
        )
    print(f"✅ SADTALKER_PATH={path_str}")


def _detect_cuda() -> str:
    """CUDA 버전 문자열 반환 (없으면 빈 문자열)."""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            # nvcc로 CUDA 버전 확인
            r2 = subprocess.run(["nvcc", "--version"], capture_output=True, text=True)
            if "release 12" in r2.stdout:
                return "12"
            if "release 11" in r2.stdout:
                return "11"
            return "12"  # 드라이버만 있으면 최신으로 가정
    except FileNotFoundError:
        pass
    return ""


def main():
    print("=" * 55)
    print("  SadTalker 설치 (무료 로컬 립싱크)")
    print("=" * 55)

    step1_clone()
    step2_install_deps()
    step3_download_models()
    step4_update_env()

    print("\n" + "=" * 55)
    print("✅ 설치 완료!")
    print("=" * 55)
    print("\n다음 단계:")
    print("  uvicorn app.main:app --reload --port 8000")
    print("\n  → 상단 '🎙 SadTalker (로컬)' 뱃지 확인 후 씬 생성")
    gpu = _detect_cuda()
    if gpu:
        print("\n  ⚡ GPU 감지됨 — 씬당 약 30초~2분 예상")
    else:
        print("\n  🐢 GPU 없음 — 씬당 약 5~15분 소요 (CPU 모드)")


if __name__ == "__main__":
    main()
