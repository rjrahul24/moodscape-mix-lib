"""Background sound library: list, save uploads, load to numpy."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from pedalboard.io import AudioFile

from .config import BACKGROUNDS_DIR, SAMPLE_RATE, SUPPORTED_BG_EXTS


def list_backgrounds() -> list[Path]:
    BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(
        p for p in BACKGROUNDS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_BG_EXTS
    )


def _safe_name(name: str) -> str:
    name = re.sub(r"[^\w.\- ]+", "_", name).strip()
    return name or "upload.wav"


def save_upload(filename: str, data: bytes) -> Path:
    """Save uploaded file bytes to backgrounds/, returning the final path.

    If a file with the same name already exists it is overwritten so the
    dropdown never accumulates numbered duplicates (_2, _3, …).
    """
    BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKGROUNDS_DIR / _safe_name(filename)
    target.write_bytes(data)
    return target


def load_audio(path: Path, target_sr: int = SAMPLE_RATE) -> tuple[np.ndarray, int]:
    """Load any supported audio file, resample if needed, return (channels, samples) float32.

    Shape is always 2D: (n_channels, n_samples). Mono stays (1, N), stereo stays (2, N).
    """
    with AudioFile(str(path)).resampled_to(target_sr) as f:
        audio = f.read(f.frames)  # shape: (channels, samples), float32

    if audio.ndim == 1:
        audio = audio[np.newaxis, :]
    return audio.astype(np.float32), target_sr
