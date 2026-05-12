"""Content-addressed disk cache for ElevenLabs PCM.

Key = SHA256 of all inputs that affect the audio: text, voice_id, model_id,
voice_settings, output_format, seed, previous_text, next_text.

Editing a single paragraph in a 40-paragraph script invalidates exactly one
cache entry, so re-renders pay for only what changed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import CACHE_DIR


def _key(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def cache_path(payload: dict[str, Any]) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{_key(payload)}.pcm"


def load(payload: dict[str, Any]) -> bytes | None:
    p = cache_path(payload)
    if p.exists():
        return p.read_bytes()
    return None


def store(payload: dict[str, Any], pcm: bytes) -> Path:
    p = cache_path(payload)
    tmp = p.with_suffix(".pcm.part")
    tmp.write_bytes(pcm)
    tmp.rename(p)
    p.with_suffix(".json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False)
    )
    return p


def clear() -> int:
    if not CACHE_DIR.exists():
        return 0
    n = 0
    for f in CACHE_DIR.iterdir():
        if f.is_file():
            f.unlink()
            n += 1
    return n
