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
    """Simple placeholder synthesizer.

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
        amp = 6000
        frames = bytearray()
        for i in range(n_samples):
            v = int(amp * math.sin(2.0 * math.pi * freq * (i / sample_rate)))
            frames.extend(int(v).to_bytes(2, byteorder="little", signed=True))
        wav_file.writeframes(bytes(frames))

    return duration_sec
