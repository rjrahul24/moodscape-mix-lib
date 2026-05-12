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


def _dedupe(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    i = 2
    while True:
        candidate = path.with_name(f"{stem}_{i}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def save_upload(filename: str, data: bytes) -> Path:
    """Save uploaded file bytes to backgrounds/, returning the final path."""
    BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)
    target = _dedupe(BACKGROUNDS_DIR / _safe_name(filename))
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


def to_mono(audio: np.ndarray) -> np.ndarray:
    """Downmix (channels, samples) -> (samples,)."""
    if audio.ndim == 1:
        return audio
    return audio.mean(axis=0)


def to_stereo(audio: np.ndarray) -> np.ndarray:
    """Ensure shape is (2, samples)."""
    if audio.ndim == 1:
        return np.stack([audio, audio], axis=0)
    if audio.shape[0] == 1:
        return np.repeat(audio, 2, axis=0)
    if audio.shape[0] == 2:
        return audio
    # fold any >2-channel down to stereo by averaging
    mono = audio.mean(axis=0)
    return np.stack([mono, mono], axis=0)
