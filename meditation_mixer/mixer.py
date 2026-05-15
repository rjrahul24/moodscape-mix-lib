"""End-to-end mix pipeline: voice + background -> mastered stereo file.

Voice chain  : HPF 90 (rumble removal only); optional mud cut, compression,
               de-ess, presence/air EQ, and convolution reverb — ALL off
               by default so the ElevenLabs output reaches the bus
               un-coloured.
Music chain  : LPF 12 kHz → Compressor → Gain → M/S widen
Ducking      : Frequency-selective sidechain (200 Hz – 4 kHz) with 10 ms
               look-ahead; only the mid band of the music ducks.
Master       : HPF 30 → bus glue Compressor → Air shelf → 4x oversampled
               true-peak Limiter → LUFS normalize to -16 → optional dither
Verify       : LUFS / true-peak / LRA / mono-sum-delta gate before export
Stems        : voice / music / premaster written alongside the master so
               re-mixing or re-mastering doesn't pay for TTS again
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
from pedalboard import (
    Compressor,
    Gain,
    HighShelfFilter,
    HighpassFilter,
    LowpassFilter,
    Pedalboard,
    PeakFilter,
)
from pedalboard.io import AudioFile

from . import arrange, deess, ducking, library, mastering, reverb
from .config import (
    LRA_RANGE,
    OUTPUTS_DIR,
    SAMPLE_RATE,
    TARGET_LUFS,
    TRUE_PEAK_DB,
)


@dataclass
class MixSettings:
    # Music level + ducking
    bg_gain_db: float = -11.0
    duck_threshold_db: float = -30.0
    duck_range_db: float = -7.0
    duck_attack_ms: float = 15.0
    duck_release_ms: float = 500.0
    duck_lookahead_ms: float = 10.0

    # Script-aware ducking (deterministic curve from phrase timestamps).
    # When enabled, builds a predictive descent + held duck + lifted-
    # pause envelope from voice-phrase boundaries, then combines it with
    # the reactive detector via np.minimum so off-script audio still gets
    # ducked. This is the move that makes the music feel like it's
    # "breathing" with the voice.
    use_script_aware_duck: bool = True
    duck_pre_descent_ms: float = 300.0
    duck_attack_ramp_ms: float = 250.0
    duck_lift_db: float = 2.0
    duck_lift_pause_s: float = 1.5

    # Static "carved pocket" on the music. A gentle dip in the speech-
    # intelligibility band (~2 kHz, Q 0.7) lets the dynamic ducker move
    # less aggressively while voice still cuts through cleanly. Static
    # because the carving never needs to move — it's the speech band
    # that always wants room.
    music_pocket_db: float = -2.0
    music_pocket_freq_hz: float = 2000.0
    music_pocket_q: float = 0.7

    # High-shelf brightness boost on the music bed. Compensates for
    # Fletcher-Munson brightness loss when ducking attenuates overall
    # volume — the ear loses high-frequency sensitivity faster than
    # midrange sensitivity as amplitude drops.  A +3 dB shelf at 4500 Hz
    # keeps the music sounding ethereal and present even when ducked by
    # -7 to -9 dB.  (Ref: Optimizations12.md §3.3)
    music_treble_db: float = 3.0
    music_treble_freq_hz: float = 4500.0

    # Arrangement
    pre_roll_s: float = 3.0
    post_roll_s: float = 5.0
    bg_fade_in_s: float = 4.0
    bg_fade_out_s: float = 6.0

    # Voice EQ + reverb. ALL of these default to off / 0 dB so the
    # ElevenLabs output passes through to the mix bus un-coloured.
    # Convolution reverb on a close-mic'd TTS voice is the primary
    # source of the "echoey/robotic" character the previous defaults
    # had, so it is gated behind `apply_voice_reverb`.
    apply_voice_reverb: bool = False
    apply_voice_compression: bool = False
    apply_voice_deess: bool = False
    reverb_wet_db: float = -20.0
    reverb_pre_delay_ms: float = 25.0
    reverb_ir_path: Path | None = None  # None = synthetic plate
    presence_db: float = 0.0
    air_db: float = 0.0
    mud_cut_db: float = 0.0

    # Reverb ducking. Only used when `apply_voice_reverb` is True.
    reverb_duck_db: float = -6.0
    reverb_lift_db: float = 4.0

    # Stereo width on the music bed
    music_width: float = 1.15
    music_mid_db: float = -2.0

    # Targets
    target_lufs: float = TARGET_LUFS
    true_peak_db: float = TRUE_PEAK_DB
    lra_range: tuple[float, float] = field(default_factory=lambda: LRA_RANGE)

    # Output options
    write_stems: bool = True
    dither_16bit: bool = True


def _voice_chain(settings: MixSettings) -> Pedalboard:
    """Build the voice processing chain. Everything except the 90 Hz HPF
    (sub-audible rumble removal) is opt-in — by default we keep the
    ElevenLabs output crisp and untouched.
    """
    stages: list = [HighpassFilter(cutoff_frequency_hz=90.0)]
    if abs(settings.mud_cut_db) > 0.05:
        stages.append(PeakFilter(
            cutoff_frequency_hz=300.0, gain_db=settings.mud_cut_db, q=1.0,
        ))
    if settings.apply_voice_compression:
        stages.append(Compressor(
            threshold_db=-22.0, ratio=2.5, attack_ms=12.0, release_ms=120.0,
        ))
    if abs(settings.presence_db) > 0.05:
        stages.append(PeakFilter(
            cutoff_frequency_hz=4000.0, gain_db=settings.presence_db, q=0.7,
        ))
    if abs(settings.air_db) > 0.05:
        stages.append(HighShelfFilter(
            cutoff_frequency_hz=10000.0, gain_db=settings.air_db,
        ))
    return Pedalboard(stages)


def _bg_chain(
    gain_db: float,
    pocket_freq_hz: float,
    pocket_gain_db: float,
    pocket_q: float,
    treble_db: float = 0.0,
    treble_freq_hz: float = 4500.0,
) -> Pedalboard:
    """Music processing chain.

    * High-shelf boost at `treble_freq_hz` adds brightness that survives
      heavy ducking (Fletcher-Munson compensation — §3.3 of Optimizations12).
    * PeakFilter dip near 2 kHz pre-carves a static "pocket" in the
      speech-intelligibility band so dynamic ducking can be gentler.
    * LPF at 12 kHz acts as a safety ceiling after the treble boost.
    * Compressor + Gain finish the chain.
    """
    stages: list = []
    # Treble boost BEFORE the LPF so the LPF acts as a safety ceiling.
    if abs(treble_db) > 0.05:
        stages.append(HighShelfFilter(
            cutoff_frequency_hz=treble_freq_hz,
            gain_db=treble_db,
        ))
    stages.append(LowpassFilter(cutoff_frequency_hz=12000.0))
    if abs(pocket_gain_db) > 0.05:
        stages.append(PeakFilter(
            cutoff_frequency_hz=pocket_freq_hz,
            gain_db=pocket_gain_db,
            q=pocket_q,
        ))
    stages.append(
        Compressor(threshold_db=-20.0, ratio=2.0, attack_ms=20.0, release_ms=400.0)
    )
    stages.append(Gain(gain_db=gain_db))
    return Pedalboard(stages)


def _master_chain() -> Pedalboard:
    return Pedalboard([
        HighpassFilter(cutoff_frequency_hz=30.0),
        Compressor(threshold_db=-12.0, ratio=1.5, attack_ms=50.0, release_ms=200.0),
        HighShelfFilter(cutoff_frequency_hz=12000.0, gain_db=1.0),
    ])


def _to_mono(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return audio
    if audio.shape[0] == 1:
        return audio[0]
    return audio.mean(axis=0)


def _to_stereo(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return np.stack([audio, audio], axis=0)
    if audio.shape[0] == 1:
        return np.repeat(audio, 2, axis=0)
    if audio.shape[0] == 2:
        return audio
    mono = audio.mean(axis=0)
    return np.stack([mono, mono], axis=0)


def render(
    voice: np.ndarray,
    sr: int,
    bg_path: Path,
    settings: MixSettings,
    output_path: Path,
    output_format: str = "wav",
    speech_segments: list[tuple[float, float]] | None = None,
) -> dict:
    """Run the full mix and write to disk. Returns a render manifest dict.

    voice: 1D mono float32 in [-1, 1] at `sr`.

    `speech_segments`: optional list of (start_s, end_s) phrase
    boundaries IN THE INPUT VOICE TIMELINE (before pre-roll). Comes from
    `tts.synthesize_script(...)`'s manifest. Used to drive the script-
    aware ducking curve when `settings.use_script_aware_duck` is True.
    If omitted, the script-aware duck falls back to envelope-based
    phrase detection on the rendered voice — slightly less precise but
    still much better than reactive-only.
    """
    if voice.ndim != 1:
        voice = _to_mono(voice)
    voice = voice.astype(np.float32)

    # 1. Pad voice with pre/post-roll silence.
    voice_padded = arrange.pad_voice(voice, sr, settings.pre_roll_s, settings.post_roll_s)
    target_n = voice_padded.shape[0]

    # Shift the provided speech-segment timestamps into the padded
    # timeline so all downstream curves share one frame of reference.
    if speech_segments:
        shifted_segments = [
            (s + settings.pre_roll_s, e + settings.pre_roll_s)
            for (s, e) in speech_segments
        ]
    else:
        shifted_segments = None

    # 2. Load + fit background to total length. Handles every combination:
    #    bg longer  → trimmed (master fade-out covers the cut)
    #    bg shorter → seamlessly looped with crossfades
    #    bg equal   → used as-is
    bg, _ = library.load_audio(bg_path, target_sr=sr)
    bg = _to_stereo(bg)
    bg_fit, fit_report = arrange.fit_to_length(
        bg, sr, target_n, crossfade_ms=500.0,
    )
    bg_fit = arrange.apply_fades(
        bg_fit, sr,
        fade_in_s=settings.bg_fade_in_s,
        fade_out_s=settings.bg_fade_out_s,
    )

    # 3. Voice chain. By default this is just a 90 Hz HPF — every other
    # stage (compressor, EQ) is opt-in.
    voice_fx = _voice_chain(settings)(voice_padded, sr)
    voice_mono = _to_mono(voice_fx)

    # 4. De-ess — opt-in. ElevenLabs v3 voices are clean enough that
    # de-essing usually reduces "crispness" more than it helps.
    if settings.apply_voice_deess:
        voice_mono = deess.deess(voice_mono, sr)

    # 5. Convolution reverb — opt-in. Plate reverb on close-mic'd TTS
    # is the main source of "slight echo / robotic" character, so we
    # skip the wet path entirely by default and ship the dry voice as
    # stereo.
    if settings.apply_voice_reverb:
        dry_stereo, wet_stereo = reverb.convolution_reverb_split(
            voice_mono, sr,
            ir_path=settings.reverb_ir_path,
            pre_delay_ms=settings.reverb_pre_delay_ms,
            ir_hpf_hz=250.0,
        )
    else:
        dry_stereo = np.stack([voice_mono, voice_mono], axis=0).astype(np.float32)
        wet_stereo = None

    # 6. Background FX + M/S widen. The PeakFilter in _bg_chain pre-
    # carves a static pocket in the speech-intelligibility band.
    bg_fx = _bg_chain(
        settings.bg_gain_db,
        pocket_freq_hz=settings.music_pocket_freq_hz,
        pocket_gain_db=settings.music_pocket_db,
        pocket_q=settings.music_pocket_q,
        treble_db=settings.music_treble_db,
        treble_freq_hz=settings.music_treble_freq_hz,
    )(bg_fit, sr)
    bg_fx = _to_stereo(bg_fx)
    bg_fx = mastering.adjust_stereo_width(
        bg_fx,
        width=settings.music_width,
        mid_gain_db=settings.music_mid_db,
    )

    # 7. Ducking. Script-aware deterministic curve if we have phrase
    # timestamps (or fall back to envelope-based phrase detection on the
    # voice). Combined with reactive detector via np.minimum so off-
    # script audio (breaths, mouth noise) still gets ducked.
    n = min(dry_stereo.shape[-1], bg_fx.shape[-1], voice_mono.shape[0])
    if wet_stereo is not None:
        n = min(n, wet_stereo.shape[-1])
    if settings.use_script_aware_duck:
        bg_ducked, _ = ducking.script_aware_duck(
            bg_fx[..., :n],
            voice_mono[:n],
            sr,
            phrases=shifted_segments,
            pre_descent_ms=settings.duck_pre_descent_ms,
            attack_ramp_ms=settings.duck_attack_ramp_ms,
            release_ms=settings.duck_release_ms,
            duck_db=settings.duck_range_db,
            lift_db=settings.duck_lift_db,
            lift_pause_s=settings.duck_lift_pause_s,
            reactive_threshold_db=settings.duck_threshold_db,
            reactive_attack_ms=settings.duck_attack_ms,
            reactive_release_ms=settings.duck_release_ms,
            reactive_lookahead_ms=settings.duck_lookahead_ms,
        )
    else:
        bg_ducked = ducking.freq_selective_duck(
            bg_fx[..., :n],
            voice_mono[:n],
            sr,
            threshold_db=settings.duck_threshold_db,
            range_db=settings.duck_range_db,
            attack_ms=settings.duck_attack_ms,
            release_ms=settings.duck_release_ms,
            lookahead_ms=settings.duck_lookahead_ms,
        )

    # 7b. Reverb ducking. Only relevant when the reverb send is active.
    if wet_stereo is not None and (
        settings.reverb_duck_db < 0.0 or settings.reverb_lift_db > 0.0
    ):
        wet_gain_db = ducking.script_aware_gain_db(
            n, sr,
            phrases=shifted_segments
            if shifted_segments is not None
            else ducking.detect_phrases_from_audio(voice_mono[:n], sr),
            pre_descent_ms=settings.duck_pre_descent_ms,
            attack_ms=settings.duck_attack_ramp_ms,
            release_ms=settings.duck_release_ms,
            duck_db=settings.reverb_duck_db,
            lift_db=settings.reverb_lift_db,
            lift_pause_s=settings.duck_lift_pause_s,
            smooth_hz=8.0,
        )
        wet_lin = (10.0 ** (wet_gain_db / 20.0)).astype(np.float32)
        wet_send_gain = 10.0 ** (settings.reverb_wet_db / 20.0)
        wet_ducked = wet_stereo[..., :n] * wet_send_gain * wet_lin
    elif wet_stereo is not None:
        wet_send_gain = 10.0 ** (settings.reverb_wet_db / 20.0)
        wet_ducked = wet_stereo[..., :n] * wet_send_gain
    else:
        wet_ducked = None

    voice_stereo = dry_stereo[..., :n]
    if wet_ducked is not None:
        voice_stereo = voice_stereo + wet_ducked

    # 8. Sum to a stereo pre-master.
    premaster = voice_stereo[..., :n] + bg_ducked[..., :n]

    # 9. Master bus chain (HPF / glue comp / air).
    mastered = _master_chain()(premaster, sr)
    mastered = _to_stereo(mastered)

    # 10. LUFS normalize FIRST. Doing this before the limiter is critical:
    # normalization is a wide-band gain, so if we limited first then
    # normalized, a quiet mix would get gained back up and re-exceed
    # -1 dBTP (and clip 0 dBFS on hot content). Normalize, then limit.
    mastered, pre_lufs = mastering.normalize_lufs(mastered, sr, settings.target_lufs)

    # 11. True-peak limit (4x oversampled) at -1 dBTP. This is the LAST
    # gain stage that touches amplitude, so the final output respects the
    # true-peak ceiling regardless of LUFS gain or transient content.
    mastered = mastering.true_peak_limit(
        mastered, sr,
        threshold_db=settings.true_peak_db,
        release_ms=200.0,
    )

    # 12. Verify against the gate.
    report = mastering.verify_master(
        mastered, sr,
        target_lufs=settings.target_lufs,
        target_tp_db=settings.true_peak_db,
        lra_range=settings.lra_range,
    )

    # 13. Optional TPDF dither for 16-bit WAV. The limiter already keeps
    # peaks ≤ -1 dBTP so no hard clip is required (a hard clip here would
    # introduce harmonic distortion — exactly what we're trying to avoid).
    bit_depth = "PCM_16" if (output_format == "wav" and settings.dither_16bit) else None
    if bit_depth == "PCM_16":
        mastered = mastering.tpdf_dither(mastered, bits=16)

    # 14. Write outputs.
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    write_kwargs = {}
    if output_format == "wav":
        write_kwargs["bit_depth"] = 16 if settings.dither_16bit else 24

    with AudioFile(str(output_path), "w", sr, num_channels=2, **write_kwargs) as f:
        f.write(mastered)

    stems_dir = output_path.parent / f"{output_path.stem}_stems"
    if settings.write_stems:
        stems_dir.mkdir(parents=True, exist_ok=True)
        with AudioFile(str(stems_dir / "voice.wav"), "w", sr, num_channels=2) as f:
            f.write(voice_stereo[..., :n])
        with AudioFile(str(stems_dir / "music.wav"), "w", sr, num_channels=2) as f:
            f.write(bg_ducked[..., :n])
        with AudioFile(str(stems_dir / "premaster.wav"), "w", sr, num_channels=2) as f:
            f.write(np.clip(premaster, -1.0, 1.0))

    # Build a human-readable note about how the bg was fitted.
    if fit_report.mode == "used_as_is":
        bg_fit_note = (
            f"Background length matched target ({fit_report.target_seconds:.1f}s) — used as-is."
        )
    elif fit_report.mode == "trimmed":
        trimmed = fit_report.source_seconds - fit_report.target_seconds
        bg_fit_note = (
            f"Background ({fit_report.source_seconds:.1f}s) was longer than "
            f"target ({fit_report.target_seconds:.1f}s) — trimmed {trimmed:.1f}s "
            "from the tail (master fade-out covers the cut)."
        )
    elif fit_report.mode == "looped":
        bg_fit_note = (
            f"Background ({fit_report.source_seconds:.1f}s) was looped "
            f"{fit_report.loops}× to fill target ({fit_report.target_seconds:.1f}s) "
            f"with {fit_report.crossfade_ms:.0f} ms equal-power crossfades at seams."
        )
    else:  # tiled_no_xfade
        bg_fit_note = (
            f"Background ({fit_report.source_seconds*1000:.0f}ms) was too short for "
            f"crossfading — tiled {fit_report.loops}× with hard joins. "
            "Consider a longer source for smoother seams."
        )

    return {
        "output_path": str(output_path),
        "stems_dir": str(stems_dir) if settings.write_stems else None,
        "sample_rate": sr,
        "duration_s": mastered.shape[-1] / sr,
        "pre_norm_lufs": pre_lufs,
        "integrated_lufs": report.integrated_lufs,
        "true_peak_db": report.true_peak_db,
        "lra_lu": report.lra_lu,
        "mono_sum_delta_lu": report.mono_sum_delta_lu,
        "issues": report.issues,
        "bg_fit_mode": fit_report.mode,
        "bg_fit_loops": fit_report.loops,
        "bg_source_seconds": fit_report.source_seconds,
        "bg_target_seconds": fit_report.target_seconds,
        "bg_crossfade_ms": fit_report.crossfade_ms,
        "bg_fit_note": bg_fit_note,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
