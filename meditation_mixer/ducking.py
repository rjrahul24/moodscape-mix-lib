"""Frequency-selective sidechain ducking with look-ahead.

Two layers of ducking:

1. `freq_selective_duck` — reactive envelope follower. Detects voice in
   the 200 Hz – 4 kHz band, smooths to a per-sample gain curve with a
   short look-ahead, and ducks only the mid band of the music. Cheap,
   always-on, catches anything that happens to be loud on the voice bus
   (including off-script breaths).

2. `script_aware_duck` — deterministic curve generated from phrase
   timestamps. Descends predictively 500 ms BEFORE each phrase onset,
   holds -9 dB during the phrase, releases over 1200 ms with a cubic
   S-curve, and LIFTS the music +1.5 dB during long pauses so the bed
   "breathes" with the script. Far more musical than a reactive duck on
   long silences; impossible to implement reactively.

3. `combine_script_with_reactive` — combines the two: where the
   reactive detector engages (voice present), it can deepen the duck
   beyond what the script asked for; where it doesn't engage (silence),
   the script curve passes through verbatim so positive +lift plateaus
   survive. A naive np.minimum would silently clamp the lift to 0 dB.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt, sosfiltfilt


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



# ----- Script-aware deterministic ducking ---------------------------- #


def _smoothstep(x: np.ndarray) -> np.ndarray:
    """Cubic Hermite S-curve, x in [0,1] -> [0,1]. Zero derivative at
    both endpoints — transitions read as "musical" rather than as
    automation snaps.
    """
    x = np.clip(x, 0.0, 1.0)
    return (x * x * (3.0 - 2.0 * x)).astype(np.float32)


def reactive_gain_db(
    voice_mono: np.ndarray, sr: int,
    threshold_db: float = -30.0,
    range_db: float = -9.0,
    attack_ms: float = 15.0,
    release_ms: float = 500.0,
    lookahead_ms: float = 10.0,
    detector_band_hz: tuple[float, float] = (200.0, 4000.0),
) -> np.ndarray:
    """Reactive envelope-follower gain curve in dB, same detector as
    `freq_selective_duck` but without applying it to any bg. Useful as a
    safety-net signal combined into the script-aware curve via `np.minimum`.
    """
    det = _bandpass(voice_mono, sr, detector_band_hz[0], detector_band_hz[1])
    env = _rms_env(det, sr, ms=30.0)
    env_db = 20.0 * np.log10(env + 1e-9)
    over = np.clip(env_db - threshold_db, 0.0, None)
    slope = range_db / 9.0
    target_db = np.clip(over * slope, range_db, 0.0).astype(np.float32)
    smoothed_db = _smoothed_gain(target_db, sr, attack_ms, release_ms)
    la = int(sr * lookahead_ms / 1000.0)
    if la > 0:
        smoothed_db = np.concatenate(
            [smoothed_db[la:], np.zeros(la, dtype=np.float32)]
        )
    return smoothed_db


def detect_phrases_from_audio(
    voice_mono: np.ndarray, sr: int,
    threshold_db: float = -40.0,
    env_ms: float = 30.0,
    min_phrase_ms: float = 150.0,
    merge_gap_ms: float = 250.0,
) -> list[tuple[float, float]]:
    """Voice activity detection by RMS-envelope thresholding.

    Returns a list of (start_s, end_s) phrase boundaries. Within-phrase
    gaps shorter than `merge_gap_ms` (the typical inter-word pause inside
    a sentence) are merged so we don't pump the music between words.
    Phrases shorter than `min_phrase_ms` are dropped as breath/click
    noise.

    Used as a fallback when the chunker can't supply timestamps directly
    (e.g. when a single chunk contains many sentences and we don't have
    word-level data from ElevenLabs).
    """
    if voice_mono.size == 0:
        return []
    env = _rms_env(voice_mono.astype(np.float32), sr, ms=env_ms)
    env_db = 20.0 * np.log10(env + 1e-9)
    is_voice = env_db > threshold_db

    # Find rising/falling edges.
    diffs = np.diff(is_voice.astype(np.int8))
    starts = (np.where(diffs > 0)[0] + 1).tolist()
    ends = (np.where(diffs < 0)[0] + 1).tolist()
    if is_voice[0]:
        starts.insert(0, 0)
    if is_voice[-1]:
        ends.append(int(is_voice.size))
    if not starts or not ends:
        return []

    phrases = list(zip(starts, ends))
    merge_n = int(sr * merge_gap_ms / 1000.0)
    merged: list[tuple[int, int]] = [phrases[0]]
    for s, e in phrases[1:]:
        ps, pe = merged[-1]
        if s - pe < merge_n:
            merged[-1] = (ps, e)
        else:
            merged.append((s, e))

    min_n = int(sr * min_phrase_ms / 1000.0)
    merged = [(s, e) for s, e in merged if (e - s) >= min_n]
    return [(s / sr, e / sr) for s, e in merged]


def script_aware_gain_db(
    duration_samples: int,
    sr: int,
    phrases: list[tuple[float, float]],
    pre_descent_ms: float = 500.0,
    attack_ms: float = 450.0,
    release_ms: float = 1200.0,
    duck_db: float = -9.0,
    lift_db: float = 1.5,
    lift_pause_s: float = 1.5,
    smooth_hz: float = 5.0,
) -> np.ndarray:
    """Build a deterministic music-gain envelope (in dB) from phrase
    timestamps. Positive lift during long pauses, smooth S-curve descent
    starting BEFORE each phrase, -9 dB hold during the phrase, S-curve
    release back to baseline (or to lift_db if the next gap is long).

    Final output is zero-phase smoothed at `smooth_hz` so any keyframe
    corners round into "musical" transitions.
    """
    n = int(duration_samples)
    g_db = np.zeros(n, dtype=np.float32)
    if n == 0:
        return g_db

    duration_s = n / sr

    # 1. Pause lifts — flat plateau at +lift_db wherever the gap between
    #    adjacent phrases is at least `lift_pause_s`. The S-curves into
    #    and out of the plateau are absorbed by the descent/release of
    #    the bounding phrases below, so we only fill the centre here.
    if lift_db > 0 and phrases and lift_pause_s > 0:
        # Build gap list: from t=0 to first phrase, between phrases,
        # last phrase to duration_s.
        boundaries: list[tuple[float, float]] = []
        prev_end = 0.0
        for (s, e) in phrases:
            if s - prev_end >= lift_pause_s:
                boundaries.append((prev_end, s))
            prev_end = e
        if duration_s - prev_end >= lift_pause_s:
            boundaries.append((prev_end, duration_s))

        for (g_start, g_end) in boundaries:
            # Keep clear of the upcoming descent and the previous release.
            plateau_start = g_start + release_ms / 1000.0
            plateau_end = g_end - pre_descent_ms / 1000.0
            if plateau_end <= plateau_start:
                continue
            i0 = max(0, int(plateau_start * sr))
            i1 = min(n, int(plateau_end * sr))
            if i1 > i0:
                g_db[i0:i1] = lift_db

    # 2. For each phrase: predictive descent, held duck, post-phrase
    #    ascent. The ascent target is +lift_db if the next gap is long,
    #    else 0 dB.
    for idx, (t_on, t_off) in enumerate(phrases):
        # Predictive descent: cubic S-curve, ending exactly at t_on so
        # the duck is fully engaged on the consonant onset.
        ramp_n = max(1, int(attack_ms / 1000.0 * sr))
        desc_start = int(round((t_on - pre_descent_ms / 1000.0) * sr))
        desc_end = desc_start + ramp_n
        if desc_end > 0 and desc_start < n:
            seg_start = max(0, desc_start)
            seg_end = min(n, desc_end)
            seg_len = seg_end - seg_start
            if seg_len > 0:
                t = (np.arange(seg_len, dtype=np.float32)
                     + (seg_start - desc_start)) / max(1, ramp_n)
                # Starting value = current gain at desc_start (could be
                # lift_db if we're descending out of a long pause, or 0).
                g0 = float(g_db[seg_start]) if seg_start < n else 0.0
                g_db[seg_start:seg_end] = g0 + (duck_db - g0) * _smoothstep(t)

        # Held duck through phrase.
        i_on = max(0, int(round(t_on * sr)))
        i_off = min(n, int(round(t_off * sr)))
        if i_off > i_on:
            g_db[i_on:i_off] = duck_db

        # Post-phrase ascent. Target is lift_db if there is a long gap
        # before the next phrase, else 0 dB.
        next_on = phrases[idx + 1][0] if idx + 1 < len(phrases) else duration_s
        gap_s = next_on - t_off
        target = lift_db if (gap_s >= lift_pause_s and lift_db > 0) else 0.0
        rel_n = max(1, int(release_ms / 1000.0 * sr))
        rel_end = min(n, i_off + rel_n)
        seg_len = rel_end - i_off
        if seg_len > 0:
            t = np.arange(seg_len, dtype=np.float32) / max(1, rel_n)
            g_db[i_off:rel_end] = duck_db + (target - duck_db) * _smoothstep(t)

    # 3. Zero-phase Butterworth smoothing at `smooth_hz` to round any
    #    remaining keyframe corners. sosfiltfilt is double-pass so the
    #    cutoff is effectively √2× lower — at 8 Hz that's ~125 ms
    #    perceptual softening, just enough to feel natural.
    if smooth_hz and smooth_hz > 0 and n > 12:
        sos = butter(2, float(smooth_hz), btype="low", fs=sr, output="sos")
        g_db = sosfiltfilt(sos, g_db).astype(np.float32)

    return g_db



def combine_script_with_reactive(
    g_script: np.ndarray, g_reactive: np.ndarray,
) -> np.ndarray:
    """Combine a script-aware curve (may contain positive +lift plateaus)
    with a reactive safety-net curve (always <= 0 dB).

    Logic:
      - Where script is asking for lift (g_script > 0 dB), the script
        wins. The reactive curve's release tail after a phrase typically
        sits around -1 to -3 dB for half a second or more — a naive
        np.minimum would let that tail erase the +lift plateau on every
        pause, silently killing the "music breathes" effect.
      - Where script is at 0 dB or ducking, take the more-restrictive of
        script and reactive. Off-script audio (breaths, mouth noise) gets
        ducked correctly because the reactive detector still triggers.
        Reactive can also deepen an already-ducking script if the voice
        peak is louder than the script predicted.
    """
    n = min(g_script.shape[0], g_reactive.shape[0])
    gs = g_script[:n].astype(np.float32, copy=False)
    gr = g_reactive[:n].astype(np.float32, copy=False)
    return np.where(gs > 0, gs, np.minimum(gs, gr)).astype(np.float32)


def apply_band_split_gain(
    bg_stereo: np.ndarray,
    sr: int,
    gain_db: np.ndarray,
    duck_band_hz: tuple[float, float] = (200.0, 4000.0),
) -> np.ndarray:
    """Apply a dB-gain curve to just the 200 Hz – 4 kHz band of the bg.

    Lows (bass drones) and highs (shimmer) stay at full level, so the
    music still feels present underneath the voice. The mid band is
    where the speech intelligibility window lives — that's the only
    band that needs to move.
    """
    if bg_stereo.ndim == 1:
        bg_stereo = np.stack([bg_stereo, bg_stereo], axis=0)
    n = min(bg_stereo.shape[-1], gain_db.shape[0])
    bg = bg_stereo[..., :n]
    g = gain_db[:n]

    low_hz, high_hz = duck_band_hz
    low_l = _lowpass(bg[0], sr, low_hz)
    low_r = _lowpass(bg[1], sr, low_hz)
    high_l = _highpass(bg[0], sr, high_hz)
    high_r = _highpass(bg[1], sr, high_hz)
    mid_l = bg[0] - low_l - high_l
    mid_r = bg[1] - low_r - high_r

    gain_lin = (10.0 ** (g / 20.0)).astype(np.float32)
    mid_l = mid_l * gain_lin
    mid_r = mid_r * gain_lin

    return np.stack(
        [low_l + mid_l + high_l, low_r + mid_r + high_r],
        axis=0,
    ).astype(np.float32)


def script_aware_duck(
    bg_stereo: np.ndarray,
    voice_mono: np.ndarray,
    sr: int,
    phrases: list[tuple[float, float]] | None = None,
    pre_descent_ms: float = 500.0,
    attack_ramp_ms: float = 450.0,
    release_ms: float = 1200.0,
    duck_db: float = -9.0,
    lift_db: float = 1.5,
    lift_pause_s: float = 1.5,
    smooth_hz: float = 5.0,
    duck_band_hz: tuple[float, float] = (200.0, 4000.0),
    # Reactive safety-net params:
    reactive_threshold_db: float = -30.0,
    reactive_attack_ms: float = 15.0,
    reactive_release_ms: float = 500.0,
    reactive_lookahead_ms: float = 10.0,
) -> tuple[np.ndarray, np.ndarray]:
    """End-to-end script-aware duck. Returns (bg_ducked, combined_gain_db).

    If `phrases` is None, falls back to envelope-based phrase detection
    on the voice — useful when the caller doesn't have explicit timestamps
    available (e.g. a pre-rendered voice file). When the caller has the
    chunker timestamps + phrase boundaries detected per chunk, pass them
    in directly for tighter, click-accurate moves.
    """
    if bg_stereo.shape[-1] != voice_mono.shape[0]:
        raise ValueError(
            f"bg samples ({bg_stereo.shape[-1]}) != "
            f"voice samples ({voice_mono.shape[0]})"
        )
    n = bg_stereo.shape[-1]

    if phrases is None:
        phrases = detect_phrases_from_audio(voice_mono, sr)

    g_script = script_aware_gain_db(
        n, sr, phrases,
        pre_descent_ms=pre_descent_ms,
        attack_ms=attack_ramp_ms,
        release_ms=release_ms,
        duck_db=duck_db,
        lift_db=lift_db,
        lift_pause_s=lift_pause_s,
        smooth_hz=smooth_hz,
    )

    g_react = reactive_gain_db(
        voice_mono, sr,
        threshold_db=reactive_threshold_db,
        range_db=duck_db,  # match the script's depth so neither dominates
        attack_ms=reactive_attack_ms,
        release_ms=reactive_release_ms,
        lookahead_ms=reactive_lookahead_ms,
    )

    g_combined = combine_script_with_reactive(g_script, g_react)
    bg_out = apply_band_split_gain(bg_stereo, sr, g_combined, duck_band_hz)
    return bg_out, g_combined
