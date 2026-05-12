"""Arrangement helpers: looping with crossfades, fades, padding.

The mixer always renders to a fixed target length (voice + pre/post-roll).
The background music is fitted to that length via `fit_to_length`:

- If the music is LONGER than the target → it's trimmed (and the master
  fade-out covers the cut so there's no abrupt end).
- If the music is SHORTER than the target → it's looped with equal-power
  crossfades at every seam. The crossfade auto-shrinks if the music is
  too short to support a 500 ms seam without smearing content.
- If the music is EXACTLY the target → it's used as-is (no crossfade).

A `FitReport` is returned alongside the audio so the caller can surface
"looped N times" or "trimmed X seconds" in the render manifest.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np


@dataclass(frozen=True)
class FitReport:
    mode: Literal["used_as_is", "trimmed", "looped", "tiled_no_xfade"]
    loops: int               # how many times the source is repeated (≥ 1)
    source_seconds: float
    target_seconds: float
    crossfade_ms: float      # actual crossfade used (may be < requested)


def _equal_power_curves(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Equal-power fade-out and fade-in curves of length n."""
    t = np.linspace(0.0, 1.0, n, endpoint=False, dtype=np.float32)
    return np.cos(t * np.pi / 2.0).astype(np.float32), np.sin(t * np.pi / 2.0).astype(np.float32)


def _equal_power_crossfade(a: np.ndarray, b: np.ndarray, n: int) -> np.ndarray:
    """Crossfade the last n samples of a with the first n samples of b.

    Operates on (channels, samples) arrays. Returns concatenated audio of length
    a.shape[-1] + b.shape[-1] - n. Used by callers that don't need the
    pre-allocated O(N) loop_to_length path.
    """
    n = min(n, a.shape[-1], b.shape[-1])
    if n <= 0:
        return np.concatenate([a, b], axis=-1)
    fade_out, fade_in = _equal_power_curves(n)
    head = a[..., :-n]
    tail = b[..., n:]
    cross = a[..., -n:] * fade_out + b[..., :n] * fade_in
    return np.concatenate([head, cross, tail], axis=-1)


def fit_to_length(
    bg: np.ndarray,
    sr: int,
    target_samples: int,
    crossfade_ms: float = 500.0,
) -> tuple[np.ndarray, FitReport]:
    """Fit `bg` to exactly `target_samples` samples.

    Handles every length combination:
      target == 0           → empty array
      bg.length == target   → returned untouched (no crossfade)
      bg.length >  target   → trimmed to target
      bg.length <  target   → seamlessly looped with crossfades
      bg.length is tiny     → crossfade auto-shrinks to 25 % of bg, or
                              falls back to no-crossfade tiling if the
                              source is shorter than 4 ms

    Returns (audio, FitReport). Audio shape is (channels, target_samples).
    """
    if bg.ndim == 1:
        bg = bg[np.newaxis, :]
    if bg.dtype != np.float32:
        bg = bg.astype(np.float32, copy=False)
    n_ch, n_bg = bg.shape

    if n_bg == 0:
        raise ValueError("Background audio is empty.")
    if target_samples < 0:
        raise ValueError(f"target_samples must be >= 0, got {target_samples}")

    source_s = n_bg / sr
    target_s = target_samples / sr

    # Empty target.
    if target_samples == 0:
        return (np.zeros((n_ch, 0), dtype=np.float32),
                FitReport("used_as_is", 1, source_s, target_s, 0.0))

    # Fast path: exactly the right length.
    if n_bg == target_samples:
        return (bg.copy(),
                FitReport("used_as_is", 1, source_s, target_s, 0.0))

    # Fast path: bg longer than target → just trim.
    if n_bg > target_samples:
        return (bg[..., :target_samples].copy(),
                FitReport("trimmed", 1, source_s, target_s, 0.0))

    # bg is shorter than target → loop with crossfades.
    requested_xfade = int(sr * crossfade_ms / 1000.0)
    # Keep at least 50 % of each loop pristine: cap xfade at 25 % of bg.
    xfade = min(requested_xfade, max(0, n_bg // 4))
    # Don't bother with xfades shorter than ~4 ms — gives clicks anyway.
    if xfade < int(sr * 0.004):
        xfade = 0

    out = np.zeros((n_ch, target_samples), dtype=np.float32)

    if xfade <= 0:
        # Source too short for a meaningful crossfade; tile and truncate.
        n_repeats = -(-target_samples // n_bg)  # ceil divide
        tiled = np.tile(bg, (1, n_repeats))
        out[:] = tiled[..., :target_samples]
        return out, FitReport(
            "tiled_no_xfade", n_repeats, source_s, target_s, 0.0,
        )

    # Pre-allocated O(N) construction. Each new loop overwrites the last
    # `xfade` samples of the previous placement with a crossfade, then
    # writes bg[xfade:] as fresh body.
    fade_out, fade_in = _equal_power_curves(xfade)

    # Place the first copy verbatim.
    first_take = min(n_bg, target_samples)
    out[..., :first_take] = bg[..., :first_take]
    pos = first_take
    loops = 1

    bg_body = bg[..., xfade:]            # length n_bg - xfade
    bg_head = bg[..., :xfade]            # length xfade

    while pos < target_samples:
        loops += 1
        # Crossfade region: last `xfade` of placed audio with first `xfade` of bg.
        overlap_start = pos - xfade
        out[..., overlap_start:pos] = (
            out[..., overlap_start:pos] * fade_out
            + bg_head * fade_in
        )
        # Append the body of bg after the crossfade.
        remaining = target_samples - pos
        take = min(bg_body.shape[-1], remaining)
        out[..., pos:pos + take] = bg_body[..., :take]
        pos += take

    return out, FitReport(
        "looped", loops, source_s, target_s, xfade * 1000.0 / sr,
    )


# Backward-compatible wrapper used elsewhere; returns just the audio.
def loop_to_length(
    bg: np.ndarray, sr: int, target_samples: int, crossfade_ms: float = 500.0,
) -> np.ndarray:
    audio, _ = fit_to_length(bg, sr, target_samples, crossfade_ms=crossfade_ms)
    return audio


def apply_fades(audio: np.ndarray, sr: int,
                fade_in_s: float = 2.0, fade_out_s: float = 4.0) -> np.ndarray:
    """Apply linear fade-in and fade-out (returns a new array)."""
    out = audio.copy()
    n = out.shape[-1]

    fi = min(int(sr * fade_in_s), n)
    if fi > 0:
        ramp = np.linspace(0.0, 1.0, fi, dtype=np.float32)
        out[..., :fi] *= ramp

    fo = min(int(sr * fade_out_s), n)
    if fo > 0:
        ramp = np.linspace(1.0, 0.0, fo, dtype=np.float32)
        out[..., -fo:] *= ramp

    return out


def pad_voice(voice: np.ndarray, sr: int,
              pre_roll_s: float, post_roll_s: float) -> np.ndarray:
    """Add silence before and after the voice. Voice is 1D (mono)."""
    pre = int(sr * pre_roll_s)
    post = int(sr * post_roll_s)
    return np.concatenate([
        np.zeros(pre, dtype=np.float32),
        voice.astype(np.float32),
        np.zeros(post, dtype=np.float32),
    ])
