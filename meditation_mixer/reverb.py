"""Convolution reverb on the voice send.

Replaces Pedalboard's Freeverb (a 1970s Schroeder design that sounds metallic
on close-mic'd TTS) with a real convolution path against a plate-style IR.

Out of the box we synthesize a "studio plate" IR — dense exponentially decaying
stereo noise, high-passed at 250 Hz so the wet signal stays out of the voice
fundamental. You can also drop your own IR (OpenAIR, Samplicity Bricasti M7
free pack, etc.) into `irs/` and pick it from the UI.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, fftconvolve, sosfilt

from .config import IR_DIR, SAMPLE_RATE


SYNTHETIC_PLATE_NAME = "synthetic_plate_48k.wav"


def _hpf(audio: np.ndarray, sr: int, hz: float) -> np.ndarray:
    sos = butter(2, hz, btype="high", fs=sr, output="sos")
    return sosfilt(sos, audio).astype(np.float32)


def synthesize_plate_ir(
    sr: int = SAMPLE_RATE,
    rt60_s: float = 1.2,
    pre_delay_ms: float = 8.0,
    hpf_hz: float = 250.0,
    seed: int = 0xC0FFEE,
) -> np.ndarray:
    """Generate a studio-plate-style stereo IR.

    Returns shape (2, n_samples) float32 with unit ENERGY per channel
    (sum(ir**2) == 1), so convolving a signal of RMS r produces a wet
    signal of comparable RMS — letting `wet_db` mean what it says.

    The shape of a real plate (vs the naive "white noise × exponential
    decay" that v1 of this generator used) has two key properties:
      1. The HIGH frequencies decay much faster than the lows. A pure
         white-noise tail sounds like static hiss because the highs hang
         around for the full RT60. Splitting the tail into a low-mid band
         that decays slowly and a high band that decays ~3× faster
         removes the hissy character.
      2. The tail is smoothed (denser, less stochastic) so it perceives
         as a wash rather than as audible per-sample noise. A mild LPF
         applied to the noise basis does that without losing density.
    """
    rng = np.random.default_rng(seed)
    n = int(sr * rt60_s)
    t = np.arange(n) / sr

    # Two decay envelopes: bright/highs die fast, body sustains.
    decay_body = np.exp(-6.9078 * t / rt60_s).astype(np.float32)            # -60 dB at rt60
    decay_high = np.exp(-6.9078 * t / (rt60_s * 0.35)).astype(np.float32)    # 65 % shorter

    # Decorrelated noise per channel + per band, so the stereo image is
    # diffuse rather than two copies of the same texture.
    body_l = rng.standard_normal(n).astype(np.float32) * decay_body
    body_r = rng.standard_normal(n).astype(np.float32) * decay_body
    hi_l = rng.standard_normal(n).astype(np.float32) * decay_high
    hi_r = rng.standard_normal(n).astype(np.float32) * decay_high

    # Smooth the body noise so the diffuse tail reads as a wash, not as
    # audible per-sample crackle. A 2nd-order LP at 6 kHz keeps the
    # plate's characteristic shimmer but kills the broadband hiss that
    # makes white-noise tails sound like "static" on quiet content.
    sos_smooth = butter(2, 6000.0, btype="low", fs=sr, output="sos")
    body_l = sosfilt(sos_smooth, body_l).astype(np.float32)
    body_r = sosfilt(sos_smooth, body_r).astype(np.float32)
    # The high band keeps its shimmer (no smoothing) but is short-lived.

    # Combine: the body carries the sustain, the highs carry the early
    # sparkle. The 0.35 factor on highs keeps them subordinate to the body.
    left = body_l + 0.35 * hi_l
    right = body_r + 0.35 * hi_r

    # 10 ms raised-cosine attack on the IR head so the very first sample
    # of the wet doesn't kick like a transient (which otherwise reads as a
    # tick at the start of every consonant).
    attack_n = int(sr * 0.010)
    if attack_n > 0:
        ramp = 0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, attack_n, dtype=np.float32))
        left[:attack_n] *= ramp
        right[:attack_n] *= ramp

    # Pre-delay (first reflections arrive after a few ms of silence).
    pd = int(sr * pre_delay_ms / 1000.0)
    left = np.concatenate([np.zeros(pd, dtype=np.float32), left])
    right = np.concatenate([np.zeros(pd, dtype=np.float32), right])

    # HPF the IR so the wet send stays out of the voice fundamental.
    left = _hpf(left, sr, hpf_hz)
    right = _hpf(right, sr, hpf_hz)

    ir = np.stack([left, right], axis=0).astype(np.float32)
    # Unit-energy normalization: convolving a unit-RMS signal yields a
    # roughly unit-RMS wet output, so wet_db = -20 means "wet is 20 dB
    # below the dry voice", which is what the rest of the chain assumes.
    energy = np.sqrt(np.sum(ir ** 2, axis=-1, keepdims=True)) + 1e-12
    ir = ir / energy
    return ir


def ensure_default_ir(sr: int = SAMPLE_RATE) -> Path:
    IR_DIR.mkdir(parents=True, exist_ok=True)
    path = IR_DIR / SYNTHETIC_PLATE_NAME
    if not path.exists():
        ir = synthesize_plate_ir(sr=sr)
        sf.write(path, ir.T, sr, subtype="FLOAT")
    return path


def list_irs() -> list[Path]:
    IR_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p for p in IR_DIR.iterdir() if p.suffix.lower() in {".wav", ".flac"})


def _load_ir(path: Path, sr: int, hpf_hz: float | None = 250.0) -> np.ndarray:
    data, file_sr = sf.read(path, dtype="float32", always_2d=True)
    # data shape: (frames, channels)
    if file_sr != sr:
        # Resample with scipy.signal.resample_poly for quality.
        from scipy.signal import resample_poly
        gcd = np.gcd(file_sr, sr)
        up, down = sr // gcd, file_sr // gcd
        data = resample_poly(data, up, down, axis=0).astype(np.float32)
    ir = data.T  # (channels, samples)
    if ir.shape[0] == 1:
        ir = np.repeat(ir, 2, axis=0)
    elif ir.shape[0] > 2:
        ir = ir[:2]
    # Unit-energy normalization per channel: sum(ir**2) == 1, so convolution
    # gain is predictable regardless of IR length. (Unit-RMS would scale by
    # sqrt(N) — a 1-second 48 kHz IR would add ~+47 dB and clip everything.)
    energy = np.sqrt(np.sum(ir ** 2, axis=-1, keepdims=True)) + 1e-12
    ir = (ir / energy).astype(np.float32)
    if hpf_hz:
        ir = np.stack([_hpf(ir[0], sr, hpf_hz), _hpf(ir[1], sr, hpf_hz)], axis=0)
    return ir


def convolution_reverb_split(
    dry_mono: np.ndarray,
    sr: int,
    ir_path: Path | None = None,
    pre_delay_ms: float = 25.0,
    ir_hpf_hz: float = 250.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (dry_stereo, wet_stereo) separately from a mono dry voice.

    Splitting wet from dry lets the mixer apply an independent "reverb
    duck" — attenuating the wet send while the voice is speaking (so the
    voice stays clear) and lifting it during pauses (so the reverb tail
    blooms into the silence). That bloom is the single biggest "spacious
    room" cue in Headspace/Calm production.

    Both outputs have shape (2, N) where N == dry_mono.shape[0]. The wet
    tail past N is truncated; the master fade-out covers the cut.
    """
    if dry_mono.ndim != 1:
        raise ValueError("convolution_reverb_split expects mono dry signal")

    if ir_path is None:
        ir_path = ensure_default_ir(sr)
    ir = _load_ir(Path(ir_path), sr, hpf_hz=ir_hpf_hz)

    pd = int(sr * pre_delay_ms / 1000.0)
    if pd > 0:
        ir = np.pad(ir, ((0, 0), (pd, 0)))

    wet_l = fftconvolve(dry_mono, ir[0])[: dry_mono.shape[0]]
    wet_r = fftconvolve(dry_mono, ir[1])[: dry_mono.shape[0]]
    wet = np.stack([wet_l, wet_r], axis=0).astype(np.float32)
    dry_stereo = np.stack([dry_mono, dry_mono], axis=0).astype(np.float32)
    return dry_stereo, wet


def convolution_reverb(
    dry_mono: np.ndarray,
    sr: int,
    ir_path: Path | None = None,
    wet_db: float = -20.0,
    pre_delay_ms: float = 25.0,
    ir_hpf_hz: float = 250.0,
) -> np.ndarray:
    """Wet+dry stereo signal from a mono dry voice convolved with `ir_path`.

    Backward-compatible wrapper. Prefer `convolution_reverb_split` when
    you need to time-vary the wet level (e.g. reverb ducking).
    """
    dry_stereo, wet = convolution_reverb_split(
        dry_mono, sr,
        ir_path=ir_path,
        pre_delay_ms=pre_delay_ms,
        ir_hpf_hz=ir_hpf_hz,
    )
    wet_gain = 10.0 ** (wet_db / 20.0)
    return dry_stereo + wet * wet_gain
