"""Split-band de-esser using a Linkwitz-Riley 4th-order crossover.

Pedalboard 0.9 has no native de-esser. Two paths exist:
1. Load Techivation T-De-Esser 2 (free VST3) via `pedalboard.load_plugin()`.
2. The pure-Python implementation below, which compresses only the high band
   (sibilance lives at ~5.5-8 kHz) and sums back. This is a real split-band
   dynamic process — not the dead-sounding bandstop EQ trick.

Used post-compressor on the voice chain, where sibilance is loudest relative
to the rest of the body.
"""
from __future__ import annotations

import numpy as np
from pedalboard import Compressor, Pedalboard
from scipy.signal import butter, sosfilt


def _linkwitz_riley_4(audio: np.ndarray, sr: int, cutoff_hz: float) -> tuple[np.ndarray, np.ndarray]:
    """4th-order Linkwitz-Riley split: two cascaded 2nd-order Butterworths.

    Sum of low + high is allpass at the crossover, so reassembly is artefact-free.
    """
    sos_lp = butter(2, cutoff_hz, btype="low", fs=sr, output="sos")
    sos_hp = butter(2, cutoff_hz, btype="high", fs=sr, output="sos")
    low = sosfilt(sos_lp, sosfilt(sos_lp, audio)).astype(np.float32)
    high = sosfilt(sos_hp, sosfilt(sos_hp, audio)).astype(np.float32)
    return low, high


def deess(
    audio_mono: np.ndarray,
    sr: int,
    cutoff_hz: float = 6500.0,
    threshold_db: float = -26.0,
    ratio: float = 4.0,
    attack_ms: float = 0.5,
    release_ms: float = 40.0,
) -> np.ndarray:
    """Compress only the >cutoff_hz band of a mono voice signal."""
    if audio_mono.ndim != 1:
        raise ValueError("deess expects mono input")

    low, high = _linkwitz_riley_4(audio_mono, sr, cutoff_hz)
    high_c = Pedalboard([
        Compressor(
            threshold_db=threshold_db,
            ratio=ratio,
            attack_ms=attack_ms,
            release_ms=release_ms,
        )
    ])(high.astype(np.float32), sr)
    if high_c.ndim > 1:
        high_c = high_c[0]
    return (low + high_c).astype(np.float32)
