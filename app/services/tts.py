from __future__ import annotations

import math
import wave
from pathlib import Path


def apply_pronunciation(script: str, pronunciation_dict: dict[str, str]) -> str:
    rendered = script
    for src, target in pronunciation_dict.items():
        rendered = rendered.replace(src, target)
    return rendered


def synthesize_wav(script: str, output_path: Path, sample_rate: int = 22050) -> float:
    """Simple deterministic placeholder synthesizer.

    Duration scales with script length to mimic TTS timing.
    """
    duration_sec = max(1.2, min(10.0, len(script) / 7.0))
    n_samples = int(duration_sec * sample_rate)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)

        freq = 220.0
        amp = 5500
        frames = bytearray()
        for i in range(n_samples):
            wobble = 1.0 + 0.15 * math.sin(2.0 * math.pi * 2.0 * (i / sample_rate))
            v = int(amp * wobble * math.sin(2.0 * math.pi * freq * (i / sample_rate)))
            frames.extend(int(v).to_bytes(2, byteorder="little", signed=True))
        wav_file.writeframes(bytes(frames))

    return duration_sec


def write_srt(script: str, duration_sec: float, output_path: Path) -> None:
    h, rem = divmod(int(duration_sec), 3600)
    m, s = divmod(rem, 60)
    ms = int((duration_sec - int(duration_sec)) * 1000)
    end_ts = f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    content = f"1\n00:00:00,000 --> {end_ts}\n{script}\n"
    output_path.write_text(content, encoding="utf-8")
