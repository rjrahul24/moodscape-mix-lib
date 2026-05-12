"""Frequency-selective sidechain ducking with look-ahead.

Upgrades over a plain amplitude follower:
1. Detector uses the voice's 200 Hz - 4 kHz band so consonants — not breath
   thumps or sibilance — drive ducking.
2. RMS envelope (not peak |x|) for smoother, more musical response.
3. Threshold + range mapping in dB, not a linear depth scalar, so the
   background sits at full level when the voice is silent and dips by a
   fixed amount only when the voice exceeds the threshold.
4. Configurable look-ahead (default 10 ms) eliminates the late-tick on
   consonant onsets.
5. Ducks only the background's mid band; bass drones and shimmery highs
   stay at full level for a richer Calm/Headspace-style feel.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt


def _bandpass(audio: np.ndarray, sr: int, low_hz: float, high_hz: float) -> np.ndarray:
    sos = butter(2, [low_hz, high_hz], btype="band", fs=sr, output="sos")
    return sosfilt(sos, audio).astype(np.float32)


def _lowpass(audio: np.ndarray, sr: int, hz: float) -> np.ndarray:
    sos = butter(2, hz, btype="low", fs=sr, output="sos")
    return sosfilt(sos, audio).astype(np.float32)


def _highpass(audio: np.ndarray, sr: int, hz: float) -> np.ndarray:
    sos = butter(2, hz, btype="high", fs=sr, output="sos")
    return sosfilt(sos, audio).astype(np.float32)


def _rms_env(x: np.ndarray, sr: int, ms: float = 30.0) -> np.ndarray:
    alpha = float(np.exp(-1.0 / (sr * ms / 1000.0)))
    sq = (x.astype(np.float32) ** 2)
    out = np.empty_like(sq)
    e = 0.0
    for i in range(sq.shape[0]):
        e = alpha * e + (1.0 - alpha) * float(sq[i])
        out[i] = e
    return np.sqrt(out, dtype=np.float32)


def _smoothed_gain(
    target_db: np.ndarray, sr: int, attack_ms: float, release_ms: float,
) -> np.ndarray:
    """Asymmetric attack/release smoothing on a gain-reduction-in-dB signal.
    target_db <= 0. Smoothing moves toward more negative values on attack,
    back toward 0 on release.
    """
    a = float(np.exp(-1.0 / (sr * attack_ms / 1000.0))) if attack_ms > 0 else 0.0
    r = float(np.exp(-1.0 / (sr * release_ms / 1000.0))) if release_ms > 0 else 0.0
    out = np.empty_like(target_db)
    g = 0.0
    for i in range(target_db.shape[0]):
        t = float(target_db[i])
        c = a if t < g else r
        g = c * g + (1.0 - c) * t
        out[i] = g
    return out


def freq_selective_duck(
    bg_stereo: np.ndarray,
    voice_mono: np.ndarray,
    sr: int,
    threshold_db: float = -30.0,
    range_db: float = -9.0,
    attack_ms: float = 15.0,
    release_ms: float = 500.0,
    lookahead_ms: float = 10.0,
    detector_band_hz: tuple[float, float] = (200.0, 4000.0),
    duck_band_hz: tuple[float, float] = (200.0, 4000.0),
) -> np.ndarray:
    """Apply Calm/Headspace-style ducking.

    `bg_stereo` is (2, N) float32. `voice_mono` is (N,). Lengths must match.
    `range_db` is the maximum dip (negative dB). −9 dB feels musical; the
    music is still felt, not erased.
    """
    if bg_stereo.shape[-1] != voice_mono.shape[0]:
        raise ValueError(
            f"bg samples ({bg_stereo.shape[-1]}) != voice samples ({voice_mono.shape[0]})"
        )

    # 1. Detector: voice band-limited to consonant/word range.
    det = _bandpass(voice_mono, sr, detector_band_hz[0], detector_band_hz[1])
    env = _rms_env(det, sr, ms=30.0)
    env_db = 20.0 * np.log10(env + 1e-9)

    # 2. Map to target gain reduction.
    over = np.clip(env_db - threshold_db, 0.0, None)  # dB above threshold
    # When voice is at threshold, gr=0. When voice is ~+9 dB over threshold,
    # gr=range_db. Slope 1:1 over a 9 dB range above threshold.
    slope = range_db / 9.0
    target_db = np.clip(over * slope, range_db, 0.0).astype(np.float32)

    # 3. Smooth with asymmetric attack/release.
    smoothed_db = _smoothed_gain(target_db, sr, attack_ms, release_ms)

    # 4. Look-ahead: delay the audio relative to the gain curve so the
    # reduction lands slightly before the consonant onset.
    la = int(sr * lookahead_ms / 1000.0)
    if la > 0:
        # shift gain curve forward in time relative to audio: pad gain at start, trim end
        smoothed_db = np.concatenate(
            [smoothed_db[la:], np.zeros(la, dtype=np.float32)]
        )

    gain_lin = (10.0 ** (smoothed_db / 20.0)).astype(np.float32)

    # 5. Split bg into low / mid / high; apply gain only to mid.
    low_hz, high_hz = duck_band_hz
    low_l = _lowpass(bg_stereo[0], sr, low_hz)
    low_r = _lowpass(bg_stereo[1], sr, low_hz)
    high_l = _highpass(bg_stereo[0], sr, high_hz)
    high_r = _highpass(bg_stereo[1], sr, high_hz)
    mid_l = bg_stereo[0] - low_l - high_l
    mid_r = bg_stereo[1] - low_r - high_r

    mid_l *= gain_lin
    mid_r *= gain_lin

    out = np.stack([low_l + mid_l + high_l, low_r + mid_r + high_r], axis=0).astype(np.float32)
    return out


# Backward-compatible name (old `duck()` signature → new freq-selective duck
# with the prior `depth` argument mapped to a sensible `range_db`).
def duck(
    bg: np.ndarray, voice_mono: np.ndarray, sr: int,
    depth: float = 0.5,
    attack_ms: float = 15.0,
    release_ms: float = 500.0,
) -> np.ndarray:
    """Compatibility shim. `depth` 0..1 maps to range_db 0..-18 dB."""
    range_db = -18.0 * float(np.clip(depth, 0.0, 1.0))
    if bg.ndim == 1:
        bg = np.stack([bg, bg], axis=0)
    return freq_selective_duck(
        bg, voice_mono, sr,
        range_db=range_db,
        attack_ms=attack_ms,
        release_ms=release_ms,
    )
