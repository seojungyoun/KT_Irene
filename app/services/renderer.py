"""최종 영상 렌더러

템플릿 A~F:
  A — 6:4 Split   : 앵커 60% 좌 + 자막/타이틀 패널 40% 우
  B — PIP         : 전체 앵커 + 우하단 미니 창
  C — Anchor Full : 앵커 풀스크린 (기본)
  D — Side Panel  : 앵커 50% 우 + 뉴스 패널 50% 좌
  E — Ticker      : 앵커 상단 + 하단 자막 티커 바
  F — Dual Box    : 좌우 동일 박스 (앵커 좌 / 타이틀 우)

흐름:
  1. 각 씬 영상에 템플릿 레이아웃 적용 (ffmpeg filtergraph)
  2. 씬 간 크로스디졸브(0.35s) 전환
  3. 최종 MP4 출력
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

TEMPLATE_LABEL = {
    "A": "6:4 Split",
    "B": "PIP",
    "C": "Anchor Full",
    "D": "Side Panel",
    "E": "Ticker",
    "F": "Dual Box",
}

W, H = 1280, 720           # 출력 해상도
FADE  = 0.35               # 씬 전환 페이드 시간(초)
FPS   = 24

KT_RED = "e6002d"


# ══════════════════════════════════════════════════════════════════════════════
# 템플릿별 ffmpeg filtergraph
# ══════════════════════════════════════════════════════════════════════════════
def _filter_A(title: str) -> str:
    """A: 6:4 — 앵커 좌 768px + 타이틀 패널 우 512px"""
    safe_title = _esc(title[:30])
    return (
        f"[0:v]scale=768:{H},setsar=1[anchor];"
        f"color=c=#111827:s=512x{H}:r={FPS}[panel];"
        f"[panel]drawtext=text='뉴스':fontsize=22:fontcolor=#e6002d:x=30:y=40,"
        f"drawtext=text='{safe_title}':fontsize=28:fontcolor=white:x=30:y=80:line_spacing=10[panel_txt];"
        f"[anchor][panel_txt]hstack=inputs=2[v]"
    )


def _filter_B() -> str:
    """B: PIP — 전체 앵커 + 우하단 미니 창 (앵커 축소본)"""
    pw, ph = 320, 180
    px, py = W - pw - 20, H - ph - 20
    return (
        f"[0:v]scale={W}:{H},setsar=1[full];"
        f"[0:v]scale={pw}:{ph}[pip];"
        f"[full][pip]overlay=x={px}:y={py}[v]"
    )


def _filter_C() -> str:
    """C: Anchor Full — 풀스크린 (패스스루)"""
    return f"[0:v]scale={W}:{H},setsar=1[v]"


def _filter_D(title: str) -> str:
    """D: Side Panel — 뉴스 패널 좌 50% + 앵커 우 50%"""
    safe_title = _esc(title[:30])
    return (
        f"color=c=#0f172a:s=640x{H}:r={FPS}[bg];"
        f"[bg]drawbox=x=0:y=0:w=8:h={H}:color={KT_RED}:t=fill,"
        f"drawtext=text='KT NEWS':fontsize=20:fontcolor=#e6002d:x=30:y=40,"
        f"drawtext=text='{safe_title}':fontsize=26:fontcolor=white:x=30:y=80:line_spacing=8[panel];"
        f"[0:v]scale=640:{H},setsar=1[anchor];"
        f"[panel][anchor]hstack=inputs=2[v]"
    )


def _filter_E(title: str) -> str:
    """E: Ticker — 앵커 상단 660px + 하단 60px 티커"""
    safe_ticker = _esc(title[:60])
    return (
        f"[0:v]scale={W}:660,pad={W}:{H}:0:0:color=#0f172a,setsar=1[anchor];"
        f"color=c=#e6002d:s={W}x60:r={FPS}[ticker_bg];"
        f"[ticker_bg]drawtext=text='■ {safe_ticker}':fontsize=24:fontcolor=white:"
        f"x='mod(200*t\\,{W+len(safe_ticker)*14})':y=18[ticker];"
        f"[anchor][ticker]overlay=x=0:y=660[v]"
    )


def _filter_F(title: str) -> str:
    """F: Dual Box — 앵커 좌 + 타이틀 우"""
    safe_title = _esc(title[:30])
    return (
        f"[0:v]scale=640:{H},setsar=1[left];"
        f"color=c=#1e293b:s=640x{H}:r={FPS}[right_bg];"
        f"[right_bg]drawtext=text='KT NEWS':fontsize=20:fontcolor=#e6002d:x=40:y=60,"
        f"drawtext=text='{safe_title}':fontsize=28:fontcolor=white:x=40:y=100:line_spacing=10[right];"
        f"[left][right]hstack=inputs=2[v]"
    )


def _esc(text: str) -> str:
    """ffmpeg drawtext용 특수문자 이스케이프."""
    return (
        text
        .replace("\\", "\\\\")
        .replace("'",  "\\'")
        .replace(":",  "\\:")
        .replace("%",  "\\%")
    )


def _get_filter(template: str, title: str) -> str:
    return {
        "A": lambda: _filter_A(title),
        "B": lambda: _filter_B(),
        "C": lambda: _filter_C(),
        "D": lambda: _filter_D(title),
        "E": lambda: _filter_E(title),
        "F": lambda: _filter_F(title),
    }.get(template, lambda: _filter_C())()


# ══════════════════════════════════════════════════════════════════════════════
# 단일 씬에 템플릿 적용
# ══════════════════════════════════════════════════════════════════════════════
def _apply_template_to_scene(
    src: Path,
    dst: Path,
    template: str,
    title: str,
) -> bool:
    """씬 영상에 템플릿 레이아웃을 적용합니다. 성공 시 True."""
    vfilter = _get_filter(template, title)
    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(src),
                "-filter_complex", vfilter,
                "-map", "[v]",
                "-map", "0:a",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "128k",
                str(dst),
            ],
            check=True,
            capture_output=True,
        )
        return True
    except Exception:
        # 실패 시 원본 그대로 복사
        dst.write_bytes(src.read_bytes())
        return False


# ══════════════════════════════════════════════════════════════════════════════
# 크로스디졸브 연결
# ══════════════════════════════════════════════════════════════════════════════
def _concat_with_dissolve(inputs: list[Path], output: Path) -> bool:
    """씬 목록을 크로스디졸브 전환으로 연결합니다."""
    if len(inputs) == 1:
        output.write_bytes(inputs[0].read_bytes())
        return True

    try:
        from moviepy import VideoFileClip, concatenate_videoclips  # type: ignore

        clips = [VideoFileClip(str(p)) for p in inputs]
        acc   = [clips[0]]
        for c in clips[1:]:
            acc.append(
                c.with_start(acc[-1].end - FADE).crossfadein(FADE)
            )
        final = concatenate_videoclips(acc, method="compose", padding=-FADE)
        final.write_videofile(str(output), fps=FPS, codec="libx264",
                              audio_codec="aac", logger=None)
        for c in clips:
            c.close()
        final.close()
        return True
    except Exception:
        pass

    # moviepy 실패 → ffmpeg concat (단순 이어붙이기)
    return _concat_ffmpeg(inputs, output)


def _concat_ffmpeg(inputs: list[Path], output: Path) -> bool:
    """ffmpeg concat 필터로 이어붙이기 (페이드 없음)."""
    list_file = output.parent / "_concat_list.txt"
    list_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in inputs),
        encoding="utf-8",
    )
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", str(list_file), "-c", "copy", str(output)],
            check=True, capture_output=True,
        )
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# 공개 API
# ══════════════════════════════════════════════════════════════════════════════
def render_final_video(
    project_dir: Path,
    scene_video_paths: list[Path],
    template: str,
    scene_scripts: list[str] | None = None,
    transition_sec: float = FADE,
) -> Path:
    """
    씬 영상들에 템플릿을 적용하고 최종 MP4를 생성합니다.

    Args:
        project_dir:       프로젝트 데이터 디렉터리
        scene_video_paths: 씬 영상 경로 목록 (order_index 순)
        template:          템플릿 코드 (A~F)
        scene_scripts:     씬별 대본 (타이틀 패널용), 없으면 빈 문자열

    Returns:
        Path: 최종 영상 경로 (final.mp4)
    """
    output = project_dir / "final.mp4"

    valid = [p for p in scene_video_paths if p.exists() and p.stat().st_size > 100]
    if not valid:
        output.write_text("생성된 씬 영상이 없습니다.", encoding="utf-8")
        return output

    scene_scripts = scene_scripts or [""] * len(valid)

    # ① 각 씬에 템플릿 적용
    templated: list[Path] = []
    tmp_dir = project_dir / "_render_tmp"
    tmp_dir.mkdir(exist_ok=True)

    for idx, (scene_path, title) in enumerate(zip(valid, scene_scripts)):
        out_scene = tmp_dir / f"scene_{idx:03d}_tmpl.mp4"
        _apply_template_to_scene(scene_path, out_scene, template, title)
        templated.append(out_scene)

    # ② 크로스디졸브 연결
    if not _concat_with_dissolve(templated, output):
        output.write_text(
            f"렌더 실패\ntemplate={TEMPLATE_LABEL.get(template, template)}\n",
            encoding="utf-8",
        )

    return output
