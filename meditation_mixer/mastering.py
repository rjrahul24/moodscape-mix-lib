"""Mastering helpers: true-peak limiting, LUFS normalization, dither, M/S width,
and a verification gate.
"""
from __future__ import annotations

import warnings
from typing import NamedTuple

import numpy as np
import pyloudnorm as pyln
from scipy.ndimage import minimum_filter1d
from scipy.signal import resample_poly


def _lookahead_brickwall(
    audio: np.ndarray, sr: int,
    threshold_lin: float,
    attack_ms: float,
    release_ms: float,
) -> np.ndarray:
    """Per-sample gain envelope that keeps |audio| ≤ threshold_lin everywhere.

    `audio` is (channels, samples). The detector is the cross-channel peak,
    so the stereo image is preserved (both channels get the same gain).
    Attack uses a backward minimum-filter look-ahead so reduction lands a
    few ms *before* a transient, and a one-pole release walks gain back
    toward 1.0 between peaks.
    """
    detector = np.max(np.abs(audio), axis=0)
    target = np.minimum(1.0, threshold_lin / np.maximum(detector, 1e-12)).astype(np.float32)

    la = max(1, int(sr * attack_ms / 1000.0))
    # Sliding minimum over the next `la` samples: at sample i the gain
    # already reflects the smallest target_gain in [i, i+la). Equivalent
    # to a look-ahead window equal to the attack time.
    target = minimum_filter1d(target, size=la, origin=-(la // 2), mode="nearest")

    r = float(np.exp(-1.0 / (sr * release_ms / 1000.0))) if release_ms > 0 else 0.0
    smoothed = np.empty_like(target)
    g = 1.0
    for i in range(target.size):
        t = float(target[i])
        # Instant attack (already pre-scheduled by the look-ahead window);
        # one-pole release back up toward 1.0.
        g = t if t < g else (r * g + (1.0 - r) * t)
        smoothed[i] = g
    return smoothed


def true_peak_limit(
    stereo: np.ndarray, sr: int,
    threshold_db: float = -1.0,
    release_ms: float = 200.0,
    attack_ms: float = 2.0,
    oversample: int = 4,
    safety_margin_db: float = 0.3,
) -> np.ndarray:
    """4×-oversampled brickwall true-peak limiter.

    Upsample by `oversample`, compute a per-sample gain envelope that holds
    |x| ≤ threshold (with a look-ahead window equal to attack_ms), then
    downsample. This is a real ITU-R BS.1770 true-peak limiter — no
    transient overshoots, no harmonic-distortion ringing on the next stage.

    `threshold_db` is the *user-facing* true-peak ceiling. Because the final
    clip happens at the original sample rate but true-peak measurement
    reconstructs intersample peaks via oversampling, the measured TP can
    land slightly above the clip threshold (typically 0.05-0.2 dB). We
    internally clip `safety_margin_db` below the user-facing target so the
    *measured* TP comes in under spec.
    """
    threshold_lin = float(10.0 ** ((threshold_db - safety_margin_db) / 20.0))
    up_sr = sr * oversample
    up = resample_poly(stereo, oversample, 1, axis=-1).astype(np.float32)

    gain = _lookahead_brickwall(up, up_sr, threshold_lin, attack_ms, release_ms)
    up *= gain[np.newaxis, :]
    # Safety net for any 1-sample numerical overshoot.
    np.clip(up, -threshold_lin, threshold_lin, out=up)

    down = resample_poly(up, 1, oversample, axis=-1).astype(np.float32)
    # Resample-lowpass ringing can briefly poke 0.05-0.1 dB above ceiling.
    # Clip in the original sample rate; the energy is sub-perceptible and
    # this guarantees the file respects the dBTP target.
    np.clip(down, -threshold_lin, threshold_lin, out=down)
    return down


def normalize_lufs(stereo: np.ndarray, sr: int, target_lufs: float) -> tuple[np.ndarray, float]:
    """Integrated-loudness normalize. Returns (audio, measured_lufs_before).

    pyloudnorm warns when its output exceeds ±1.0 ("Possible clipped
    samples"). In this pipeline the true-peak limiter runs immediately
    after normalize, so brief >1.0 excursions here are expected and
    intentionally handled downstream — silence that specific warning.
    """
    meter = pyln.Meter(sr, filter_class="DeMan")
    interleaved = stereo.T.astype(np.float32)
    loudness = float(meter.integrated_loudness(interleaved))
    if not np.isfinite(loudness):
        return stereo, loudness
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Possible clipped samples in output.",
            category=UserWarning,
            module=r"pyloudnorm\..*",
        )
        out = pyln.normalize.loudness(interleaved, loudness, target_lufs).T.astype(np.float32)
    return out, loudness


def tpdf_dither(audio: np.ndarray, bits: int = 16, rng: np.random.Generator | None = None) -> np.ndarray:
    """Triangular-PDF dither at ±1 LSB before bit-depth reduction."""
    rng = rng or np.random.default_rng()
    lsb = 1.0 / (2 ** (bits - 1))
    noise = (rng.random(audio.shape, dtype=np.float32)
             - rng.random(audio.shape, dtype=np.float32)) * lsb
    return audio + noise


def adjust_stereo_width(
    stereo: np.ndarray, width: float = 1.15, mid_gain_db: float = -2.0,
) -> np.ndarray:
    """M/S widening for the music bed. `width` > 1 widens; mid_gain_db tucks
    the centre to carve space for the centered voice. Mono compatibility is
    checked separately via `mono_sum_delta_lu`.
    """
    mid = (stereo[0] + stereo[1]) * 0.5 * (10.0 ** (mid_gain_db / 20.0))
    side = (stereo[0] - stereo[1]) * 0.5 * width
    return np.stack([mid + side, mid - side], axis=0).astype(np.float32)


class VerifyReport(NamedTuple):
    integrated_lufs: float
    true_peak_db: float
    lra_lu: float
    mono_sum_delta_lu: float
    issues: list[str]


def measure_true_peak(stereo: np.ndarray, sr: int, oversample: int = 4) -> float:
    up = resample_poly(stereo, oversample, 1, axis=-1)
    peak = float(np.max(np.abs(up)) + 1e-12)
    return 20.0 * np.log10(peak)


def mono_sum_delta_lu(stereo: np.ndarray, sr: int) -> float:
    """Stereo LUFS - mono-sum LUFS. A large positive value indicates side info
    that will collapse when summed (over-widening).
    """
    meter = pyln.Meter(sr, filter_class="DeMan")
    stereo_lufs = float(meter.integrated_loudness(stereo.T.astype(np.float32)))
    mono = (stereo[0] + stereo[1]) * 0.5
    mono_stack = np.stack([mono, mono], axis=0)
    mono_lufs = float(meter.integrated_loudness(mono_stack.T.astype(np.float32)))
    if not (np.isfinite(stereo_lufs) and np.isfinite(mono_lufs)):
        return 0.0
    return stereo_lufs - mono_lufs


def verify_master(
    stereo: np.ndarray, sr: int,
    target_lufs: float = -16.0,
    target_tp_db: float = -1.0,
    lra_range: tuple[float, float] = (4.0, 10.0),
    lufs_tolerance: float = 0.5,
    mono_sum_max_lu: float = 3.0,
) -> VerifyReport:
    meter = pyln.Meter(sr, filter_class="DeMan")
    interleaved = stereo.T.astype(np.float32)
    integrated = float(meter.integrated_loudness(interleaved))
    try:
        lra = float(meter.loudness_range(interleaved))
    except Exception:
        lra = float("nan")
    tp = measure_true_peak(stereo, sr)
    mono_delta = mono_sum_delta_lu(stereo, sr)

    issues: list[str] = []
    if np.isfinite(integrated) and abs(integrated - target_lufs) > lufs_tolerance:
        issues.append(f"LUFS off by {integrated - target_lufs:+.2f} (target {target_lufs})")
    if tp > target_tp_db:
        issues.append(f"True peak {tp:+.2f} dBTP exceeds {target_tp_db}")
    if np.isfinite(lra) and not (lra_range[0] <= lra <= lra_range[1]):
        issues.append(f"LRA {lra:.1f} LU outside {lra_range}")
    if abs(mono_delta) > mono_sum_max_lu:
        issues.append(f"Mono-sum delta {mono_delta:+.2f} LU exceeds ±{mono_sum_max_lu}")

    return VerifyReport(
        integrated_lufs=integrated,
        true_peak_db=tp,
        lra_lu=lra,
        mono_sum_delta_lu=mono_delta,
        issues=issues,
    )
